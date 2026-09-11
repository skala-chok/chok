from typing import Optional, Tuple, Type
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)

    # 핵심 LLM 설정
    OPENAI_API_KEY: Optional[str] = None
    MODEL_NAME: str = "gpt-5.6-luna"
    TEMPERATURE: float = 0.0

    # YouTube API 설정 (워커 1, 2)
    YOUTUBE_API_KEY: Optional[str] = None

    # 네이버 Cloud API Hub 설정 (워커 3, 4)
    NAVER_CLIENT_ID: Optional[str] = None
    NAVER_CLIENT_SECRET: Optional[str] = None

    # 인스타그램 Graph API 설정 (워커 5)
    INSTAGRAM_ACCESS_TOKEN: Optional[str] = None
    INSTAGRAM_USER_ID: Optional[str] = None
    INSTAGRAM_API_VERSION: str = "v26.0"

settings = Settings()
