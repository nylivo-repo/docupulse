"""
Encryption for secrets kept in the database (Okta client secret, directory bind password), so a
database backup or a DBA's query does not reveal them. Fernet (AES-128-CBC + HMAC-SHA256).

The key comes from [security] secret_key / IDP_SECRET_KEY, or from secret_key_file, which is created
on first start with owner-only permissions. Losing the key means re-entering those two secrets.
"""
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

PREFIX = "enc:v1:"
log = logging.getLogger("idp.secrets")
_fernet: Optional[Fernet] = None


def _box() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.SECRET_KEY
        if not key:
            path = settings.SECRET_KEY_FILE
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(Fernet.generate_key().decode())
                log.warning("Created the secrets encryption key %s (back it up securely)", path)
            with open(path) as f:
                key = f.read().strip()
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt(value: str) -> str:
    if not value or value.startswith(PREFIX):
        return value
    return PREFIX + _box().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value or not value.startswith(PREFIX):
        return value  # stored before encryption was added; encrypted at the next save
    try:
        return _box().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        log.error("A stored secret could not be decrypted (wrong or replaced secret key); re-enter it in Admin Settings")
        return ""
