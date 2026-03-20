import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

logger = logging.getLogger("enem")

# passlib 1.7.4 + bcrypt >= 4.0.0: detect_wrap_bug chama bcrypt.hashpw com 256
# bytes; bcrypt 4.0+ rejeita isso com ValueError. Patchamos bcrypt.hashpw para
# truncar silenciosamente em 72 bytes (comportamento pré-4.0, semanticamente correto).
try:
    import bcrypt as _bcrypt_module
    _orig_hashpw = _bcrypt_module.hashpw

    def _hashpw_compat(password: bytes, salt: bytes) -> bytes:
        if isinstance(password, str):
            password = password.encode("utf-8")
        return _orig_hashpw(password[:72], salt)

    _bcrypt_module.hashpw = _hashpw_compat  # type: ignore[attr-defined]
except Exception:
    pass

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class RequiresLoginException(Exception):
    """Levantada quando o usuário não está autenticado. Tratada via exception_handler."""
    pass


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")
    if not token:
        logger.debug("Token ausente — redirecionando para /login")
        raise RequiresLoginException()

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub", "")
        if not email:
            raise JWTError("campo sub ausente")
    except JWTError as exc:
        logger.warning("Token inválido: %s", exc)
        raise RequiresLoginException() from exc

    user = db.query(User).filter(User.email == email).first()
    if not user:
        logger.warning("Usuário do token não encontrado: %s", email)
        raise RequiresLoginException()

    return user
