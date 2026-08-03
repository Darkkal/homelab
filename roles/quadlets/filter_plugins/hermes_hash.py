import base64
import hashlib
import secrets

def hermes_scrypt(password):
    if not password:
        password = "admin"
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=16384,
        r=8,
        p=1,
        dklen=32,
        maxmem=0,
    )
    return f"scrypt$16384$8$1${base64.b64encode(salt).decode('ascii')}${base64.b64encode(dk).decode('ascii')}"

class FilterModule(object):
    def filters(self):
        return {
            'hermes_scrypt': hermes_scrypt
        }
