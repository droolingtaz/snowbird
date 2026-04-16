from datetime import datetime, timedelta, timezone
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from cryptography.fernet import Fernet
import base64
import hashlib

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt only hashes the first 72 bytes of a password. bcrypt>=4 raises
# when passed longer input instead of silently truncating, so we truncate
# explicitly at the byte level before hashing or verifying.
_BCRYPT_MAX_BYTES = 72


def _bcrypt_safe(password: str) -> str:
    encoded = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return encoded.decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    return pwd_context.hash(_bcrypt_safe(password))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_bcrypt_safe(plain), hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def _get_fernet() -> Fernet:
    """Derive a 32-byte Fernet key from SECRET_KEY."""
    raw = settings.SECRET_KEY.encode()
    key_bytes = hashlib.sha256(raw).digest()
    key_b64 = base64.urlsafe_b64encode(key_bytes)
    return Fernet(key_b64)


def encrypt_secret(plaintext: str) -> str:
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
