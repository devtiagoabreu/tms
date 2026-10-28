"""Configuração comum dos testes.

Os testes de API usam ``TestClient`` sobre um banco SQLite isolado, passado via
``app.dependency_overrides[get_db]``. O middleware de autenticação, porém, roda
antes das dependências e usa a sessão global — por isso ele é substituído aqui
por um usuário de teste fixo.
"""

from types import SimpleNamespace

import pytest

from tms.app import main as app_main
from tms.models.auth import UserRole


@pytest.fixture(autouse=True)
def authenticated(monkeypatch):
    """Autentica todas as requisições dos testes como administrador."""
    fake_user = SimpleNamespace(
        id=1,
        email="test@tms.local",
        username="test",
        full_name="Usuário de teste",
        role=UserRole.admin,
        is_active=True,
    )
    monkeypatch.setattr(app_main, "_resolve_user", lambda token: fake_user)
    return fake_user
