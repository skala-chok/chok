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
    assert "유료 프로모션 장단점 비교" in result
    assert "기대 장점" in result
    assert "리스크·검증 조건" in result
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


def _video_tool(rows: list) -> MagicMock:
    tool = MagicMock()
    tool.invoke.return_value = rows
    return tool


VIDEO_ROWS = [
    {"video_id": "v1", "title": "신형 러닝화 공개 | 가벼움", "description": "러닝화의 성능을 확인하세요",
     "channel_name": "A사 Official", "published_at": "2026-08-03T09:00:00Z",
     "url": "https://www.youtube.com/watch?v=v1"},
    {"video_id": "v2", "title": "[광고] 러닝화 내구성 테스트", "description": "러닝화가 얼마나 버티는가",
     "channel_name": "A사 Official", "published_at": "2026-08-18T09:00:00Z",
     "url": "https://www.youtube.com/watch?v=v2"},
]
METRIC_ROWS = [
    {"video_id": "v1", "title": "신형 러닝화 공개 | 가벼움", "published_at": "2026-08-03T09:00:00Z",
     "duration": "PT45S", "views": 120000, "likes": 3400, "comments": 210,
     "engagement_rate": 3.008, "daily_views": 4000.0, "url": "https://www.youtube.com/watch?v=v1"},
    {"video_id": "v2", "title": "[광고] 러닝화 내구성 테스트", "published_at": "2026-08-18T09:00:00Z",
     "duration": "PT8M12S", "views": 54000, "likes": 1200, "comments": 90,
     "engagement_rate": 2.389, "daily_views": 1800.0, "url": "https://www.youtube.com/watch?v=v2"},
]


def _strategy_report() -> str:
    scenario = CompetitorStrategyScenario()
    tools = {
        "find_youtube_channel": _video_tool([{"channel_id": "UC1", "channel_name": "A사 Official", "url": "https://youtube.com/@a"}]),
        "get_channel_details": _video_tool({"channel_name": "A사 Official", "channel_url": "https://youtube.com/@a"}),
        "get_competitor_recent_uploads": _video_tool(VIDEO_ROWS),
        "get_video_metrics": _video_tool(METRIC_ROWS),
    }
    return scenario.execute(CompetitorStrategyParams(company="A사", start_date="2026-08-01"), tools)


def test_report_escapes_table_separators_and_link_brackets():
    """제목의 `|`와 `[]`가 Markdown 표/링크 문법을 깨지 않아야 합니다."""
    body = _strategy_report().split("\n```\n", 1)[1]
    assert "신형 러닝화 공개 \\| 가벼움" in body
    assert "\\[광고\\] 러닝화 내구성 테스트" in body
    for line in body.splitlines():
        if line.startswith("|") and not line.startswith("| :") and not line.startswith("| ---"):
            assert line.count("|") - line.count("\\|") >= 2


def test_report_exposes_time_axis_and_localized_labels():
    """트렌드 판독용 시계열·게시일 축과 한국어 라벨이 노출되어야 합니다."""
    body = _strategy_report().split("\n```\n", 1)[1]
    assert "기간 내 반응 추이" in body
    assert "콘텐츠 형식별 성과" in body
    assert "게시일" in body and "08-18" in body
    assert "브랜드 채널" in body
    for leaked in ("insufficient data", "recent response stronger", "possible fatigue", "'brand'"):
        assert leaked not in body


def test_report_handles_empty_sample_without_crashing():
    """표본이 없어도 렌더링이 실패하지 않고 안내 문구를 남겨야 합니다."""
    scenario = CompetitorStrategyScenario()
    empty = _video_tool([])
    result = scenario.execute(
        CompetitorStrategyParams(company="A사", start_date="2026-08-01"),
        {"find_youtube_channel": empty, "get_competitor_recent_uploads": empty, "get_video_metrics": empty},
    )
    assert "분석 가능한 공개 영상 표본이 없습니다" in result
