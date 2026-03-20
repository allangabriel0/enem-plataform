"""
utils/logging.py — Configuração centralizada de logging para a plataforma ENEM.

Configura o logger raiz "enem" com:
  - RotatingFileHandler em logs/app.log (5 MB × 3 backups)
  - StreamHandler para console
  - Formato padronizado com timestamp, nível, nome do logger e mensagem
"""
import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "app.log"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configura e retorna o logger "enem".

    Idempotente: se o logger já tiver handlers configurados, retorna sem
    adicionar duplicatas (evita dupla escrita em reload do uvicorn --reload).
    """
    logger = logging.getLogger("enem")

    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Garante que o diretório de logs existe
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Handler de arquivo com rotação
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Handler de console
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    # Evita propagação para o logger raiz do Python (evita log duplicado)
    logger.propagate = False

    return logger
