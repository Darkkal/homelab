"""Prepare a synthetic launcher packet on the controller; never access the runner."""
import hashlib
import json
import pathlib
import sys
import jinja2
import yaml
from test_forgejo_runner_job_policy import PolicyTests, policy, ROOT
from test_forgejo_runner_policy_render import RenderTests


def main():
    dest=pathlib.Path(sys.argv[1]);dest.mkdir(mode=0o755,parents=True,exist_ok=False)
    inventory=yaml.safe_load((ROOT/'inventory/group_vars/forgejo_runner_hosts.yml').read_text())
    image=inventory['forgejo_runner_job_image']
    fixture=PolicyTests();fixture.setUp()
    value={**fixture.value,'job_image':image,'hostname':'h81-route.invalid'}
    render=RenderTests();render.setUp()
    render.values.update(forgejo_runner_job_image=image,forgejo_runner_labels=['ubuntu-latest:docker://'+image])
    # The wrapper replaces this path with its private per-invocation staging path.
    effective=policy.job_policy(value,image,'/H81_STAGING',['ubuntu-latest:docker://'+image])
    render.values['forgejo_runner_effective_job_policy']=effective
    rendered=yaml.safe_load(render.render((ROOT/'roles/forgejo_runner/templates/config.yaml.j2').read_text()))
    packet={'image':image,'daemon':inventory['forgejo_runner_image'],
            'options':rendered['container']['options'],'env':rendered['runner']['envs'],
            'bundle':effective['bundle'],'bundle_sha256':hashlib.sha256(effective['bundle'].encode()).hexdigest()}
    (dest/'packet.json').write_text(json.dumps(packet))
    for src in [ROOT/'tests/fixtures/forgejo_runner_policy_probe.cjs',ROOT/'tests/run_forgejo_runner_launcher.py']:
        (dest/src.name).write_bytes(src.read_bytes())
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir()}
    (dest/'hashes.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('synthetic_launcher_packet=prepared')

if __name__=='__main__':main()
