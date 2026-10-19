// Runs only inside the private mount/PID/IPC namespace, with no engine credential.
import { Codex } from '@openai/codex-sdk';
const chunks = [];
let bytes = 0;
for await (const chunk of process.stdin) {
  bytes += chunk.length;
  if (bytes > 131072) process.exit(2);
  chunks.push(chunk);
}
try {
  const { text, model, reasoning, sandbox } = JSON.parse(Buffer.concat(chunks));
  const codex = new Codex({
    codexPathOverride: '/opt/executor/codex',
    env: { PATH: '/usr/local/bin:/usr/bin:/bin', HOME: '/home/agent',
      CODEX_HOME: '/home/agent/.codex', XDG_CACHE_HOME: '/home/agent/.cache' },
    config: { forced_login_method: 'chatgpt', model_provider: 'openai' },
  });
  const thread = codex.startThread({ model, modelReasoningEffort: reasoning,
    workingDirectory: '/workspace', sandboxMode: sandbox, approvalPolicy: 'untrusted',
    webSearchMode: 'disabled', networkAccessEnabled: false, skipGitRepoCheck: true });
  const controller = new AbortController();
  process.on('SIGTERM', () => controller.abort());
  const { events } = await thread.runStreamed(text, { signal: controller.signal });
  let outcome = 'unknown';
  let count = 0;
  for await (const event of events) {
    // SDK/CLI event bodies can contain prompts, commands and secrets. Never forward them.
    if (++count > 100000) throw new Error('event_limit');
    if (event.type === 'turn.completed') outcome = 'completed';
    if (event.type === 'turn.failed' || event.type === 'error') outcome = 'failed';
  }
  process.stdout.write(JSON.stringify({ outcome }));
} catch {
  process.stdout.write(JSON.stringify({ outcome: 'failed' }));
}
