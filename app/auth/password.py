from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash for storage."""
    return _pwd.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plain password against its stored bcrypt hash."""
    return _pwd.verify(plain_password, hashed_password)
