"""Cria usuário administrador inicial."""
from __future__ import annotations

import sys

from sqlalchemy import select

from tms.core.auth import hash_password
from tms.db.base import SessionLocal, engine
from tms.models import Base
from tms.models.auth import User, UserRole


def main() -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        exists = db.execute(select(User).where(User.email == "admin@tms.local")).scalar_one_or_none()
        if exists:
            print("Já existe usuário admin@tms.local")
            return 0
        user = User(
            email="admin@tms.local",
            username="admin",
            full_name="Administrador",
            password_hash=hash_password("admin"),
            role=UserRole.admin,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print("Criado com sucesso: admin@tms.local / admin")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
