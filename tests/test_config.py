import pytest
from src.config import Settings, settings

def test_settings_default_values():
    test_settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="test-openai-key",
        YOUTUBE_API_KEY="test-yt-key",
        NAVER_CLIENT_ID="test-naver-id",
        NAVER_CLIENT_SECRET="test-naver-secret"
    )
    assert test_settings.OPENAI_API_KEY == "test-openai-key"
    assert test_settings.MODEL_NAME == "gpt-5.6-luna"
    assert test_settings.TEMPERATURE == 0.0
    assert test_settings.YOUTUBE_API_KEY == "test-yt-key"
    assert test_settings.NAVER_CLIENT_ID == "test-naver-id"
    assert test_settings.NAVER_CLIENT_SECRET == "test-naver-secret"

def test_settings_singleton():
    assert isinstance(settings, Settings)
    assert bool(settings.MODEL_NAME)
