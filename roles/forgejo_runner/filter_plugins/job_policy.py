"""Validate the configured opt-in; never include input values in errors."""
import datetime
import hashlib
import ipaddress
import re
import shlex

from ansible.errors import AnsibleFilterError
from cryptography import x509
from cryptography.hazmat.primitives import hashes

BUNDLE_PATH = '/opt/homelab/job-ca-bundle.pem'
CERTIFICATE = re.compile(r'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]+-----END CERTIFICATE-----')
FIELDS = {'enabled', 'hostname', 'job_image', 'ca_certificate', 'ca_sha256',
          'base_bundle', 'base_bundle_sha256'}


def certificates(pem):
    if not isinstance(pem, str) or not 0 < len(pem) <= 1048576:
        raise ValueError()
    blocks = CERTIFICATE.findall(pem)
    if not blocks or CERTIFICATE.sub('', pem).strip():
        raise ValueError()
    return [x509.load_pem_x509_certificate(block.encode('ascii')) for block in blocks]


def job_policy(value, job_image, data_dir, labels):
    """An empty policy is inert. Partial policies never enable route-only fixes."""
    try:
        if not isinstance(value, dict):
            raise ValueError()
        if not value or (set(value) == {'enabled'} and value['enabled'] is False):
            return {'enabled': False}
        if set(value) != FIELDS or value['enabled'] is not True:
            raise ValueError()
        if not all(isinstance(value[k], str) for k in FIELDS - {'enabled'}):
            raise ValueError()
        hostname = value['hostname']
        if len(hostname) > 253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', hostname):
            raise ValueError()
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise ValueError()
        if value['job_image'] != job_image or not re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}', job_image):
            raise ValueError()
        if labels != ['ubuntu-latest:docker://' + job_image]:
            raise ValueError()
        if not isinstance(data_dir, str) or not data_dir.startswith('/') or any(c in data_dir for c in ':\n\r\x00*?[]{}\\') or '..' in data_dir.split('/'):
            raise ValueError()
        for key in ['ca_sha256', 'base_bundle_sha256']:
            if not re.fullmatch(r'[0-9a-f]{64}', value[key]):
                raise ValueError()
        root, = certificates(value['ca_certificate'])
        if root.fingerprint(hashes.SHA256()).hex() != value['ca_sha256']:
            raise ValueError()
        if not root.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError()
        now = datetime.datetime.now(datetime.timezone.utc)
        if not root.not_valid_before_utc <= now < root.not_valid_after_utc:
            raise ValueError()
        # Keep even expired original roots: this mechanism must not edit image trust.
        certificates(value['base_bundle'])
        if hashlib.sha256(value['base_bundle'].encode()).hexdigest() != value['base_bundle_sha256']:
            raise ValueError()
        bundle = value['base_bundle'] + '\n' + value['ca_certificate']
        source = data_dir.rstrip('/') + '/job-ca-bundle.pem'
        options = shlex.join(['--add-host', hostname + ':host-gateway',
                             '--volume', source + ':' + BUNDLE_PATH + ':ro,z'])
        return {'enabled': True, 'bundle': bundle, 'options': options,
                'env': {'GIT_SSL_CAINFO': BUNDLE_PATH, 'GIT_SSL_CAPATH': '',
                        'SSL_CERT_FILE': BUNDLE_PATH,
                        'CURL_CA_BUNDLE': BUNDLE_PATH}}
    except Exception:
        raise AnsibleFilterError('Invalid runner job policy') from None


class FilterModule:
    def filters(self):
        return {'forgejo_runner_job_policy': job_policy}
