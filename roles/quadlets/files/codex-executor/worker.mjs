import { Hatchet } from '@hatchet-dev/typescript-sdk';
import { policy, run } from './boundary.mjs';

// Do not let SDK diagnostic exceptions serialize task input, engine headers or responses.
const silentLogger = () => ({ debug() {}, info() {}, green() {}, warn() {}, error() {} });
const shutdown = new AbortController();
let worker;
let running;
let activeRun;
let stopping;
let accepting = false;
let busy = false;
const emit = result => process.stdout.write(`${JSON.stringify(result)}\n`);
function stopWorker() {
  accepting = false;
  shutdown.abort();
  if (!stopping) {
    // Keep this deadline armed until process exit, including if stop/start never settle.
    setTimeout(() => process.exit(1), 10000);
    stopping = (async () => {
      try {
        await worker?.stop();
        await running?.catch(() => {});
      } finally {
        await activeRun?.catch(() => {});
      }
    })();
  }
  return stopping;
}
function foregroundRun(p, task, login = false) {
  activeRun = (async () => {
    const result = await run(p, task, shutdown.signal, login);
    // Include run()'s finally and result flush in the operation awaited by signal shutdown.
    await new Promise((resolve, reject) => {
      process.stdout.write(`${JSON.stringify(result)}\n`, error => error ? reject(error) : resolve());
    });
    return result;
  })();
  return activeRun;
}
async function main() {
  const p = await policy();
  if (process.argv[2] === 'login') {
    const result = await foregroundRun(p, null, true);
    if (result.stop_instance) { await stopWorker().catch(() => {}); process.exit(1); }
    return;
  }
  if (process.argv[2] === 'manual') {
    const chunks = [];
    let bytes = 0;
    const inputDeadline = setTimeout(() => process.stdin.destroy(new Error('input_timeout')), 30000);
    try {
      for await (const chunk of process.stdin) {
        bytes += chunk.length;
        if (bytes > 131072) throw new Error('input_limit');
        chunks.push(chunk);
      }
    } finally { clearTimeout(inputDeadline); }
    const result = await foregroundRun(p, JSON.parse(Buffer.concat(chunks)));
    if (result.stop_instance) { await stopWorker().catch(() => {}); process.exit(1); }
    return;
  }
  if (process.argv[2] !== 'worker') throw new Error('invalid_mode');
  const hatchet = Hatchet.init({ logger: silentLogger, log_level: 'OFF',
    cancellation_grace_period: 5, cancellation_warning_threshold: 4 });
  const task = hatchet.task({ name: `codex-${p.role}`, retries: 0,
    executionTimeout: `${p.timeoutSeconds + 15}s`, scheduleTimeout: '5m',
    fn: async (input, ctx) => {
      if (!accepting || shutdown.signal.aborted) return { outcome: 'refused' };
      // Local guard supplements slots:1; duplicate deliveries have no exactly-once promise.
      if (busy) return { outcome: 'busy' };
      busy = true;
      // The SDK may stop tracking a cancelled task before its callback settles.
      activeRun = (async () => { try {
        const signal = AbortSignal.any([shutdown.signal, ctx.abortController.signal]);
        const result = await run(p, input, signal);
        if (result.stop_instance) {
          accepting = false;
          process.exitCode = 1;
          // stop() waits for this task, so initiate it only after returning.
          setImmediate(() => { stopWorker().catch(() => {}).finally(() => process.exit(1)); });
        }
        emit(result);
        return result;
      } catch {
        const result = { instance: p.instance, role: p.role, outcome: 'unknown' };
        emit(result);
        return result;
      } finally { busy = false; } })();
      return await activeRun;
    },
  });
  const startup = setTimeout(() => { shutdown.abort(); process.exit(1); }, 30000);
  try {
    worker = await hatchet.worker(`codex-${p.instance}`, { slots: 1, durableSlots: 0,
      workflows: [task], labels: { role: p.role, instance: p.instance }, handleKill: false });
    running = worker.start();
    running.catch(() => shutdown.abort());
    await worker.waitUntilReady(25000);
    if (shutdown.signal.aborted) throw new Error('startup_aborted');
    accepting = true;
    clearTimeout(startup);
    await running;
    await stopWorker();
    process.exit(process.exitCode || 0);
  } catch (error) {
    // Do not clear the startup deadline until the resident worker has been stopped/awaited.
    await stopWorker().catch(() => {});
    throw error;
  } finally { accepting = false; clearTimeout(startup); }
}
for (const sig of ['SIGTERM', 'SIGINT']) {
  process.on(sig, async () => {
    await stopWorker().catch(() => {});
    process.exit(process.exitCode || 0);
  });
}
main().catch(async () => {
  await stopWorker().catch(() => {});
  process.stdout.write(`${JSON.stringify({ outcome: 'startup_or_input_refused' })}\n`,
    () => process.exit(1));
});
