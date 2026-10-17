"""Native Ansible configuration convergence and actual Quadlet generation.

Only temporary local inventories and dummy secrets; no host service operations.
"""
import copy
import hashlib
import json
import os
import re
import shlex
from pathlib import Path
import site
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
DUMMY = 'synthetic token " \\ newline\n☃'


class WebGalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='webgallery-test-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        shutil.copytree(ROOT / 'roles/quadlets', self.work / 'roles/quadlets')
        (self.work / 'roles/quadlets/handlers/main.yml').write_text(yaml.safe_dump([
            {'name': 'Restart webgallery service',
             'ansible.builtin.debug': {'msg': 'Synthetic restart notification'}}]))
        self.data = self.work / 'data with spaces'
        (self.data / 'scrapers/gallery-dl').mkdir(parents=True)
        self.settings = {'app': {'colorTheme': 'dark', 'customFutureOption': [True, 3]},
                         'scraper': {'cookiesSource': 'firefox', 'proxy': '', 'retries': 7}}
        self.gallery = {'extractor': {'cookies': ['firefox'], 'pixiv': {'filename': '{id}.{extension}'},
                                      'twitter': {'directory': ['{category}', '{author[id]}']}},
                        'downloader': {'retries': 7, 'proxy': ''},
                        'postprocessor': {'custom': {'name': 'metadata', 'event': 'post'}}}
        self.values = dict(webgallery_enabled=True, webgallery_data_dir=str(self.data),
                           webgallery_media_dir=str(self.work / 'bulk media'),
                           webgallery_browser_dir=str(self.work / 'browser profile'),
                           webgallery_image='localhost/synthetic-gallery:fixture',
                           webgallery_settings=self.settings,
                           webgallery_gallery_dl_config=self.gallery,
                           vault_webgallery_pixiv_refresh_token=DUMMY,
                           network_name='homelab.network',
                           quadlet_dir=str(self.work), quadlet_services=[],
                           ansible_facts={'user_uid': os.getuid(), 'user_gid': os.getgid()})
        (self.work / 'inventory.yml').write_text('all:\n  children:\n    service_hosts:\n      hosts:\n        fixture:\n          ansible_connection: local\n')
        (self.work / 'ansible.cfg').write_text(
            '[defaults]\ninventory=inventory.yml\nroles_path=' + str(self.work / 'roles') +
            '\nretry_files_enabled=False\ninterpreter_python=auto_silent\n')
        self.env = {'PATH': os.environ['PATH'], 'HOME': str(self.work),
                    'ANSIBLE_CONFIG': str(self.work / 'ansible.cfg'),
                    'ANSIBLE_LOCAL_TEMP': str(self.work / 'controller'),
                    'ANSIBLE_REMOTE_TEMP': str(self.work / 'remote'),
                    'ANSIBLE_NOCOLOR': '1', 'PYTHONPATH': site.getusersitepackages()}

    def run_play(self, values=None, disabled=False, extra=(), expect_success=True, tasks_override=None, site_play=False):
        (self.work / 'vars.yml').write_text(yaml.safe_dump(values or self.values))
        tasks = [{'ansible.builtin.include_role': {'name': 'quadlets', 'public': True,
                                                   **({} if disabled else {'tasks_from': 'webgallery'})}}]
        if not disabled:
            tasks += [{'ansible.builtin.template': {
                'src': str(ROOT / 'roles/quadlets/templates/webgallery.container.j2'),
                'dest': str(self.work / 'webgallery.container'), 'mode': '0644'}}]
        if tasks_override is not None:
            tasks = tasks_override
        play = [{'hosts': 'all', 'gather_facts': False, 'vars_files': ['vars.yml'],
                 'tasks': tasks, 'handlers': [{'name': 'Restart webgallery service',
                     'ansible.builtin.debug': {'msg': 'Synthetic restart notification'}}]}]
        if site_play:
            selected = next(p for p in yaml.safe_load((ROOT / 'playbooks/site.yml').read_text())
                            if p.get('name') == 'Deploy opted-in Web Gallery')
            play = [{**selected, 'hosts': 'all', 'gather_facts': False, 'vars_files': ['vars.yml']}]
        (self.work / 'play.yml').write_text(yaml.safe_dump(play))
        result = subprocess.run(['ansible-playbook', 'play.yml', *extra], cwd=self.work,
                                env=self.env, text=True, capture_output=True)
        self.assertNotIn(DUMMY, result.stdout + result.stderr)
        if expect_success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Validate adopted Web Gallery inputs', result.stdout)
        return result.stdout + result.stderr

    def test_full_configuration_idempotence_check_and_restore(self):
        self.run_play(extra=('--syntax-check',))
        self.run_play(extra=('--check', '--diff'))
        self.assertFalse((self.data / 'settings.json').exists())
        self.run_play(extra=('--diff',))
        settings_path = self.data / 'settings.json'
        gallery_path = self.data / 'scrapers/gallery-dl/gallery-dl.conf'
        self.assertEqual(json.loads(settings_path.read_text()), self.settings)
        expected = copy.deepcopy(self.gallery)
        expected['extractor']['pixiv']['refresh-token'] = DUMMY
        self.assertEqual(json.loads(gallery_path.read_text()), expected)
        self.assertEqual(gallery_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(settings_path.stat().st_mode & 0o777, 0o600)
        self.assertIn('changed=0', self.run_play())
        edited = copy.deepcopy(expected)
        edited['downloader']['retries'] = 999
        gallery_path.write_text(json.dumps(edited))
        self.assertIn('changed=1', self.run_play())
        self.assertEqual(json.loads(gallery_path.read_text()), expected)
        self.assertIn('changed=0', self.run_play(extra=('--check', '--diff')))

    def test_missing_and_empty_required_secret_fail_without_writes(self):
        for token in (None, '', '   '):
            values = copy.deepcopy(self.values)
            if token is None:
                values.pop('vault_webgallery_pixiv_refresh_token')
            else:
                values['vault_webgallery_pixiv_refresh_token'] = token
            self.run_play(values, expect_success=False)
            self.assertFalse((self.data / 'settings.json').exists())

    def test_disabled_role_does_not_require_inputs_or_create_unit(self):
        self.assertIn('changed=0', self.run_play({'webgallery_enabled': False,
            'quadlet_services': [], 'quadlet_dir': str(self.work)}, disabled=True))
        self.assertIn('changed=0', self.run_play({'webgallery_enabled': False}, site_play=True))
        self.assertFalse((self.work / 'webgallery.container').exists())
        self.assertFalse((self.data / 'settings.json').exists())

    def test_disabled_base_paths_and_caddy_route(self):
        base = yaml.safe_load((ROOT / 'roles/base/tasks/main.yml').read_text())
        task = next(t for t in base if t.get('name') == 'Ensure opted-in Web Gallery data directories exist')
        caddy = yaml.safe_load((ROOT / 'roles/caddy/defaults/main.yml').read_text())
        values = {**caddy, 'webgallery_enabled': False}
        tasks = [task, {'ansible.builtin.template': {
            'src': str(ROOT / 'roles/caddy/templates/Caddyfile.j2'),
            'dest': str(self.work / 'Caddyfile')}}]
        self.run_play(values, tasks_override=tasks)
        disabled = (self.work / 'Caddyfile').read_text()
        self.assertNotIn('webgallery', disabled)
        # Original Caddy routes remain byte-identical with opt-in disabled.
        self.assertEqual(hashlib.sha256(disabled.encode()).hexdigest(), '32de50b379ffb8a8f5f47a3d63e5a413d1f95a9e8e430a8b9528d54c79023690')
        values['webgallery_enabled'] = True
        self.run_play(values, tasks_override=tasks[1:])
        enabled = (self.work / 'Caddyfile').read_text()
        self.assertEqual(enabled, disabled + 'webgallery.home {\n    reverse_proxy webgallery:3000\n}\n')

    def test_additional_extractor_credential_preserves_full_desired_configuration(self):
        values = copy.deepcopy(self.values)
        values['webgallery_extractor_credentials'] = {
            'pixiv': {'refresh-token': DUMMY}, 'synthetic': {'api-key': 'dummy-future-key'}}
        self.run_play(values)
        actual = json.loads((self.data / 'scrapers/gallery-dl/gallery-dl.conf').read_text())
        self.assertEqual(actual['extractor']['synthetic'], {'api-key': 'dummy-future-key'})
        self.assertEqual(actual['postprocessor'], self.gallery['postprocessor'])
        self.assertIn('changed=0', self.run_play(values))

    def test_quadlet_generator_preserves_paths_environment_and_readonly_browser(self):
        self.run_play()
        (self.work / 'homelab.network').write_text('[Network]\nNetworkName=homelab\n')
        env = {**self.env, 'QUADLET_UNIT_DIRS': str(self.work),
               'XDG_RUNTIME_DIR': str(self.work / 'runtime')}
        (self.work / 'runtime').mkdir(mode=0o700)
        result = subprocess.run(['/usr/libexec/podman/quadlet', '--user', '--dryrun'],
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = result.stdout + result.stderr
        self.assertIn('webgallery.service', generated)
        for path, target in [(self.data, '/data:Z'),
                             (self.work / 'bulk media', '/media:Z'),
                             (self.work / 'browser profile', '/home/node/.mozilla/firefox:ro')]:
            self.assertIn(str(path) + ':' + target, generated)
        for setting in ['DATA_DIR=/data', 'MEDIA_DIR=/media', 'NODE_ENV=production',
                        '--userns keep-id', '--publish 3000:3000', '--pull never']:
            self.assertIn(setting, generated)
        self.assertNotIn(DUMMY, generated)
        command = next(line.removeprefix('ExecStart=') for line in generated.splitlines()
                       if line.startswith('ExecStart=/usr/bin/podman run '))
        argv = [re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m[1], 16)), arg)
                for arg in shlex.split(command)]
        volumes = [argv[i + 1] for i, value in enumerate(argv) if value == '-v']
        self.assertIn(str(self.data) + ':/data:Z', volumes)
        self.assertIn(str(self.work / 'browser profile') + ':/home/node/.mozilla/firefox:ro', volumes)
        self.assertIn('homepage.group=Web Services', argv)


if __name__ == '__main__':
    unittest.main()
