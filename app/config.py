import logging
from typing import Any, List, Tuple, Type

from pydantic import field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

logger = logging.getLogger("enem")


def _parse_group_ids(value: Any) -> List[int]:
    """Parse TELEGRAM_GROUP_IDS de string CSV ou lista para List[int]."""
    if isinstance(value, list):
        return [int(x) for x in value if str(x).strip()]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        return [int(x.strip()) for x in value.split(",") if x.strip()]
    return []


class _CommaListEnvSource(EnvSettingsSource):
    """EnvSettingsSource que trata TELEGRAM_GROUP_IDS como CSV antes do JSON decode."""

    def prepare_field_value(self, field_name: str, field: Any, value: Any, value_is_complex: bool) -> Any:
        if field_name == "TELEGRAM_GROUP_IDS" and isinstance(value, str):
            return _parse_group_ids(value)
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class _CommaListDotEnvSource(DotEnvSettingsSource):
    """DotEnvSettingsSource que trata TELEGRAM_GROUP_IDS como CSV antes do JSON decode."""

    def prepare_field_value(self, field_name: str, field: Any, value: Any, value_is_complex: bool) -> Any:
        if field_name == "TELEGRAM_GROUP_IDS" and isinstance(value, str):
            return _parse_group_ids(value)
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "ENEM Studies"
    SECRET_KEY: str = "dev-secret-key-troque-em-producao"

    # Database
    DATABASE_URL: str = "sqlite:///./data/enem.db"

    # Cache
    CACHE_DIR: str = "data/cache"
    CACHE_MAX_GB: int = 50
    SD_CARD_PATH: str = ""

    # Telegram
    TELEGRAM_API_ID: int = 0
    TELEGRAM_API_HASH: str = ""
    TELEGRAM_PHONE: str = ""
    TELEGRAM_GROUP_IDS: List[int] = []
    TELEGRAM_FETCH_LIMIT: int = 3000

    # Menus
    MENU_FILE: str = "data/menus/raw_menus.txt"

    # Usuários iniciais
    USER1_NAME: str = "Maria"
    USER1_EMAIL: str = "maria@email.com"
    USER1_PASSWORD: str = ""
    USER2_NAME: str = "João"
    USER2_EMAIL: str = "joao@email.com"
    USER2_PASSWORD: str = ""

    @field_validator("TELEGRAM_GROUP_IDS", mode="before")
    @classmethod
    def parse_group_ids(cls, v: Any) -> List[int]:
        """Converte string CSV ou lista em List[int]. Usado para init kwargs."""
        return _parse_group_ids(v)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _CommaListEnvSource(settings_cls),
            _CommaListDotEnvSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()