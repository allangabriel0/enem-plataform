from pydantic_settings import SettingsConfigDict


def _isolated_settings(monkeypatch, **env_vars):
    """Cria instância de Settings isolada: sem .env, sem env vars residuais."""
    from app.config import Settings

    # Limpa env vars do Settings para evitar interferência do ambiente do dev
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name, raising=False)

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    class IsolatedSettings(Settings):
        model_config = SettingsConfigDict(env_file=None, extra="ignore")

    return IsolatedSettings()


def test_settings_loads_with_defaults(monkeypatch):
    """Settings carrega sem .env usando valores padrão."""
    s = _isolated_settings(monkeypatch)

    assert s.APP_NAME == "ENEM Studies"
    assert s.DATABASE_URL == "sqlite:///./data/enem.db"
    assert s.CACHE_MAX_GB == 50
    assert s.TELEGRAM_FETCH_LIMIT == 3000
    assert s.TELEGRAM_GROUP_IDS == []
    assert s.SD_CARD_PATH == ""


def test_telegram_group_ids_parse_csv(monkeypatch):
    """TELEGRAM_GROUP_IDS parseia '123,456' para [123, 456]."""
    s = _isolated_settings(monkeypatch, TELEGRAM_GROUP_IDS="123,456")
    assert s.TELEGRAM_GROUP_IDS == [123, 456]


def test_telegram_group_ids_empty(monkeypatch):
    """TELEGRAM_GROUP_IDS vazio retorna []."""
    s = _isolated_settings(monkeypatch, TELEGRAM_GROUP_IDS="")
    assert s.TELEGRAM_GROUP_IDS == []
