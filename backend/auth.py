"""Password hashing and random session credentials; no plaintext password storage."""
import hashlib
import hmac
import secrets

ITERATIONS = 600_000
DEMO_PASSWORD = 'LocalDealDemo!2026'


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password, encoded):
    if not isinstance(password, str) or not isinstance(encoded, str):
        return False
    try:
        algorithm, iterations, salt, stored = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or int(iterations) != ITERATIONS:
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(digest.hex(), stored)
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def new_session_credentials():
    return secrets.token_urlsafe(32), secrets.token_hex(32)


# Unknown accounts perform the same password derivation as known accounts.
DUMMY_HASH = hash_password('not-a-user-password-' + secrets.token_hex(16))
