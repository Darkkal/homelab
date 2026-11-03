import https from 'node:https';

// All paths below are constructed from already validated identifiers. Never
// follow upstream redirects or forward response/error bodies to logs.
export function validateForgejoOrigin(origin) {
  if (typeof origin !== 'string') throw new Error('reader_config');
  const base = new URL(origin);
  if (base.protocol !== 'https:' || base.username || base.password || base.pathname !== '/'
      || base.search || base.hash) throw new Error('reader_config');
  return base;
}

export function forgejoReader({ origin, ca, token, signal }) {
  const base = validateForgejoOrigin(origin);
  if (typeof token !== 'string' || !token || !ca) throw new Error('reader_config');
  const agent = new https.Agent({ ca, rejectUnauthorized: true, keepAlive: false });
  async function get(parts, query = {}) {
    const url = new URL(`/api/v1/${parts.map(encodeURIComponent).join('/')}`, base);
    for (const [key, value] of Object.entries(query)) url.searchParams.set(key, String(value));
    return await new Promise((resolve, reject) => {
      let done = false, size = 0, response;
      const finish = (error, value) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        if (error) { response?.destroy(); req.destroy(); reject(error); }
        else resolve(value);
      };
      const req = https.get(url, { agent, signal, headers: { Authorization: `token ${token}`, Accept: 'application/json' } }, res => {
        response = res;
        if (res.statusCode !== 200) { finish(new Error('read_refused')); return; }
        const chunks = [];
        res.on('data', chunk => { size += chunk.length; if (size > 1048576) { finish(new Error('read_limit')); } else chunks.push(chunk); });
        res.on('error', () => finish(new Error('read_failed')));
        res.on('end', () => { try { finish(null, JSON.parse(Buffer.concat(chunks))); } catch { finish(new Error('read_invalid')); } });
      });
      const timer = setTimeout(() => finish(new Error('read_timeout')), 10000);
      req.on('error', () => finish(new Error('read_failed')));
    });
  }
  const path = (repo, suffix) => ['repos', ...repo.split('/'), ...suffix];
  return Object.freeze({
    repository: repo => get(path(repo, [])),
    issue: (repo, number) => get(path(repo, ['issues', String(number)])),
    pull: (repo, number) => get(path(repo, ['pulls', String(number)])),
    comment: (repo, id) => get(path(repo, ['issues', 'comments', String(id)])),
    reviews: (repo, number) => get(path(repo, ['pulls', String(number), 'reviews']), { page: 1, limit: 50 }),
    status: (repo, sha) => get(path(repo, ['commits', sha, 'status'])),
    actor: (repo, actor) => get(path(repo, ['collaborators', actor, 'permission'])),
  });
}
