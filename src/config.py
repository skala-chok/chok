from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core LLM
    OPENAI_API_KEY: Optional[str] = None
    MODEL_NAME: str = "gpt-4o-mini"
    TEMPERATURE: float = 0.0

    # YouTube API (Worker 1, 2)
    YOUTUBE_API_KEY: Optional[str] = None

    # Naver API (Worker 3, 4)
    NAVER_CLIENT_ID: Optional[str] = None
    NAVER_CLIENT_SECRET: Optional[str] = None

settings = Settings()
