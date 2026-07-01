from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, driven by environment variables.

    DATABASE_URL accepts postgresql+asyncpg:// or sqlite+aiosqlite://
    for test convenience, though production uses Postgres.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/youtube_topk"
    APP_PORT: int = 8000
