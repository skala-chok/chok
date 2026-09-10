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
    MODEL_NAME: str = "gpt-5-luna"
    TEMPERATURE: float = 0.0

    # YouTube API (Worker 1, 2)
    YOUTUBE_API_KEY: Optional[str] = None

    # Naver API (Worker 3, 4)
    NAVER_CLIENT_ID: Optional[str] = None
    NAVER_CLIENT_SECRET: Optional[str] = None

    # Instagram Graph API
    INSTAGRAM_ACCESS_TOKEN: Optional[str] = None
    INSTAGRAM_USER_ID: Optional[str] = None
    INSTAGRAM_API_VERSION: str = "v26.0"

settings = Settings()
