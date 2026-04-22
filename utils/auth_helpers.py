"""
Authentication helper utilities for RailOps.
Optional utilities for password hashing and validation.

These functions are NOT used by default - they are available
if you want to add password hashing support later.
"""


def is_password_hashed(password_value: str) -> bool:
    """
    Detect if a password string is hashed or plain text.

    Hashed passwords have specific patterns:
    - werkzeug format: starts with 'pbkdf2:sha256$' or similar
    - scrypt format: starts with 'scrypt$'
    - bcrypt format: starts with 'bcrypt$'

    Returns True if the password appears to be hashed.
    """
    if not isinstance(password_value, str):
        return False

    hash_patterns = ['pbkdf2:', 'scrypt$', 'bcrypt$', 'argon2']
    return any(password_value.startswith(pattern) for pattern in hash_patterns)


def verify_password_flexible(stored_password: str, provided_password: str) -> bool:
    """
    Verify a password against stored value.

    Supports both plain-text passwords (current system)
    and hashed passwords (optional future use).
    """
    if not stored_password or not provided_password:
        return False

    if is_password_hashed(stored_password):
        try:
            from werkzeug.security import check_password_hash
            return check_password_hash(stored_password, provided_password)
        except ImportError:
            pass
        except Exception:
            pass

    return stored_password == provided_password