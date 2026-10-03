"""Password hashing and opaque bearer-token helpers for identity workflows."""

import base64
import hashlib
import hmac
import secrets


_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_KEY_LENGTH = 64


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_KEY_LENGTH,
    )
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${encode(salt)}${encode(digest)}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if stored_hash is None:
        return False
    try:
        algorithm, n_text, r_text, p_text, salt_text, expected_text = stored_hash.split("$", 5)
        n, r, p = int(n_text), int(r_text), int(p_text)
        if algorithm != "scrypt" or n != _SCRYPT_N or r != _SCRYPT_R or p != _SCRYPT_P:
            return False
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        salt, expected = decode(salt_text), decode(expected_text)
        if len(salt) != 16 or len(expected) != _SCRYPT_KEY_LENGTH:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, OverflowError):
        return False


def create_bearer_token() -> str:
    return secrets.token_urlsafe(32)


def hash_bearer_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
