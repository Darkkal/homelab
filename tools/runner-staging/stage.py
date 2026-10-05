#!/usr/bin/env python3
"""Finite synthetic staging packet; execution requires separate owner approval."""
import argparse
import hashlib
import json
import io
import tarfile
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

CANDIDATE = 'sha256:7e048ab852dac206966554c2d347addb9d31001ea35481c8c498db5b4abaa734'
NODE_ARCHIVE = Path('/tmp/h85-node-pinned.oci.tar')
NODE_ARCHIVE_SHA = '5c47e9e66b606f2460ee14f0a4e813bcb3bdb2834b8d574641674eb4be033592'
NODE_ID = 'sha256:2ff56a1e437102232fc4f3923138b9513f0d2e36bc0e57f39c3054a86c884e27'
ARCHIVE_SHA = '59bdbabe360a58e73ae003f8f1b50780b3c45953aa362ba937ee9fcce9a77f99'
NODE = 'data.forgejo.org/oci/node:lts-bookworm@sha256:934240a162082fd8b8a2f90cd5114446443f1eba1c5378f6687167ca405e6584'


def emit(**fields):
    print(json.dumps(fields), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-approved', action='store_true', required=True)
    parser.add_argument('--archive', type=Path, default=Path('/tmp/h85-delivery/candidate.oci.tar'))
    args = parser.parse_args()
    if os.getuid() == 0 or os.uname().machine != 'x86_64':
        raise RuntimeError('requires unprivileged Linux amd64 owner account')
    if hashlib.file_digest(args.archive.open('rb'), 'sha256').hexdigest() != ARCHIVE_SHA:
        raise RuntimeError('retained archive identity mismatch')
    if hashlib.file_digest(NODE_ARCHIVE.open('rb'), 'sha256').hexdigest() != NODE_ARCHIVE_SHA:
        raise RuntimeError('retained Node archive identity mismatch')
    root = Path(tempfile.mkdtemp(prefix='h85-stage-', dir='/tmp'))
    os.chmod(root, 0o700)
    emit(event='packet', directory=str(root))
    (root / 'registry-auth.json').write_text('{"auths":{}}')
    configuration = root / 'containers.conf'
    mounts = root / 'mounts.conf'
    networks = root / 'network-config'
    networks.mkdir()
    mounts.write_text('')
    configuration.write_text(
        '[containers]\nenv = []\nenv_host = false\nhttp_proxy = false\n'
        '[network]\nnetwork_backend = "netavark"\nnetwork_config_dir = '
        + json.dumps(str(networks)) + '\n')
    # All policy inputs are packet-owned before any engine mutation.
    for path in (configuration, mounts, networks):
        if path.is_symlink() or path.resolve().parent != root or path.stat().st_uid != os.getuid():
            raise RuntimeError('packet configuration is not confined')
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(root / 'home'),
           'XDG_CONFIG_HOME': str(root / 'config'), 'XDG_DATA_HOME': str(root / 'data'),
           'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}', 'LC_ALL': 'C',
           'REGISTRY_AUTH_FILE': str(root / 'registry-auth.json'),
           'CONTAINERS_CONF': str(configuration),
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_AUTHOR_NAME': 'Synthetic fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
           'GIT_COMMITTER_NAME': 'Synthetic fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
    for name in ('home', 'config', 'data', 'work', 'cache', 'runroot', 'storage'):
        (root / name).mkdir()
    # Sole engine: no default socket, remote connection, shared storage or pruning.
    engine = ['podman', '--remote=false', '--root', str(root / 'storage'),
              '--runroot', str(root / 'runroot'), '--storage-driver=vfs',
              '--network-config-dir', str(networks), '--default-mounts-file', str(mounts)]
    log = (root / 'private.log').open('wb')
    service = None
    passed = False

    def run(command, limit=30, capture=False):
        return subprocess.run(command, env=env, cwd=root, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE if capture else log,
                              stderr=log, timeout=limit, check=True).stdout

    def podman(*command, limit=30, capture=False):
        return run(engine + list(command), limit, capture)

    def interrupt(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        podman('load', '-i', str(args.archive.resolve()), limit=300)
        actual = podman('image', 'inspect', '--format', '{{.Id}}', CANDIDATE, capture=True).decode().strip()
        if actual.removeprefix('sha256:') != CANDIDATE.removeprefix('sha256:'):
            raise RuntimeError('loaded candidate ID mismatch')
        # Owner-exported exact pinned cache: registry no longer serves this digest.
        # OCI export rewrote the manifest but retained a conflicting old digest name.
        # Change only its local reference annotation; all config/layer blobs stay exact.
        normalized = root / 'node.oci.tar'
        with tarfile.open(NODE_ARCHIVE) as source, tarfile.open(normalized, 'w') as target:
            for member in source:
                payload = source.extractfile(member) if member.isfile() else None
                if member.name == 'index.json':
                    index = json.load(payload)
                    index['manifests'][0]['annotations']['org.opencontainers.image.ref.name'] = 'localhost/h85-node:cached'
                    data = json.dumps(index).encode()
                    member.size = len(data)
                    payload = io.BytesIO(data)
                target.addfile(member, payload)
        podman('load', '-i', str(normalized), limit=300)
        node_id = podman('image', 'inspect', '--format', '{{.Id}}', NODE_ID, capture=True).decode().strip()
        if node_id.removeprefix('sha256:') != NODE_ID.removeprefix('sha256:'):
            raise RuntimeError('loaded pinned Node identity mismatch')
        network = podman('network', 'create', '--internal', '--ipv6',
                        '--subnet', '10.85.86.0/24', '--subnet', 'fd85:86::/64',
                        'h85-staging', capture=True).decode().strip()
        refs = {}
        for action in ('checkout', 'cache'):
            source = root / ('fixture-' + action)
            (source / 'dist').mkdir(parents=True)
            (source / '.eslintignore').write_text('fixture\n')
            (source / 'action.yml').write_text(
                'name: synthetic\ndescription: staging fixture\nruns:\n'
                '  using: node20\n  main: dist/main.js\n  post: dist/post.js\n')
            common = ("const fs=require('fs'); const assert=require('assert');\n"
                      "assert(__dirname.startsWith('/run/act/actions/'));\n"
                      "assert.equal(fs.readFileSync(__dirname+'/../.eslintignore','utf8'),'fixture\\n');\n")
            (source / 'dist/main.js').write_text(common +
                f"fs.writeFileSync('/run/act/{action}-main','ok');\n" +
                "fs.appendFileSync(process.env.GITHUB_STATE,'fixture=ok\\n');\n")
            post = common + "assert.equal(process.env.STATE_fixture,'ok');\n"
            if action == 'checkout':
                post += "assert.equal(fs.readFileSync('/run/act/cache-post','utf8'),'ok');\nconsole.log('H85_POST_PASS');\n"
            else:
                post += "fs.writeFileSync('/run/act/cache-post','ok');\n"
            (source / 'dist/post.js').write_text(post)
            run(['git', 'init', str(source)])
            run(['git', '-C', str(source), 'add', '.'])
            run(['git', '-C', str(source), 'commit', '-m', 'Synthetic staging fixture'])
            refs[action] = run(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture=True).decode().strip()
            url = 'https://fixture.invalid/actions/' + action
            digest = hashlib.sha256(url.encode()).hexdigest()
            bare = root / 'cache/act' / digest[:2] / digest[2:]
            bare.parent.mkdir(parents=True, exist_ok=True)
            run(['git', 'clone', '--bare', str(source), str(bare)])
            run(['git', '--git-dir', str(bare), 'remote', 'set-url', 'origin', url])
        workflow = root / 'work/workflow.yml'
        workflow.write_text(f'''name: h85-staging
on: push
jobs:
  staging:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{refs['checkout']}
      - uses: actions/cache@{refs['cache']}
      - name: Workflow script
        run: |
          test "$RUNNER_TEMP" = /tmp
          test "$(cat /run/act/checkout-main)" = ok
          test "$(cat /run/act/cache-main)" = ok
          printf ok > /run/act/script-main
          echo H85_SCRIPT_PASS
      - uses: docker://{NODE_ID}
        with:
          entrypoint: /bin/sh
          args: -ec 'test "$(cat /run/act/script-main)" = ok; echo H85_DOCKER_PASS'
''')
        run(['git', 'init', str(root / 'work')])
        run(['git', '-C', str(root / 'work'), 'add', '.'])
        run(['git', '-C', str(root / 'work'), 'commit', '-m', 'Synthetic workflow'])
        socket = root / 'engine.sock'
        service = subprocess.Popen(engine + ['system', 'service', '--time=0', 'unix:' + str(socket)],
                                   env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        deadline = time.monotonic() + 15
        while not socket.exists() and time.monotonic() < deadline:
            if service.poll() is not None:
                raise RuntimeError('private API failed')
            time.sleep(0.1)
        if not socket.exists():
            raise RuntimeError('private API timeout')
        # Same absolute fixture/cache paths visible to runner and API host.
        podman('run', '--name=h85-candidate', '--pull=never', '--user=0', '--network', network,
               '--env', 'HOME=' + str(root / 'home'), '--env', 'XDG_CACHE_HOME=' + str(root / 'cache'),
               '--env', 'DOCKER_HOST=unix://' + str(socket), '--env', 'GIT_CONFIG_NOSYSTEM=1',
               '--env', 'GIT_CONFIG_GLOBAL=/dev/null', '--security-opt=label=disable',
               '--volume', f'{root / "home"}:{root / "home"}',
               '--volume', f'{root / "cache"}:{root / "cache"}',
               '--volume', f'{root / "work"}:{root / "work"}',
               '--volume', f'{socket}:{socket}',
               '--workdir', str(root / 'work'), '--entrypoint', '/bin/forgejo-runner', CANDIDATE,
               'exec', '--directory', str(root / 'work'), '--workflows', str(workflow),
               '--env-file', '/dev/null', '--no-skip-checkout', '--default-actions-url',
               'https://fixture.invalid', '--image', NODE_ID, '--network', network,
               '--container-daemon-socket', str(socket), '--container-architecture', 'linux/amd64', limit=600)
        log.flush()
        output = (root / 'private.log').read_bytes()
        for marker in ('SCRIPT', 'DOCKER', 'POST'):
            if ('H85_' + marker + '_PASS').encode() not in output:
                raise RuntimeError('missing lifecycle assertion: ' + marker)
        passed = True
        emit(event='staging', actual_copy=True, script=True, docker_share=True, post=True, result='pass')
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        cleanup = True
        # Capture exact IDs in this freshly created private engine; never name/glob prune.
        for kind, listing, removal in (
            ('container', ['ps', '-aq'], ['rm', '-f']),
            ('volume', ['volume', 'ls', '-q'], ['volume', 'rm']),
            ('network', ['network', 'ls', '--format', '{{.ID}} {{.Name}}'], ['network', 'rm'])):
            try:
                rows = podman(*listing, capture=True).decode().splitlines()
                ids = [row.split()[0] for row in rows if kind != 'network' or row.split()[1] == 'h85-staging']
                (root / (kind + '-ids.json')).write_text(json.dumps(ids))
                for resource in ids:
                    podman(*removal, resource)
            except (subprocess.SubprocessError, OSError):
                cleanup = False
        if service is not None:
            service.terminate()
            try:
                service.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait(timeout=5)
        log.close()
        emit(event='cleanup', result='pass' if cleanup else 'fail', retained_private_images=True)
        if not cleanup or not passed:
            raise RuntimeError('staging incomplete; retain private artifacts for investigation')


if __name__ == '__main__':
    main()
