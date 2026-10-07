"""Owner-run synthetic test. Uses local exec, never production credentials or daemon config."""
import hashlib
import json
import os
import pathlib
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import yaml

ROOT=pathlib.Path(__file__).resolve().parent
BASE=pathlib.Path('/home/forgejo-runner/homelab/forgejo-runner/work')
CONFIG=BASE.parent/'config.yaml'
SOCKET='unix:///run/user/1001/podman/podman.sock'


def call(args, timeout=10):
    p=subprocess.run(args,capture_output=True,timeout=timeout)
    if p.returncode or len(p.stdout)+len(p.stderr)>1048576:raise ValueError()
    return p.stdout.decode().strip()


def launch(args):
    p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    selector=selectors.DefaultSelector();data=bytearray();deadline=time.monotonic()+60
    for stream in [p.stdout,p.stderr]:selector.register(stream,selectors.EVENT_READ)
    try:
        while selector.get_map():
            if time.monotonic()>deadline:raise TimeoutError()
            for key,_ in selector.select(.1):
                chunk=os.read(key.fd,4096)
                if not chunk:selector.unregister(key.fileobj);continue
                data.extend(chunk)
                if len(data)>65536:raise ValueError()
        return p.wait(timeout=2),data.decode(errors='replace')
    finally:
        selector.close()
        if p.poll() is None:p.kill();p.wait()
        p.stdout.close();p.stderr.close()


def records(output):
    found=[]
    for line in output.splitlines():
        if 'H81_RESULT ' not in line:continue
        try:value=json.loads(line.split('H81_RESULT ',1)[1])
        except ValueError:continue
        if set(value)!={'case','result'} or value['case'] not in ['default_before','opt_in','default_after'] or value['result'] not in ['pass','fail']:raise ValueError()
        found.append(value)
    return found


def emit(**value):print(json.dumps(value),flush=True)


def cleanup(nonce):
    deadline=time.monotonic()+15
    def bounded(args):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError()
        return call(args,min(5,remaining))
    for kind in ['container','network','volume']:
        listing=['podman','ps','-a','--format','{{.ID}} {{.Names}}','--no-trunc'] if kind=='container' else ['podman',kind,'ls','--format','{{.Name}}']
        for row in bounded(listing).splitlines():
            parts=row.split();name=parts[-1]
            if nonce not in name:continue
            if not re.fullmatch('[A-Za-z0-9_.-]+',name):raise ValueError()
            if kind=='container':
                cid=parts[0]
                if bounded(['podman','inspect','--format','{{.Name}}',cid]).lstrip('/')!=name:raise ValueError()
                bounded(['podman','rm','--force','--time','1',cid])
            else:bounded(['podman',kind,'rm',name])
        if nonce in bounded(listing):raise ValueError()


def main():
    if sys.argv[1:]!=['--run'] or os.getuid()!=1001:raise ValueError()
    os.chdir('/home/forgejo-runner')
    for name,digest in json.loads((ROOT/'hashes.json').read_text()).items():
        if '/' in name or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError()
    packet=json.loads((ROOT/'packet.json').read_text());cfgraw=CONFIG.read_bytes();cfg=yaml.safe_load(cfgraw)
    co=cfg['container'];ru=cfg['runner'];conn=cfg['server']['connections']['forgejo']
    if co.get('options') or co.get('network')!='' or co.get('valid_volumes') or co.get('docker_host')!=SOCKET or co.get('privileged') is not False or co.get('enable_ipv6') is not False or ru.get('insecure') is not False or ru.get('envs') or ru.get('env_file'):raise ValueError()
    if conn['labels']!=['ubuntu-latest:docker://'+packet['image']] or CONFIG.stat().st_mode & 0o777 != 0o600:raise ValueError()
    daemon=call(['podman','inspect','--format','{{.Id}}','forgejo-runner'])
    live=call(['podman','inspect','--format','{{.Image}}','forgejo-runner']).removeprefix('sha256:')
    if live!=call(['podman','image','inspect','--format','{{.Id}}',packet['daemon']]).removeprefix('sha256:'):raise ValueError()
    call(['podman','image','exists',packet['image']])
    for case in ['default_before','opt_in','default_after']:
        if call(['podman','ps','--format','{{.Names}}'])!='forgejo-runner' or CONFIG.read_bytes()!=cfgraw:raise ValueError()
        nonce='h81'+uuid.uuid4().hex
        work=pathlib.Path(tempfile.mkdtemp(prefix=nonce+'-',dir=BASE));os.chmod(work,0o755)
        try:
            enabled=case=='opt_in';expected={'case':case,'enabled':enabled,'env':packet['env'],'bundle_sha256':packet['bundle_sha256']}
            workflow={'name':nonce,'on':{'workflow_dispatch':{}},'jobs':{nonce:{'runs-on':'ubuntu-latest','steps':[{'run':"node <<'H81_JS'\n"+(ROOT/'forgejo_runner_policy_probe.cjs').read_text()+"\nH81_JS\n"}]}}}
            job=workflow['jobs'][nonce]
            if enabled:
                # Exercise runner configuration precedence over workflow/job defaults and job host options.
                workflow['env']={'GIT_SSL_CAINFO':'/synthetic-missing-workflow.pem'}
                job['env']={'GIT_SSL_CAINFO':'/synthetic-missing-job.pem'}
                job['container']={'image':packet['image'],'options':'--add-host h81-route.invalid:192.0.2.1'}
                (work/'job-ca-bundle.pem').write_text(packet['bundle']);os.chmod(work/'job-ca-bundle.pem',0o644)
            (work/'workflow.yml').write_text(yaml.safe_dump(workflow,sort_keys=False))
            args=['podman','exec','--workdir',str(work),'forgejo-runner','timeout','-s','TERM','-k','3','45','forgejo-runner','exec','--directory',str(work),'--workflows',str(work/'workflow.yml'),'--event','workflow_dispatch','--image',packet['image'],'--network','','--container-daemon-socket',SOCKET,'--env-file','/dev/null','--env','H81_EXPECTED='+json.dumps(expected)]
            if enabled:
                args+=['--container-opts',packet['options'].replace('/H81_STAGING',str(work))]
                for key,value in packet['env'].items():args+=['--env',key+'='+value]
            status,output=launch(args);found=records(output)
            if status!=0 or found!=[{'case':case,'result':'pass'}]:
                emit(case=case,result='fail');raise ValueError()
            emit(case=case,result='pass')
        finally:
            cleanup(nonce);shutil.rmtree(work)
            if CONFIG.read_bytes()!=cfgraw or call(['podman','inspect','--format','{{.Id}}','forgejo-runner'])!=daemon or call(['podman','ps','--format','{{.Names}}'])!='forgejo-runner':raise ValueError()
            emit(cleanup='pass')
    emit(launcher_matrix='pass')

if __name__=='__main__':
    try:main()
    except BaseException:emit(launcher_matrix='fail');sys.exit(1)
