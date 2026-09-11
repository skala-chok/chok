"""Structured YouTube competitor-analysis scenarios."""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.core.scenario import BaseScenario


def _run(tools: Dict[str, BaseTool], name: str, **kwargs: Any) -> Any:
    tool = tools.get(name)
    return tool.invoke(kwargs) if tool else []


def _rows(value: Any) -> List[Dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _channel_id(rows: List[Dict[str, Any]]) -> str:
    return rows[0].get("channel_id", "") if rows else ""


def _video_ids(rows: List[Dict[str, Any]]) -> List[str]:
    return [row["video_id"] for row in rows if row.get("video_id")]


class VideoEvidence(BaseModel):
    video_id: str = ""
    title: str = ""
    channel_name: str = ""
    url: str = ""
    published_at: str = ""
    views: int = 0
    likes: int = 0
    comments: int = 0
    engagement_rate: float = 0.0
    daily_average_views: float = 0.0


class ChannelAnalysis(BaseModel):
    company: str
    channel_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    videos: List[VideoEvidence] = Field(default_factory=list)


class YouTubeReport(BaseModel):
    report_type: str
    period: str
    channels: List[ChannelAnalysis] = Field(default_factory=list)
    comparative_analysis: str
    disclaimers: List[str]
    summary_markdown: str


def _evidence(videos: List[Dict[str, Any]], metrics: List[Dict[str, Any]]) -> List[VideoEvidence]:
    metrics_by_id = {row.get("video_id"): row for row in metrics}
    return [VideoEvidence(**{**video, **metrics_by_id.get(video.get("video_id"), {})}) for video in videos]


def _render(report: YouTubeReport) -> str:
    lines = [f"# 🎬 {report.report_type}", f"**분석 기간**: {report.period}", "", "### 1. 공식 채널 후보 및 영상 근거"]
    for channel in report.channels:
        lines.append(f"#### {channel.company}")
        lines.append("| 제목 | URL | 조회수 | 참여율 | 일평균 조회수 |")
        lines.append("| :--- | :--- | ---: | ---: | ---: |")
        for video in channel.videos:
            lines.append(f"| {video.title or 'N/A'} | {video.url or 'N/A'} | {video.views:,} | {video.engagement_rate:.2f}% | {video.daily_average_views:,.0f} |")
    lines.extend(["", "### 2. 비교 분석", report.comparative_analysis, "", "### 3. API 제약사항 및 준수 고지"])
    lines.extend(f"{index}. {disclaimer}" for index, disclaimer in enumerate(report.disclaimers, 1))
    report.summary_markdown = "\n".join(lines)
    return f"```json\n{report.model_dump_json(indent=2)}\n```\n\n{report.summary_markdown}"


DISCLAIMERS = [
    "공식 채널 후보는 API 응답 기반이며, 브랜드 웹사이트 등으로 추가 검증이 필요합니다.",
    "조회수·좋아요·댓글·참여율·일평균 조회수는 공개 반응 지표입니다.",
    "공개 반응 지표만으로 광고비, YouTube 광고 집행 여부, 또는 광고 효율을 단정하지 않습니다.",
]


class CompetitorComparisonParams(BaseModel):
    company_a: str = Field(description="첫 번째 비교 회사명")
    company_b: str = Field(description="두 번째 비교 회사명")
    start_date: str = Field(description="분석 시작일, YYYY-MM-DD")
    end_date: str = Field(description="분석 종료일, YYYY-MM-DD")


class CompetitorComparisonScenario(BaseScenario):
    name = property(lambda self: "youtube_competitor_comparison")
    description = property(lambda self: "두 회사 공식 YouTube 채널의 광고 후보 콘텐츠 공개 반응을 동일 기간으로 비교한다.")
    parameters_schema = property(lambda self: CompetitorComparisonParams)
    required_tool_names = property(lambda self: ["find_youtube_channel", "get_channel_videos", "get_video_metrics"])

    def execute(self, params: CompetitorComparisonParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        analyses = []
        for company in (params.company_a, params.company_b):
            candidates = _rows(_run(tools, "find_youtube_channel", company_name=company))
            videos = _rows(_run(tools, "get_channel_videos", channel_id=_channel_id(candidates), published_after=f"{params.start_date}T00:00:00Z", keyword="광고"))
            metrics = _rows(_run(tools, "get_video_metrics", video_ids=_video_ids(videos)))
            analyses.append(ChannelAnalysis(company=company, channel_candidates=candidates, videos=_evidence(videos, metrics)))
        report = YouTubeReport(report_type=f"{params.company_a} vs {params.company_b} YouTube 광고 콘텐츠 비교", period=f"{params.start_date} ~ {params.end_date}", channels=analyses, comparative_analysis="동일 기간의 광고 후보 영상 공개 반응 지표를 비교했습니다. 광고비 또는 광고 효율을 뜻하지 않습니다.", disclaimers=DISCLAIMERS, summary_markdown="")
        return _render(report)


class PaidPromotionParams(BaseModel):
    keyword: str = Field(description="탐색할 제품군 키워드")
    start_date: str = Field(default_factory=lambda: str(date.today() - timedelta(days=30)), description="분석 시작일, YYYY-MM-DD")


class PaidPromotionScenario(BaseScenario):
    name = property(lambda self: "youtube_paid_promotion_discovery")
    description = property(lambda self: "유료 프로모션 포함 표시 YouTube 콘텐츠의 공개 반응을 탐색한다.")
    parameters_schema = property(lambda self: PaidPromotionParams)
    required_tool_names = property(lambda self: ["search_paid_promotion_videos", "get_video_metrics"])

    def execute(self, params: PaidPromotionParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        videos = _rows(_run(tools, "search_paid_promotion_videos", keyword=params.keyword, published_after=f"{params.start_date}T00:00:00Z"))
        metrics = _rows(_run(tools, "get_video_metrics", video_ids=_video_ids(videos)))
        report = YouTubeReport(report_type=f"{params.keyword} 유료 프로모션 포함 표시 콘텐츠", period=f"{params.start_date} ~ 현재", channels=[ChannelAnalysis(company=params.keyword, videos=_evidence(videos, metrics))], comparative_analysis="유료 프로모션 포함으로 표시된 콘텐츠의 공개 반응을 정리했습니다. YouTube 광고 집행 영상을 뜻하지 않습니다.", disclaimers=DISCLAIMERS + ["유료 프로모션 포함 표시는 업로더 고지이며 YouTube 광고 집행 여부가 아닙니다."], summary_markdown="")
        return _render(report)


class CompetitorStrategyParams(BaseModel):
    company: str = Field(description="분석할 경쟁사명")
    start_date: str = Field(default_factory=lambda: str(date.today() - timedelta(days=30)), description="분석 시작일, YYYY-MM-DD")


class CompetitorStrategyScenario(BaseScenario):
    name = property(lambda self: "youtube_competitor_strategy")
    description = property(lambda self: "경쟁사 공식 YouTube 채널의 최근 업로드에서 제품·메시지 변화를 추적한다.")
    parameters_schema = property(lambda self: CompetitorStrategyParams)
    required_tool_names = property(lambda self: ["find_youtube_channel", "get_competitor_recent_uploads", "get_video_metrics"])

    def execute(self, params: CompetitorStrategyParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        candidates = _rows(_run(tools, "find_youtube_channel", company_name=params.company))
        videos = _rows(_run(tools, "get_competitor_recent_uploads", channel_id=_channel_id(candidates), published_after=f"{params.start_date}T00:00:00Z"))
        metrics = _rows(_run(tools, "get_video_metrics", video_ids=_video_ids(videos)))
        report = YouTubeReport(report_type=f"{params.company} 최근 콘텐츠 전략", period=f"{params.start_date} ~ 현재", channels=[ChannelAnalysis(company=params.company, channel_candidates=candidates, videos=_evidence(videos, metrics))], comparative_analysis="영상 제목·설명에서 반복 제품명·주제·소구점을 해석하십시오. 높은 조회수만으로 광고 성과를 단정하지 않습니다.", disclaimers=DISCLAIMERS, summary_markdown="")
        return _render(report)
