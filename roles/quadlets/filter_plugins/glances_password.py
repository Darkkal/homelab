import hashlib

def _get_hash(plain_password, salt=''):
    """Mirror GlancesPassword.get_hash() (pbkdf2_hmac sha256, 100k iters)."""
    return hashlib.pbkdf2_hmac(
        "sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000, dklen=128
    ).hex()

def glances_pwd(password):
    """Return a Glances password-file line (salt$pbkdf2-sha256 hex).

    Mirrors GlancesPassword.get_password()/hash_password() in glances/password.py:
    the plain password is first hashed with an empty salt, then that hash is
    re-hashed with the stored salt. The salt is derived deterministically from
    the password so the rendered file is idempotent and regenerates whenever
    the vault password changes.
    """
    if not password:
        password = "glances"
    salt = hashlib.sha256(("glances-salt:" + password).encode("utf-8")).hexdigest()
    password_hash = _get_hash(password)
    encrypted = _get_hash(password_hash, salt=salt)
    return salt + "$" + encrypted

class FilterModule(object):
    def filters(self):
        return {
            'glances_pwd': glances_pwd
        }
