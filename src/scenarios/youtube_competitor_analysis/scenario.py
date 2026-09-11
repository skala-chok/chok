"""Structured YouTube competitor-analysis scenarios."""

import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from statistics import median
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


def _select_channel(candidates: List[Dict[str, Any]], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Select one likely official candidate; selection is not ownership proof."""
    if not candidates:
        return {}
    llm = (context or {}).get("llm")
    if not llm:
        return candidates[0]
    candidate_text = "\n".join(
        f"id={item.get('channel_id')} name={item.get('channel_name')} description={item.get('description')}"
        for item in candidates
    )
    try:
        response = llm.invoke(
            "Select the single most likely official YouTube channel candidate. "
            "Return only the exact id; do not claim verification.\n" + candidate_text
        )
        selected_id = str(getattr(response, "content", response)).strip()
        return next((item for item in candidates if item.get("channel_id") == selected_id), candidates[0])
    except Exception:
        return candidates[0]


def _video_ids(rows: List[Dict[str, Any]]) -> List[str]:
    return [row["video_id"] for row in rows if row.get("video_id")]


class VideoEvidence(BaseModel):
    video_id: str = ""
    title: str = ""
    channel_name: str = ""
    url: str = ""
    published_at: str = ""
    duration: str = ""
    content_format: str = "unknown"
    views: int = 0
    likes: int = 0
    comments: int = 0
    engagement_rate: float = 0.0
    daily_average_views: float = 0.0


class ChannelAnalysis(BaseModel):
    company: str
    selected_channel: Dict[str, Any] = Field(default_factory=dict)
    official_channel_evidence: Dict[str, Any] = Field(default_factory=dict)
    official_channel_confidence: str = "unverified"
    videos: List[VideoEvidence] = Field(default_factory=list)
    weekly_upload_frequency: float = 0.0
    recent_upload_surge: bool = False
    recurring_topics: List[str] = Field(default_factory=list)
    content_format_mix: Dict[str, int] = Field(default_factory=dict)


class YouTubeReport(BaseModel):
    report_type: str
    period: str
    channels: List[ChannelAnalysis] = Field(default_factory=list)
    comparative_analysis: str
    disclaimers: List[str]
    summary_markdown: str


def _duration_seconds(value: str) -> int:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not match:
        return -1
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _evidence(videos: List[Dict[str, Any]], metrics: List[Dict[str, Any]]) -> List[VideoEvidence]:
    metrics_by_id = {row.get("video_id"): row for row in metrics}
    evidence = []
    for video in videos:
        metric = metrics_by_id.get(video.get("video_id"), {})
        duration = metric.get("duration", "")
        seconds = _duration_seconds(duration)
        content_format = "Shorts" if 0 <= seconds <= 60 else "롱폼" if seconds > 60 else "길이 미확인"
        evidence.append(VideoEvidence(**{**video, **metric, "duration": duration, "content_format": content_format, "daily_average_views": metric.get("daily_views", 0)}))
    return evidence


def _activity(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    timestamps = []
    for video in videos:
        try:
            timestamps.append(datetime.fromisoformat(video.get("published_at", "").replace("Z", "+00:00")))
        except ValueError:
            continue
    weekly = 0.0
    surge = False
    if len(timestamps) >= 2:
        timestamps.sort()
        days = max(1, (timestamps[-1] - timestamps[0]).days)
        weekly = round(len(timestamps) / days * 7, 2)
        recent = sum(1 for value in timestamps if (timestamps[-1] - value).days <= 7)
        surge = recent >= 2 and recent > weekly * 1.5
    tokens = re.findall(r"[A-Za-z가-힣0-9]{2,}", " ".join(f"{item.get('title', '')} {item.get('description', '')}" for item in videos).lower())
    topics = [token for token, count in Counter(tokens).most_common() if count >= 2][:5]
    formats = Counter("shorts" if "short" in item.get("title", "").lower() else "review" if "리뷰" in item.get("title", "") else "tutorial" if "사용법" in item.get("title", "") else "campaign" if "광고" in item.get("title", "") or "campaign" in item.get("title", "").lower() else "other" for item in videos)
    return {"weekly_upload_frequency": weekly, "recent_upload_surge": surge, "recurring_topics": topics, "content_format_mix": dict(formats)}


def _performance_summary(channel: ChannelAnalysis) -> str:
    videos = channel.videos
    if not videos:
        return f"{channel.company}: 분석 가능한 영상이 없습니다."
    top = max(videos, key=lambda video: (video.engagement_rate, video.views))
    return (
        f"{channel.company}: 영상 {len(videos)}건, 중앙 조회수 {median(video.views for video in videos):,.0f}, "
        f"중앙 참여율 {median(video.engagement_rate for video in videos):.2f}%, "
        f"중앙 일평균 조회수 {median(video.daily_average_views for video in videos):,.0f}; "
        f"최고 공개 반응 영상은 '{top.title}' ({top.url})입니다."
    )


def _comparison_text(channels: List[ChannelAnalysis]) -> str:
    lines = [
        "| 비교 대상 | 공개 반응 신호 | 메시지·형식 신호 | 회사의 광고 기획 가설 |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for channel in channels:
        videos = channel.videos
        top = max(videos, key=lambda video: (video.engagement_rate, video.views)) if videos else None
        response = (
            f"중앙 참여율 {median(video.engagement_rate for video in videos):.2f}% / "
            f"중앙 일평균 조회수 {median(video.daily_average_views for video in videos):,.0f}"
            if videos else "분석 가능한 공개 지표 없음"
        )
        message = (
            f"주제: {', '.join(channel.recurring_topics) or '확인 불가'}; "
            f"형식: {channel.content_format_mix or '확인 불가'}"
        )
        hypothesis = (
            f"'{top.title}'의 메시지·형식을 별도 크리에이티브 테스트군으로 검토"
            if top else "추가 영상 표본 수집 후 메시지·형식 테스트 설계"
        )
        lines.append(f"| {channel.company} | {response} | {message} | {hypothesis} |")
    if len(channels) == 2:
        shared = ", ".join(sorted(set(channels[0].recurring_topics) & set(channels[1].recurring_topics))) or "없음"
        distinct = ", ".join(sorted(set(channels[0].recurring_topics) ^ set(channels[1].recurring_topics))) or "없음"
        lines.append(f"| 공통/차별 포인트 | - | 공통 주제: {shared}; 차별 주제: {distinct} | 공통 주제는 차별화 메시지·CTA 변형군으로, 차별 주제는 신규 가설군으로 검토 |")
    return "\n".join(lines)


def _single_channel_planning_table(channel: ChannelAnalysis, mode: str) -> str:
    videos = channel.videos
    top = max(videos, key=lambda video: (video.engagement_rate, video.views)) if videos else None
    response = (
        f"중앙 참여율 {median(video.engagement_rate for video in videos):.2f}% / "
        f"중앙 일평균 조회수 {median(video.daily_average_views for video in videos):,.0f}"
        if videos else "분석 가능한 공개 지표 없음"
    )
    if mode == "paid_promotion":
        action = "상위 반응 영상의 표현·형식을 크리에이티브 테스트군으로 검토"
        label = "유료 프로모션 콘텐츠"
    else:
        action = "반복 주제·형식을 다음 콘텐츠 기획의 가설군으로 검토"
        label = "최근 콘텐츠 전략"
    return "\n".join([
        "| 분석 대상 | 공개 반응 신호 | 콘텐츠 신호 | 광고·콘텐츠 기획 가설 |",
        "| :--- | :--- | :--- | :--- |",
        f"| {label} | {response} | 주제: {', '.join(channel.recurring_topics) or '확인 불가'}; 형식: {dict(Counter(video.content_format for video in videos))} | {action} |",
        f"| 최고 반응 영상 | {top.title if top else 'N/A'} | {top.url if top else 'N/A'} | 메시지·CTA 변형을 별도 A/B 테스트로 검증 |",
    ])


def _render(report: YouTubeReport) -> str:
    lines = [f"# 🎬 {report.report_type}", f"**분석 기간**: {report.period}", ""]
    verified_channels = [channel for channel in report.channels if channel.selected_channel]
    if verified_channels:
        lines.extend([
            "### 1. 공식 채널 후보 검증 내역",
            "| 회사 | 검증 상태 | 채널명 | 채널 URL | 검증 근거 |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])
        for channel in verified_channels:
            evidence = channel.official_channel_evidence
            status = "⚠️ LLM 선택 후보" if channel.official_channel_confidence == "LLM-selected candidate" else "⚠️ 미검증"
            candidate = channel.selected_channel
            lines.append(
                f"| {channel.company} | {status} | {evidence.get('channel_name') or candidate.get('channel_name', 'N/A')} | "
                f"{evidence.get('channel_url') or candidate.get('url', 'N/A')} | "
                f"{evidence.get('official_status_note', 'API 후보 응답')} |"
            )
        lines.append("")
    lines.extend([
        "### 2. 핵심 공개 반응 지표",
        "| 대상 | 영상 수 | 중앙 조회수 | 중앙 참여율 | 중앙 일평균 조회수 | 최근 업로드 급증 |",
        "| :--- | ---: | ---: | ---: | ---: | :--- |",
    ])
    for channel in report.channels:
        videos = channel.videos
        top = max(videos, key=lambda video: (video.engagement_rate, video.views)) if videos else None
        med_views = median(video.views for video in videos) if videos else 0
        med_engagement = median(video.engagement_rate for video in videos) if videos else 0
        med_daily = median(video.daily_average_views for video in videos) if videos else 0
        lines.append(
            f"| {channel.company} | {len(videos)} | {med_views:,.0f} | {med_engagement:.2f}% | {med_daily:,.0f} | "
            f"{'예' if channel.recent_upload_surge else '아니오'} |"
        )
    lines.append("")
    lines.extend([
        "### 3. 콘텐츠 전략 신호",
        "| 대상 | 주당 업로드 | 반복 주제 | 콘텐츠 형식 | 최고 반응 영상 |",
        "| :--- | ---: | :--- | :--- | :--- |",
    ])
    for channel in report.channels:
        videos = channel.videos
        top = max(videos, key=lambda video: (video.engagement_rate, video.views)) if videos else None
        top_video = f"[{top.title}]({top.url})" if top and top.url else "N/A"
        format_mix = dict(Counter(video.content_format for video in videos))
        lines.append(
            f"| {channel.company} | {channel.weekly_upload_frequency:.2f}회 | "
            f"{', '.join(channel.recurring_topics) or '확인 불가'} | {format_mix or '확인 불가'} | {top_video} |"
        )
    lines.append("")
    lines.append("### 4. 영상 근거")
    for channel in report.channels:
        lines.append(f"#### {channel.company}")
        lines.append("| 제목 | 형식 | URL | 조회수 | 참여율 | 일평균 조회수 |")
        lines.append("| :--- | :--- | :--- | ---: | ---: | ---: |")
        for video in channel.videos:
            lines.append(f"| {video.title or 'N/A'} | {video.content_format} | {video.url or 'N/A'} | {video.views:,} | {video.engagement_rate:.2f}% | {video.daily_average_views:,.0f} |")
    lines.extend(["", "### 5. 광고 기획 비교", report.comparative_analysis, "", "공개 반응 신호는 광고비 또는 광고 효율을 뜻하지 않습니다. 실제 집행 전 별도 A/B 테스트가 필요합니다.", "", "### 6. API 제약사항 및 준수 고지"])
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
    required_tool_names = property(lambda self: ["find_youtube_channel", "get_channel_details", "get_channel_videos", "get_video_metrics"])

    def execute(self, params: CompetitorComparisonParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        analyses = []
        for company in (params.company_a, params.company_b):
            candidates = _rows(_run(tools, "find_youtube_channel", company_name=company))
            selected = _select_channel(candidates, context)
            details = _run(tools, "get_channel_details", channel_id=selected.get("channel_id", ""))
            videos = _rows(_run(tools, "get_channel_videos", channel_id=selected.get("channel_id", ""), published_after=f"{params.start_date}T00:00:00Z", published_before=f"{params.end_date}T23:59:59Z", keyword="광고"))
            metrics = _rows(_run(tools, "get_video_metrics", video_ids=_video_ids(videos)))
            analyses.append(ChannelAnalysis(company=company, selected_channel=selected, official_channel_evidence=details if isinstance(details, dict) else {}, official_channel_confidence="LLM-selected candidate" if (context or {}).get("llm") else "unverified", videos=_evidence(videos, metrics), **_activity(videos)))
        report = YouTubeReport(report_type=f"{params.company_a} vs {params.company_b} YouTube 광고 콘텐츠 비교", period=f"{params.start_date} ~ {params.end_date}", channels=analyses, comparative_analysis=_comparison_text(analyses), disclaimers=DISCLAIMERS, summary_markdown="")
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
        evidence = sorted(_evidence(videos, metrics), key=lambda video: (video.engagement_rate, video.views), reverse=True)
        analysis = ChannelAnalysis(company=params.keyword, videos=evidence, **_activity(videos))
        report = YouTubeReport(report_type=f"{params.keyword} 유료 프로모션 포함 표시 콘텐츠", period=f"{params.start_date} ~ 현재", channels=[analysis], comparative_analysis=_single_channel_planning_table(analysis, "paid_promotion") + "\n\n유료 프로모션 포함 표시는 YouTube 광고 집행 영상을 뜻하지 않습니다.", disclaimers=DISCLAIMERS + ["유료 프로모션 포함 표시는 업로더 고지이며 YouTube 광고 집행 여부가 아닙니다."], summary_markdown="")
        return _render(report)


class CompetitorStrategyParams(BaseModel):
    company: str = Field(description="분석할 경쟁사명")
    start_date: str = Field(default_factory=lambda: str(date.today() - timedelta(days=30)), description="분석 시작일, YYYY-MM-DD")


class CompetitorStrategyScenario(BaseScenario):
    name = property(lambda self: "youtube_competitor_strategy")
    description = property(lambda self: "경쟁사 공식 YouTube 채널의 최근 업로드에서 제품·메시지 변화를 추적한다.")
    parameters_schema = property(lambda self: CompetitorStrategyParams)
    required_tool_names = property(lambda self: ["find_youtube_channel", "get_channel_details", "get_competitor_recent_uploads", "get_video_metrics"])

    def execute(self, params: CompetitorStrategyParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        candidates = _rows(_run(tools, "find_youtube_channel", company_name=params.company))
        selected = _select_channel(candidates, context)
        details = _run(tools, "get_channel_details", channel_id=selected.get("channel_id", ""))
        videos = _rows(_run(tools, "get_competitor_recent_uploads", channel_id=selected.get("channel_id", ""), published_after=f"{params.start_date}T00:00:00Z"))
        metrics = _rows(_run(tools, "get_video_metrics", video_ids=_video_ids(videos)))
        analysis = ChannelAnalysis(company=params.company, selected_channel=selected, official_channel_evidence=details if isinstance(details, dict) else {}, official_channel_confidence="LLM-selected candidate" if (context or {}).get("llm") else "unverified", videos=_evidence(videos, metrics), **_activity(videos))
        report = YouTubeReport(report_type=f"{params.company} 최근 콘텐츠 전략", period=f"{params.start_date} ~ 현재", channels=[analysis], comparative_analysis=_single_channel_planning_table(analysis, "strategy") + f"\n\n주당 업로드 {analysis.weekly_upload_frequency:.2f}회, 최근 급증 {'감지' if analysis.recent_upload_surge else '미감지'}. 높은 조회수만으로 광고 성과를 단정하지 않습니다.", disclaimers=DISCLAIMERS, summary_markdown="")
        return _render(report)
