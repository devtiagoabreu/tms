"""Utilitários de autenticação."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SECRET_KEY = os.getenv("TMS_SECRET_KEY", "tms-dev-secret-change-me")
SESSION_SALT = "tms-session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 8

serializer = URLSafeTimedSerializer(SECRET_KEY, salt=SESSION_SALT)

try:
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception:
            return False
except Exception:
    import bcrypt

    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False


def create_session_token(user_id: int) -> str:
    payload = {"uid": user_id, "iat": datetime.utcnow().timestamp()}
    return serializer.dumps(payload)


def verify_session_token(token: str, max_age: int = SESSION_MAX_AGE_SECONDS) -> Optional[int]:
    try:
        data: dict[str, Any] = serializer.loads(token, max_age=max_age)
        uid = data.get("uid")
        if uid is None:
            return None
        return int(uid)
    except (BadSignature, SignatureExpired):
        return None
    except Exception:
        return None
