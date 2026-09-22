from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./content_engine.db"
    output_dir: Path = Path("./output")
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    ffmpeg_binary: str = "ffmpeg"
    allow_demo_fallback: bool = True
    engine_api_token: str | None = None
    public_engine_url: str = ""
    studio_url: str = ""
    token_encryption_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    instagram_client_id: str = ""
    instagram_client_secret: str = ""
    instagram_api_version: str = "v25.0"
    publishing_worker_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
