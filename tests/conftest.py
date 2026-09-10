import pytest
from unittest.mock import MagicMock
from langchain_core.language_models.chat_models import BaseChatModel


@pytest.fixture
def mock_llm():
    """Mock ChatOpenAI instance for unit testing without API keys."""
    llm = MagicMock(spec=BaseChatModel)
    return llm
