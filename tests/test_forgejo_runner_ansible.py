"""Replay policy/render tasks in an isolated inventory; never target service hosts."""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

import test_forgejo_runner_job_policy as fixtures
from test_forgejo_runner_job_policy import IMAGE, ROOT
import test_forgejo_runner_policy_render as rendering


class AnsibleTests(unittest.TestCase):
    def test_safe_check_mode_and_no_opt_in_notifications(self):
        with tempfile.TemporaryDirectory(prefix='h81-ansible-') as tmp:
            path = pathlib.Path(tmp)
            config = path / 'ansible.cfg'
            config.write_text('[defaults]\nroles_path = ' + str(ROOT / 'roles') + '\nfilter_plugins = ' + str(ROOT / 'roles/forgejo_runner/filter_plugins') + '\nlocal_tmp = '+tmp+'/local\n')
            env = {**os.environ, 'ANSIBLE_CONFIG': str(config)}
            render = rendering.RenderTests(); render.setUp()
            values = render.values
            values.update(forgejo_runner_job_image=IMAGE,
                          forgejo_runner_labels=['ubuntu-latest:docker://' + IMAGE],
                          forgejo_runner_data_dir=tmp, forgejo_runner_effective_job_policy={'enabled':False})
            for name in ['config.yaml.j2', 'forgejo-runner.container.j2']:
                baseline = (ROOT/'roles/forgejo_runner/templates'/name).read_text()
                (path/name).write_text(render.render(baseline))
            values['forgejo_runner_effective_job_policy']={'enabled':True,'options':'inherited conflict','env':{}}
            tasks = [{'name':'Validate policy','ansible.builtin.include_role':{'name':'forgejo_runner','tasks_from':'job_policy'}},
                     {'name':'Render runner artifacts','ansible.builtin.template':{'src':str(ROOT/'roles/forgejo_runner/templates')+'/{{ item }}','dest':tmp+'/{{ item }}'},
                      'loop':['config.yaml.j2','forgejo-runner.container.j2'], 'register':'rendered', 'notify':'Unexpected restart'},
                     {'ansible.builtin.assert':{'that':['not rendered.changed']}}]
            play = [{'hosts':'localhost','gather_facts':False,'vars':values,'tasks':tasks,
                     'handlers':[{'name':'Unexpected restart','ansible.builtin.fail':{'msg':'Default policy notified restart'}}]}]
            playfile=path/'test.json';playfile.write_text(json.dumps(play))
            def run(args):
                result=subprocess.run(['ansible-playbook','-i','localhost,','-c','local',str(playfile),*args],cwd=tmp,env=env,capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                return result
            run(['--syntax-check'])
            for args in [[], ['--check']]:
                result=run(args)
                self.assertIn('changed=0',result.stdout)
            fixture=fixtures.PolicyTests();fixture.setUp()
            play[0]['vars']['vault_forgejo_runner_job_policy']=fixture.value
            play[0]['tasks']=tasks[:1]+[{'ansible.builtin.assert':{'that':['forgejo_runner_effective_job_policy.enabled']}}]
            playfile.write_text(json.dumps(play));run(['--check'])
            for bad in [{'enabled':True},{'enabled':'true'},{**fixture.value,'ca_sha256':'0'*64}]:
                play[0]['vars']['vault_forgejo_runner_job_policy']=bad;playfile.write_text(json.dumps(play))
                result=subprocess.run(['ansible-playbook','-i','localhost,','-c','local',str(playfile),'--check'],cwd=tmp,env=env,capture_output=True,text=True,timeout=60)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn(fixture.value['ca_certificate'],result.stdout+result.stderr)
            # Parse the complete role without executing account/systemd operations.
            playfile.write_text(json.dumps([{'hosts':'localhost','gather_facts':False,'vars':values,'roles':['forgejo_runner']}]))
            run(['--syntax-check'])

if __name__=='__main__':unittest.main()
