"""
Prompt for a password and print the GOLDRYN_PASSWORD_HASH line for .env.

    .venv/Scripts/python backend/hash_password.py
"""

import sys
from getpass import getpass

import bcrypt

from auth import BCRYPT_MAX_BYTES


def main() -> int:
    password = getpass("Password: ")
    if not password:
        print("Password can't be empty.", file=sys.stderr)
        return 1
    if len(password.encode()) > BCRYPT_MAX_BYTES:
        print(f"Password can't be longer than {BCRYPT_MAX_BYTES} bytes (bcrypt's limit).", file=sys.stderr)
        return 1
    if getpass("Confirm:  ") != password:
        print("Passwords don't match.", file=sys.stderr)
        return 1

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    # Single quotes keep the "$"s in the hash from being read as variables.
    print(f"GOLDRYN_PASSWORD_HASH='{password_hash}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
