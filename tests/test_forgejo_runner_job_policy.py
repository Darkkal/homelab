"""Controller-only policy tests; generated certificates, no operator material."""
import datetime
import importlib.util
import pathlib
import unittest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('policy', ROOT / 'roles/forgejo_runner/filter_plugins/job_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
IMAGE = 'example.invalid/node@sha256:' + 'a' * 64


def certificate(ca=True, expired=False):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'synthetic')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=2))
            .not_valid_after(now + datetime.timedelta(days=-1 if expired else 2))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode(), cert.fingerprint(hashes.SHA256()).hex()


class PolicyTests(unittest.TestCase):
    def setUp(self):
        import hashlib
        root, fingerprint = certificate()
        base, _ = certificate()
        self.value = dict(enabled=True, hostname='synthetic.invalid', job_image=IMAGE,
                          ca_certificate=root, ca_sha256=fingerprint, base_bundle=base,
                          base_bundle_sha256=hashlib.sha256(base.encode()).hexdigest())

    def render(self, value):
        return policy.job_policy(value, IMAGE, '/tmp/runner data', ['ubuntu-latest:docker://' + IMAGE])

    def test_absent_and_disabled_are_inert(self):
        for value in [{}, {'enabled': False}]:
            self.assertEqual(self.render(value), {'enabled': False})

    def test_valid_preserves_original_roots_and_generates_safe_options(self):
        import shlex
        result = self.render(self.value)
        self.assertNotIn('GIT_SSL_NO_VERIFY', result['env'])
        self.assertTrue(result['bundle'].startswith(self.value['base_bundle']))
        self.assertIn(self.value['ca_certificate'], result['bundle'])
        self.assertEqual(shlex.split(result['options']), ['--add-host', 'synthetic.invalid:host-gateway', '--volume', '/tmp/runner data/job-ca-bundle.pem:/opt/homelab/job-ca-bundle.pem:ro,z'])
        self.assertEqual(result['env']['GIT_SSL_CAINFO'], '/opt/homelab/job-ca-bundle.pem')

    def test_missing_malformed_conflicting_policy_fails_without_echoing_values(self):
        for value in [None, [], 'SYNTHETIC_SECRET', {'enabled': 'true'}, {'enabled': 0}, {'enabled': 0.0},
                      {'enabled': False, 'hostname': 'synthetic.invalid'},
                      {**self.value, 'extra': 'SYNTHETIC_SECRET'},
                      {**self.value, 'hostname': 'bad --env=SYNTHETIC_SECRET'},
                      {**self.value, 'hostname': '127.0.0.1'},
                      {**self.value, 'ca_sha256': 'b' * 64},
                      {**self.value, 'base_bundle_sha256': 'b' * 64},
                      {**self.value, 'job_image': 'mutable:latest'},
                      {k: v for k, v in self.value.items() if k != 'ca_certificate'}]:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(Exception, '^Invalid runner job policy$'):
                    self.render(value)

    def test_rejects_non_ca_expired_or_non_certificate_input(self):
        for ca, expired in [(False, False), (True, True)]:
            pem, fingerprint = certificate(ca, expired)
            with self.assertRaises(Exception):
                self.render({**self.value, 'ca_certificate': pem, 'ca_sha256': fingerprint})
        for field in ['ca_certificate', 'base_bundle']:
            for text in ['not a certificate', self.value[field] + '\nPRIVATE KEY\n']:
                with self.assertRaises(Exception):
                    self.render({**self.value, field: text})

    def test_rejects_image_label_conflict_and_unsafe_mount_path(self):
        for image, directory, labels in [(IMAGE, '/tmp/x:bad', ['ubuntu-latest:docker://' + IMAGE]),
                                         (IMAGE, '/tmp/x', ['other:docker://mutable']),
                                         ('mutable', '/tmp/x', ['ubuntu-latest:docker://' + IMAGE])]:
            with self.assertRaises(Exception):
                policy.job_policy(self.value, image, directory, labels)

if __name__ == '__main__':
    unittest.main()
