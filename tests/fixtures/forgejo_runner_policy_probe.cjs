// No endpoint connections, credentials, raw environments or operator material.
'use strict';
const fs = require('node:fs'), crypto = require('node:crypto');
const cp = require('node:child_process'), https = require('node:https');
(async () => {
const wanted = JSON.parse(process.env.H81_EXPECTED);
const path = '/opt/homelab/job-ca-bundle.pem';
const hosts = fs.readFileSync('/etc/hosts', 'utf8').split('\n').map(line => line.split('#')[0].trim().split(/\s+/));
const addresses = host => hosts.filter(parts => parts.slice(1).includes(host)).map(parts => parts[0]);
let ok;
if (wanted.enabled) {
  const mapped = addresses('h81-route.invalid'), gateway = addresses('host.containers.internal');
  const bundle = fs.readFileSync(path);
  ok = mapped.length > 0 && mapped.every(ip => gateway.includes(ip)) &&
       crypto.createHash('sha256').update(bundle).digest('hex') === wanted.bundle_sha256 &&
       Object.entries(wanted.env).every(([key, value]) => process.env[key] === value);
  // Prove the bind is read-only, independent of file ownership.
  try { fs.writeFileSync(path, bundle); ok = false; } catch (error) { ok = ok && error.code === 'EROFS'; }
} else {
  ok = addresses('h81-route.invalid').length === 0 && !fs.existsSync(path) &&
       ['GIT_SSL_CAINFO','SSL_CERT_FILE','CURL_CA_BUNDLE'].every(key => !process.env[key]);
}
// A newly generated, unrelated certificate must fail in ordinary Git too.
const temp = fs.mkdtempSync('/tmp/h81-negative-tls-');
let server;
try {
  cp.execFileSync('openssl', ['req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256',
    '-nodes','-days','1','-subj','/CN=synthetic','-addext','subjectAltName=IP:127.0.0.1',
    '-keyout',temp+'/key','-out',temp+'/cert'], {stdio:'ignore',timeout:5000});
  let requests=0;
  server=https.createServer({key:fs.readFileSync(temp+'/key'),cert:fs.readFileSync(temp+'/cert')}, (_req,res)=>{requests++;res.end();});
  server.on('tlsClientError',()=>{});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const result=await new Promise(resolve=>{
    const child=cp.spawn('git',['-c','credential.helper=','-c','http.proxy=','ls-remote','https://127.0.0.1:'+server.address().port+'/synthetic'],
      {cwd:temp,env:{...process.env,HOME:temp,GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',GIT_CONFIG_COUNT:'0',GIT_TERMINAL_PROMPT:'0'},stdio:['ignore','pipe','pipe']});
    let stderr='',size=0;const timer=setTimeout(()=>child.kill('SIGKILL'),5000);
    child.stdout.on('data',b=>{size+=b.length;if(size>8192)child.kill('SIGKILL');});
    child.stderr.on('data',b=>{size+=b.length;if(size>8192)child.kill('SIGKILL');else stderr+=b;});
    child.on('error',()=>{clearTimeout(timer);resolve(false);});
    child.on('close',code=>{clearTimeout(timer);resolve(code!==null&&code!==0&&size<=8192&&/server certificate verification failed|SSL certificate problem/i.test(stderr));});
  });
  ok=ok&&result&&requests===0&&!Object.hasOwn(process.env,'GIT_SSL_NO_VERIFY');
} finally {
  if(server){server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
  fs.rmSync(temp,{recursive:true,force:true});
}
console.log('H81_RESULT ' + JSON.stringify({case: wanted.case, result: ok ? 'pass' : 'fail'}));
process.exitCode = ok ? 0 : 1;

})().catch(()=>{process.exitCode=1;});
