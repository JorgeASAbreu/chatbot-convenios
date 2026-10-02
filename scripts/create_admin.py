#!/usr/bin/env python3
import argparse

from sqlalchemy import select

from app.db.models import Usuario
from app.db.session import SessionLocal
from app.services.auth import AuthService

p = argparse.ArgumentParser()
p.add_argument("--login", default="admin")
p.add_argument("--nome", default="Administrador")
p.add_argument("--password", required=True)
a = p.parse_args()
with SessionLocal() as db:
    if db.scalar(select(Usuario).where(Usuario.login == a.login)):
        raise SystemExit("Usuário já existe")
    AuthService(db).create_user(a.login, a.nome, a.password, "ADMIN")
print("Administrador criado.")
