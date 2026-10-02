from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.models import Usuario


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, login: str, password: str) -> Usuario | None:
        user = self.db.scalar(select(Usuario).where(Usuario.login == login))
        return (
            user if user and user.ativo and verify_password(password, user.password_hash) else None
        )

    def create_user(self, login: str, nome: str, password: str, perfil: str = "ADMIN") -> Usuario:
        user = Usuario(login=login, nome=nome, password_hash=hash_password(password), perfil=perfil)
        self.db.add(user)
        self.db.commit()
        return user
