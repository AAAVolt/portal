"""Genera hashes de contraseña y el secreto compartido del portal.

    python tools/hash_password.py --secret          # SSO_SECRET nuevo
    python tools/hash_password.py "micontraseña"    # hash para [users.x]
"""

import hashlib
import os
import sys


def scrypt_hash(plain: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(plain.encode(), salt=salt, n=16384, r=8, p=1).hex()
    return f"scrypt${salt.hex()}${digest}"


def main(argv: list) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    if argv[1] == "--secret":
        print(os.urandom(32).hex())
        return 0
    print(scrypt_hash(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
