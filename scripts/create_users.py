"""
scripts/create_users.py — Cria ou atualiza os usuários definidos no .env.

Uso:
  python scripts/create_users.py
"""
import sys
from pathlib import Path

# Garante que o projeto está no sys.path ao rodar como script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password as get_password_hash
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import User


def _upsert_user(db, name: str, email: str, password: str) -> tuple[User, bool]:
    """Cria ou atualiza usuário. Retorna (user, created)."""
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.name = name
        user.hashed_password = get_password_hash(password)
        db.commit()
        db.refresh(user)
        return user, False
    user = User(name=name, email=email, hashed_password=get_password_hash(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, True


def main() -> None:
    init_db()
    db = SessionLocal()

    users_cfg = [
        (settings.USER1_NAME, settings.USER1_EMAIL, settings.USER1_PASSWORD),
        (settings.USER2_NAME, settings.USER2_EMAIL, settings.USER2_PASSWORD),
    ]

    created = updated = skipped = 0

    try:
        for name, email, password in users_cfg:
            if not email or not password:
                print(f"  [!] Pulando usuário '{name}' — email ou senha vazia no .env")
                skipped += 1
                continue

            user, is_new = _upsert_user(db, name, email, password)
            status = "criado" if is_new else "atualizado"
            print(f"  [{'+'  if is_new else '~'}] {name} <{email}> — {status} (id={user.id})")
            if is_new:
                created += 1
            else:
                updated += 1

    finally:
        db.close()

    print()
    print(f"  Resultado: {created} criado(s), {updated} atualizado(s), {skipped} pulado(s)")


if __name__ == "__main__":
    main()
