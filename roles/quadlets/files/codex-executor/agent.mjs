// Runs as the role's unprivileged UID with an explicit environment.
import { Codex } from '@openai/codex-sdk';

// Only fixed categories leave this process; error text may contain secrets or prompts.
export function classifyFailure(message) {
  const text = typeof message === 'string' ? message.slice(0, 8192) : '';
  if (/unauthori[sz]ed|authentication failed|invalid[_ -]token|login required|\b401\b/i.test(text)) return 'authentication';
  if (/model[^\n]{0,120}(not found|not available|unsupported|not supported|does not exist|access)/i.test(text)) return 'model_unavailable';
  if (/rate.limit|quota.exceeded|usage.limit|too many requests|\b429\b/i.test(text)) return 'rate_or_quota';
  if (/sandbox|bubblewrap|\bbwrap\b|permission denied|operation not permitted|\bEACCES\b|\bEPERM\b/i.test(text)) return 'sandbox_or_permission';
  if (/certificate|\bTLS\b|connection refused|could not resolve|\bDNS\b|network/i.test(text)) return 'network_or_tls';
  return 'other';
}
export function failureSignals(message) {
  const text = typeof message === 'string' ? message.slice(0, 8192) : '';
  const patterns = {
    cli_exit: /Codex Exec exited with code/i, config: /config|approval.policy/i,
    argument: /argument|invalid value|unexpected/i, model: /model/i,
    auth: /auth|login|credential|token/i, http: /\bHTTP\b|status code|\b(?:400|401|403|404|429|500|502|503)\b/i,
    request: /request|response|stream/i, network: /network|connection|dns|tls|certificate/i,
    sandbox: /sandbox|bwrap|permission|denied/i, filesystem: /file|directory|path|ENOENT/i,
    json: /json|parse|syntax/i, process: /spawn|executable|process|signal/i,
  };
  return Object.entries(patterns).filter(([, pattern]) => pattern.test(text)).map(([name]) => name);
}
const chunks = [];
let bytes = 0;
for await (const chunk of process.stdin) {
  bytes += chunk.length;
  if (bytes > 131072) process.exit(2);
  chunks.push(chunk);
}
try {
  const { text, model, reasoning, sandbox } = JSON.parse(Buffer.concat(chunks));
  const env = { PATH: '/usr/local/bin:/usr/bin:/bin', HOME: process.env.HOME,
    CODEX_HOME: process.env.CODEX_HOME, XDG_CACHE_HOME: process.env.XDG_CACHE_HOME,
    TMPDIR: process.env.TMPDIR };
  if (process.env.FORGEJO_TOKEN) env.FORGEJO_TOKEN = process.env.FORGEJO_TOKEN;
  const codex = new Codex({
    codexPathOverride: '/opt/executor/codex',
    env,
    config: { forced_login_method: 'chatgpt', model_provider: 'openai' },
  });
  const thread = codex.startThread({ model, modelReasoningEffort: reasoning,
    workingDirectory: process.cwd(), sandboxMode: sandbox, approvalPolicy: 'on-request',
    webSearchMode: 'disabled', networkAccessEnabled: false, skipGitRepoCheck: true });
  const controller = new AbortController();
  process.on('SIGTERM', () => controller.abort());
  const { events } = await thread.runStreamed(text, { signal: controller.signal });
  let outcome = 'unknown';
  let failureCategory = 'other';
  let failureStage = 'event';
  let signals = [];
  let count = 0;
  for await (const event of events) {
    // SDK/CLI event bodies can contain prompts, commands and secrets. Never forward them.
    if (++count > 100000) throw new Error('event_limit');
    if (event.type === 'turn.completed') outcome = 'completed';
    if (event.type === 'turn.failed' || event.type === 'error') {
      outcome = 'failed';
      const message = event.type === 'turn.failed' ? event.error?.message : event.message;
      failureStage = event.type === 'turn.failed' ? 'turn_failed' : 'stream_error';
      failureCategory = classifyFailure(message);
      signals = failureSignals(message);
    }
  }
  process.stdout.write(JSON.stringify(outcome === 'failed' ? { outcome, failure_category: failureCategory, failure_stage: failureStage, failure_signals: signals } : { outcome }));
} catch (error) {
  process.stdout.write(JSON.stringify({ outcome: 'failed', failure_category: classifyFailure(error?.message), failure_stage: 'exception', failure_signals: failureSignals(error?.message) }));
}
