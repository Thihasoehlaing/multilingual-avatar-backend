from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional

# default key = client IP. We'll override per-user where we can.
limiter = Limiter(key_func=get_remote_address)

def user_key(user_id: Optional[str]):
    return user_id if user_id else get_remote_address
