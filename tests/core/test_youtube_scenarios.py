from unittest.mock import MagicMock

from src.core.scenario_registry import ScenarioRegistry
from src.scenarios.youtube_competitor_analysis.scenario import (
    CompetitorComparisonParams, CompetitorComparisonScenario, CompetitorStrategyParams,
    CompetitorStrategyScenario, PaidPromotionParams, PaidPromotionScenario,
)


def _tool(result: str) -> MagicMock:
    tool = MagicMock()
    tool.invoke.return_value = result
    return tool


def test_competitor_comparison_calls_tools_twice_per_company():
    scenario = CompetitorComparisonScenario()
    channels = _tool("채널ID: UC1")
    videos = _tool("URL: https://www.youtube.com/watch?v=v1")
    metrics = _tool("참여율: 2.00% | 일평균 조회수: 10")
    result = scenario.execute(CompetitorComparisonParams(company_a="A사", company_b="B사", start_date="2026-01-01", end_date="2026-04-01"), {"find_youtube_channel": channels, "get_channel_videos": videos, "get_video_metrics": metrics})
    assert channels.invoke.call_count == videos.invoke.call_count == metrics.invoke.call_count == 2
    assert "광고비 또는 광고 효율을 뜻하지 않습니다" in result


def test_paid_promotion_marks_scope_and_calls_metrics_once():
    scenario = PaidPromotionScenario()
    videos, metrics = _tool("URL: https://www.youtube.com/watch?v=v1"), _tool("조회수: 10")
    result = scenario.execute(PaidPromotionParams(keyword="무선이어폰", start_date="2026-01-01"), {"search_paid_promotion_videos": videos, "get_video_metrics": metrics})
    assert videos.invoke.call_count == metrics.invoke.call_count == 1
    assert "YouTube 광고 집행 영상" in result


def test_competitor_strategy_calls_expected_tools_and_is_discovered():
    scenario = CompetitorStrategyScenario()
    channels, videos, metrics = _tool("채널ID: UC1"), _tool("URL: https://www.youtube.com/watch?v=v1"), _tool("참여율: 1%")
    result = scenario.execute(CompetitorStrategyParams(company="A사", start_date="2026-01-01"), {"find_youtube_channel": channels, "get_competitor_recent_uploads": videos, "get_video_metrics": metrics})
    assert channels.invoke.call_count == videos.invoke.call_count == metrics.invoke.call_count == 1
    assert "광고 성과를 단정하지 않습니다" in result
    registry = ScenarioRegistry()
    registry.discover_scenarios()
    assert {"youtube_competitor_comparison", "youtube_paid_promotion_discovery", "youtube_competitor_strategy"} <= set(item.name for item in registry.get_all_scenarios())
