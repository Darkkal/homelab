import fs from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { parseDocument } from 'yaml';

const ROOT = '/var/lib/codex-executor';
// Contains only data deliberately exposed to this instance's agent, never control state.
const AGENT_ROOT = '/var/lib/codex-agent';
const APP = '/opt/executor';
const UID = 10001;
export const profiles = { planner: 'read-only', worker: 'workspace-write', reviewer: 'read-only' };
const cleanEnv = { PATH: '/usr/local/bin:/usr/bin:/bin', HOME: '/nonexistent',
  LANG: 'C.UTF-8', GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null',
  GIT_TERMINAL_PROMPT: '0', GIT_ATTR_NOSYSTEM: '1', GIT_NO_REPLACE_OBJECTS: '1' };
const requireThat = (ok) => { if (!ok) throw new Error('boundary_refused'); };
class UnstoppedProcess extends Error {}

async function protectedPath(file, directory = false, allowedOtherBits = 0) {
  const stat = await fs.lstat(file);
  requireThat(!stat.isSymbolicLink() && stat.uid === 0 && !(stat.mode & (0o077 & ~allowedOtherBits))
    && (directory ? stat.isDirectory() : stat.isFile()));
  return stat;
}

export async function policy() {
  requireThat(process.getuid() === 0);
  await protectedPath('/etc/codex-executor', true);
  await protectedPath('/etc/codex-executor/policy.json');
  try { await protectedPath('/etc/codex-executor/git-credentials'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const raw = await fs.readFile('/etc/codex-executor/policy.json');
  requireThat(raw.length <= 32768);
  const p = JSON.parse(raw);
  const fields = ['instance', 'role', 'model', 'reasoning', 'skillsUrl', 'skillsBranch',
    'instructions', 'timeoutSeconds'];
  requireThat(Object.keys(p).length === fields.length && fields.every(k => Object.hasOwn(p, k)));
  requireThat(typeof p.instance === 'string' && /^[a-z][a-z0-9-]{0,47}$/.test(p.instance));
  requireThat(typeof p.role === 'string' && Object.hasOwn(profiles, p.role));
  requireThat(typeof p.model === 'string' && /^[a-zA-Z0-9._-]{1,100}$/.test(p.model));
  requireThat(['low', 'medium', 'high', 'xhigh'].includes(p.reasoning));
  requireThat(typeof p.instructions === 'string' && p.instructions.length > 0
    && Buffer.byteLength(p.instructions) <= 16384);
  requireThat(Number.isInteger(p.timeoutSeconds) && p.timeoutSeconds >= 30 && p.timeoutSeconds <= 3600);
  requireThat(typeof p.skillsUrl === 'string' && p.skillsUrl.length <= 2048);
  const url = new URL(p.skillsUrl);
  requireThat(url.protocol === 'https:' && !url.username && !url.password && !url.hash && !url.search);
  requireThat(typeof p.skillsBranch === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9/_-]{0,99}$/.test(p.skillsBranch));
  await protectedPath(ROOT, true);
  requireThat(((await protectedPath(AGENT_ROOT, true, 0o011)).mode & 0o777) === 0o711);
  return Object.freeze(p);
}

// Bounds apply to subprocesses too; output/errors are never copied to logs.
export function execute(command, args, { input = '', signal, timeout = 30000,
  limit = 8 * 1024 * 1024, env = cleanEnv, cwd = APP, interactive = false } = {}) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error('cancelled'));
    const child = spawn(command, args, { cwd, env, detached: true,
      stdio: interactive ? 'inherit' : ['pipe', 'pipe', 'ignore'] });
    let output = Buffer.alloc(0);
    let refusal = false;
    let done = false;
    let killFailed = false;
    let stopTimer;
    const groupExists = () => {
      if (!child.pid) return false;
      try { process.kill(-child.pid, 0); return true; }
      catch (error) { if (error.code === 'ESRCH') return false; return true; }
    };
    const kill = () => {
      refusal = true;
      if (child.pid) {
        try { process.kill(-child.pid, 'SIGKILL'); }
        catch (error) { if (error.code !== 'ESRCH') killFailed = true; }
      }
      if (!stopTimer) stopTimer = setTimeout(() => finish(-1, true), 5000);
    };
    const timer = setTimeout(kill, timeout);
    signal?.addEventListener('abort', kill, { once: true });
    if (!interactive) {
      child.stdout.on('data', chunk => {
        if (output.length + chunk.length > limit) kill();
        else output = Buffer.concat([output, chunk]);
      });
      child.stdin.on('error', () => {});
      child.stdin.end(input);
    }
    const finish = (code, timedOutWaiting = false) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      clearTimeout(stopTimer);
      signal?.removeEventListener('abort', kill);
      if (timedOutWaiting || killFailed || groupExists()) {
        // Leave run state quarantined; an ordinary process-group check cannot
        // establish that deliberately detached descendants have exited.
        if (!refusal && child.pid) { try { process.kill(-child.pid, 'SIGKILL'); } catch {} }
        child.stdout?.destroy();
        child.stdin?.destroy();
        child.unref();
        reject(new UnstoppedProcess('process_not_stopped'));
      } else if (refusal || code !== 0) reject(new Error('subprocess_failed'));
      else resolve(output);
    };
    child.once('error', () => finish(-1));
    child.once('close', code => finish(code));
  });
}

async function publishSkills(snapshot) {
  const root = '/etc/codex';
  await fs.mkdir(root, { mode: 0o755 }).catch(error => { if (error.code !== 'EEXIST') throw error; });
  const stat = await fs.lstat(root);
  requireThat(stat.isDirectory() && !stat.isSymbolicLink() && stat.uid === 0 && !(stat.mode & 0o022));
  const link = `${root}/skills`;
  try {
    const current = await fs.lstat(link);
    requireThat(current.isSymbolicLink() && current.uid === 0 && await fs.readlink(link) === snapshot);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    await fs.symlink(snapshot, link);
  }
}

async function skills(p, base, view, signal) {
  const repo = `${base}/source`;
  const git = (...args) => execute('/usr/bin/git', ['-C', repo,
    '-c', `core.hooksPath=${APP}/empty-hooks`, '-c', 'core.fsmonitor=false',
    '-c', 'core.attributesFile=/dev/null', '-c', 'protocol.allow=never',
    '-c', 'protocol.https.allow=always', '-c', 'credential.helper=',
    '-c', 'credential.helper=store --file=/etc/codex-executor/git-credentials',
    ...args], { signal });
  let fresh = false;
  try { await fs.mkdir(repo, { mode: 0o700 }); fresh = true; await git('init', '--quiet'); }
  catch (error) { if (error.code !== 'EEXIST') throw error; }
  // No upstream-controlled local configuration, attributes, submodules or executable filters.
  const config = (await git('config', '--local', '--name-only', '--list')).toString().trim().split('\n');
  requireThat(config.every(k => ['core.repositoryformatversion', 'core.filemode',
    'core.bare', 'core.logallrefupdates'].includes(k)));
  requireThat(!(await git('status', '--porcelain=v1', '--untracked-files=all')).length);
  const flags = (await git('ls-files', '-v')).toString().split('\n').filter(Boolean);
  requireThat(flags.every(line => line.startsWith('H ')));
  let previous;
  if (!fresh) previous = (await git('rev-parse', '--verify', 'HEAD')).toString().trim();
  await git('fetch', '--no-tags', '--no-recurse-submodules', p.skillsUrl, `refs/heads/${p.skillsBranch}`);
  const sha = (await git('rev-parse', 'FETCH_HEAD')).toString().trim();
  requireThat(/^[0-9a-f]{40,64}$/.test(sha));
  if (previous) await git('merge-base', '--is-ancestor', previous, sha);
  const treeBytes = await git('ls-tree', '-rz', '--full-tree', sha);
  requireThat(Buffer.from(treeBytes.toString()).equals(treeBytes));
  const tree = treeBytes.toString().split('\0').filter(Boolean);
  requireThat(tree.length > 0 && tree.length <= 2000);
  const snapshot = `${view}/skills`;
  await fs.rm(snapshot, { recursive: true, force: true });
  await fs.mkdir(snapshot, { mode: 0o755 });
  const names = new Set();
  let total = 0;
  let skillCount = 0;
  for (const entry of tree) {
    const match = /^(100644|100755) blob ([0-9a-f]+)\t(.+)$/.exec(entry);
    requireThat(match);
    const [, , blob, name] = match;
    requireThat(!name.startsWith('/') && name.split('/').every(v => v && v !== '.' && v !== '..')
      && !name.split('/').some(v => ['.git', '.gitattributes', '.gitmodules'].includes(v)));
    let body = await git('cat-file', 'blob', blob);
    total += body.length;
    requireThat(total <= 8 * 1024 * 1024);
    if (name.endsWith('/SKILL.md') || name === 'SKILL.md') {
      const front = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(body.toString());
      requireThat(front);
      const doc = parseDocument(front[1], { uniqueKeys: true });
      requireThat(!doc.errors.length);
      const meta = doc.toJS({ maxAliasCount: 0 });
      requireThat(typeof meta?.name === 'string' && /^[a-z0-9-]{1,64}$/.test(meta.name)
        && typeof meta.description === 'string' && meta.description.trim().length > 0
        && meta.description.length <= 4096 && !names.has(meta.name));
      names.add(meta.name);
      skillCount++;
      if (meta.name === 'skill-source-sync') {
        // Deployment-local replacement; the shared collection is never modified.
        body = Buffer.from('---\nname: skill-source-sync\ndescription: Runner-managed skill preparation status.\n---\nThe runner prepared this immutable view before launch. Do not update shared skills during a run.\n');
      }
    }
    await fs.mkdir(path.dirname(`${snapshot}/${name}`), { recursive: true });
    await fs.writeFile(`${snapshot}/${name}`, body, { mode: match[1] === '100755' ? 0o755 : 0o644 });
    await fs.chmod(`${snapshot}/${name}`, match[1] === '100755' ? 0o755 : 0o644);
  }
  requireThat(skillCount > 0);
  // Checkout only after rejecting filters/attributes and malformed tracked paths.
  await git('checkout', '--quiet', '--detach', sha);
  requireThat((await git('rev-parse', 'HEAD')).toString().trim() === sha);
  requireThat(!(await git('status', '--porcelain=v1', '--untracked-files=all')).length);
  // Explicit modes keep published paths traversable even with a restrictive launcher umask.
  async function exposeDirectories(dir) {
    for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) await exposeDirectories(path.join(dir, entry.name));
    }
    await fs.chmod(dir, 0o755);
  }
  await exposeDirectories(snapshot);
  return sha;
}

export async function run(p, task, signal, login = false) {
  const deadline = AbortSignal.timeout((login ? 360 : p.timeoutSeconds) * 1000);
  signal = AbortSignal.any([signal, deadline]);
  const identity = { run: randomUUID(), instance: p.instance, role: p.role };
  if (!login && (!task || Object.keys(task).join(',') !== 'text'
    || typeof task.text !== 'string' || !task.text.trim() || Buffer.byteLength(task.text) > 65536)) {
    return { ...identity, outcome: 'refused' };
  }
  const base = `${ROOT}/${p.instance}`;
  const view = `${AGENT_ROOT}/${p.instance}`;
  await fs.mkdir(base, { mode: 0o700 }).catch(e => { if (e.code !== 'EEXIST') throw e; });
  await protectedPath(base, true);
  let locked = false;
  let launched = false;
  let quarantined = false;
  try {
    await fs.mkdir(`${base}/lock`, { mode: 0o700 });
    locked = true;
    await fs.mkdir(view, { mode: 0o711 }).catch(e => { if (e.code !== 'EEXIST') throw e; });
    await protectedPath(view, true, 0o011);
    await fs.chmod(view, 0o711);
    identity.skills = await skills(p, base, view, signal);
    await publishSkills(`${view}/skills`);
    await fs.writeFile(`${base}/prepared.json`, JSON.stringify(identity), { mode: 0o600 });
    // Dedicated writable home persists auth/session/cache, never shared with another instance.
    const home = `${view}/home`;
    await fs.mkdir(home, { mode: 0o700 }).catch(e => { if (e.code !== 'EEXIST') throw e; });
    const h = await fs.lstat(home);
    requireThat(h.isDirectory() && !h.isSymbolicLink() && [0, UID].includes(h.uid) && !(h.mode & 0o077));
    await fs.chown(home, UID, UID);
    // Recreate managed configuration without following an agent-created symlink.
    const codexHome = `${home}/.codex`;
    await fs.mkdir(codexHome, { mode: 0o700 }).catch(e => { if (e.code !== 'EEXIST') throw e; });
    const c = await fs.lstat(codexHome);
    requireThat(c.isDirectory() && !c.isSymbolicLink() && [0, UID].includes(c.uid) && !(c.mode & 0o077));
    await fs.chown(codexHome, UID, UID);
    await fs.rm(`${codexHome}/config.toml`, { force: true });
    const config = `forced_login_method = "chatgpt"\ncli_auth_credentials_store = "file"\nmodel_provider = "openai"\ndeveloper_instructions = ${JSON.stringify(p.instructions)}\n`;
    await fs.writeFile(`${codexHome}/config.toml`, config, { flag: 'wx', mode: 0o644 });
    await fs.chmod(`${codexHome}/config.toml`, 0o644);
    await fs.rm(`${view}/workspace`, { recursive: true, force: true });
    await fs.mkdir(`${view}/workspace`, { mode: 0o700 });
    await fs.chown(`${view}/workspace`, UID, UID);
    const temporary = `${home}/.tmp`;
    await fs.mkdir(temporary, { mode: 0o700 }).catch(e => { if (e.code !== 'EEXIST') throw e; });
    const tmp = await fs.lstat(temporary);
    requireThat(tmp.isDirectory() && !tmp.isSymbolicLink() && [0, UID].includes(tmp.uid) && !(tmp.mode & 0o077));
    await fs.chown(temporary, UID, UID);
    const env = { PATH: cleanEnv.PATH, HOME: home, CODEX_HOME: codexHome,
      XDG_CACHE_HOME: `${home}/.cache`, TMPDIR: temporary };
    if (process.env.FORGEJO_TOKEN !== undefined) {
      requireThat(process.env.FORGEJO_TOKEN.length > 0 && process.env.FORGEJO_TOKEN.length <= 8192);
      env.FORGEJO_TOKEN = process.env.FORGEJO_TOKEN;
    }
    const launcher = ['--reuid=10001', '--regid=10001', '--clear-groups', '--no-new-privs',
      '--inh-caps=-all', '--ambient-caps=-all', '--bounding-set=-all',
      ...(login ? [`${APP}/codex`, 'login', '--device-auth'] : [`${APP}/node`, `${APP}/agent.mjs`])];
    requireThat(!signal.aborted);
    launched = true;
    if (login) {
      // Only the operator login command displays the native device URL/code.
      await execute('/usr/bin/setpriv', launcher, { signal, env, cwd: `${view}/workspace`,
        timeout: 300000, interactive: true });
      return { ...identity, outcome: 'login_exited' };
    }
    const output = await execute('/usr/bin/setpriv', launcher, { signal, env, cwd: `${view}/workspace`,
      timeout: p.timeoutSeconds * 1000,
      limit: 1024, input: JSON.stringify({ text: task.text, model: p.model,
        reasoning: p.reasoning, sandbox: profiles[p.role] }) });
    const result = JSON.parse(output);
    requireThat(['completed', 'failed', 'unknown'].includes(result.outcome));
    return { ...identity, outcome: result.outcome };
  } catch (error) {
    if (error instanceof UnstoppedProcess) {
      quarantined = true;
      return { ...identity, outcome: 'unknown', stop_instance: true };
    }
    return { ...identity, outcome: deadline.aborted ? 'timed_out' : signal.aborted ? 'cancelled'
      : launched ? 'unknown' : 'refused' };
  } finally {
    if (locked && !quarantined) {
      try {
        await fs.rm(`${view}/workspace`, { recursive: true, force: true });
        await fs.rmdir(`${base}/lock`);
      } catch {
        // A retained lock makes cleanup failure visible to the next startup.
        return { ...identity, outcome: 'unknown', stop_instance: true };
      }
    }
  }
}
