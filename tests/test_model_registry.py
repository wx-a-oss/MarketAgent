from __future__ import annotations

from market_agent.config.models import OPENAI_ANALYSIS_MODELS
from market_agent.llms.news_registry import list_news_models
from market_agent.llms.registry import list_models


def test_openai_analysis_models_include_gpt_55() -> None:
    assert "gpt-5.5" in OPENAI_ANALYSIS_MODELS
    assert "gpt-5.5" in list_news_models()["openai"]
    assert "gpt-5.5" in list_models()["openai"]
