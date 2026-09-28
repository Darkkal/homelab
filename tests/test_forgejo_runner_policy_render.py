import pathlib
import hashlib
import unittest
import jinja2
import json
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Pre-#81 render fingerprints with the synthetic inputs below; independent of moving main.
BASELINE = {'config.yaml.j2': '915cabc7267e0529a1b2fb23cd53f727b30c6d21a5e858747968e68ab7422bb1',
            'forgejo-runner.container.j2': '9967ee1a605be671371d7e52e998a35db558b1831f6a4fc8fbca5852c19ea4ec'}

class RenderTests(unittest.TestCase):
    def setUp(self):
        self.env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True, trim_blocks=True)
        self.env.filters['to_json'] = json.dumps
        self.values = dict(forgejo_runner_capacity=1, forgejo_runner_timeout='3h',
            forgejo_runner_shutdown_timeout='3h', forgejo_runner_fetch_timeout='5s',
            forgejo_runner_report_interval='1s', forgejo_runner_labels=['ubuntu-latest:docker://synthetic'],
            forgejo_runner_job_network='', forgejo_runner_uid=1001, forgejo_runner_workdir='/tmp/work',
            forgejo_runner_instance_url='http://synthetic.invalid:3003/', forgejo_runner_uuid='synthetic',
            forgejo_runner_token='synthetic', forgejo_runner_image='synthetic', forgejo_runner_data_dir='/tmp/data')

    def render(self, text):
        return self.env.from_string(text).render(**self.values)

    def test_disabled_matches_prechange_bytes(self):
        for name in ['config.yaml.j2', 'forgejo-runner.container.j2']:
            path='roles/forgejo_runner/templates/'+name
            self.values['forgejo_runner_effective_job_policy']={'enabled':False}
            self.assertEqual(hashlib.sha256(self.render((ROOT/path).read_text()).encode()).hexdigest(),BASELINE[name])

    def test_enabled_emits_protected_options_and_env_without_widening_volume_allowlist(self):
        self.values['forgejo_runner_effective_job_policy']={'enabled':True,'options':'--add-host synthetic.invalid:host-gateway','env':{'GIT_SSL_CAINFO':'/opt/homelab/job-ca-bundle.pem'}}
        config=yaml.safe_load(self.render((ROOT/'roles/forgejo_runner/templates/config.yaml.j2').read_text()))
        self.assertEqual(config['runner']['envs'],self.values['forgejo_runner_effective_job_policy']['env'])
        self.assertEqual(config['container']['options'],self.values['forgejo_runner_effective_job_policy']['options'])
        self.assertEqual(config['container']['valid_volumes'],[])
        self.assertFalse(config['runner']['insecure'])

if __name__=='__main__':unittest.main()
