import hashlib
import secrets
from typing import Tuple


SALT_SIZE = 16
ITERATIONS = 100_000
ALGORITHM = "sha256"


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(ALGORITHM, password.encode("utf-8"), salt, ITERATIONS)


def create_password_hash(password: str) -> str:
    salt = secrets.token_bytes(SALT_SIZE)
    hashed = _hash_password(password, salt)
    return f"{salt.hex()}${hashed.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, hash_hex = stored_hash.split("$")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(hash_hex)
    candidate = _hash_password(password, salt)
    return secrets.compare_digest(candidate, expected)
