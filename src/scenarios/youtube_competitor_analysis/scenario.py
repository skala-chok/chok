"""유튜브 경쟁사 분석 구조화 시나리오 모듈."""

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.core.scenario import BaseScenario

MAX_EVIDENCE_ROWS = 10
MAX_TIMELINE_ROWS = 18
MESSAGE_LEXICON = ("가벼움", "성능", "디자인", "내구성", "할인", "신제품", "한정판")
CTA_LEXICON = ("구매", "지금", "링크", "신청", "구독", "확인")
TOPIC_STOPWORDS = frozenset({
    "광고", "영상", "채널", "유튜브", "공식", "구독", "좋아요", "댓글", "알림", "설정",
    "이번", "저희", "여러분", "정말", "진짜", "그리고", "하지만", "에서", "으로", "까지",
    "부터", "대한", "관련", "이제", "오늘", "모두", "위해", "있는", "하는", "합니다",
    "입니다", "했습니다", "됩니다", "the", "and", "for", "with", "you", "this", "that",
    "http", "https", "www", "youtube", "com", "shorts", "video", "official", "new",
})
TOPIC_PARTICLES = "은는이가을를의에도만로과와서"
ORIGIN_LABELS = {"brand": "브랜드 채널", "creator": "크리에이터 채널", "unknown": "미상"}
TREND_LABELS = {
    "insufficient data": "표본 부족",
    "possible fatigue": "▼ 최근 반응 둔화",
    "recent response stronger": "▲ 최근 반응 강세",
    "stable": "－ 유지",
}
DISCLAIMERS = [
    "공식 채널 후보는 API 응답 기반이며, 브랜드 웹사이트 등으로 추가 검증이 필요합니다.",
    "조회수·좋아요·댓글·참여율·일평균 조회수는 공개 반응 지표입니다.",
    "공개 반응 지표만으로 광고비, YouTube 광고 집행 여부, 또는 광고 효율을 단정하지 않습니다.",
]


# ------------------------------------------------------------------------------
# 🔧 [도구 호출 헬퍼]
# ------------------------------------------------------------------------------
def _run(tools: Dict[str, BaseTool], name: str, **kwargs: Any) -> Any:
    tool = tools.get(name)
    return tool.invoke(kwargs) if tool else []


def _rows(value: Any) -> List[Dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _video_ids(rows: List[Dict[str, Any]]) -> List[str]:
    return [row["video_id"] for row in rows if row.get("video_id")]


def _select_channel(candidates: List[Dict[str, Any]], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """가장 유력한 공식 채널 후보 1개를 선택합니다 (단순 선별이며 공식 소유권 증명이 아님을 명시)."""
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


# ------------------------------------------------------------------------------
# 🔴 [Pydantic 스키마 정의]
# ------------------------------------------------------------------------------
class VideoEvidence(BaseModel):
    """단일 영상의 공개 메타데이터 및 반응 지표."""

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


class WeeklyPoint(BaseModel):
    """주차 단위로 집계한 업로드량과 공개 반응 중앙값."""

    week: str = Field(description="주차 라벨 (예: '8월 2주')")
    uploads: int = Field(default=0, description="해당 주차 업로드 영상 수")
    median_views: float = Field(default=0.0, description="해당 주차 중앙 조회수")
    median_engagement_rate: float = Field(default=0.0, description="해당 주차 중앙 참여율(%)")
    median_daily_views: float = Field(default=0.0, description="해당 주차 중앙 일평균 조회수")


class FormatPerformance(BaseModel):
    """콘텐츠 형식(Shorts/롱폼)별 공개 반응 집계."""

    content_format: str = Field(description="콘텐츠 형식 라벨")
    videos: int = Field(default=0, description="해당 형식 영상 수")
    median_views: float = Field(default=0.0, description="중앙 조회수")
    median_engagement_rate: float = Field(default=0.0, description="중앙 참여율(%)")
    median_daily_views: float = Field(default=0.0, description="중앙 일평균 조회수")


class ChannelAnalysis(BaseModel):
    """분석 대상 1건(회사 채널 또는 키워드 집합)의 집계 결과."""

    company: str
    selected_channel: Dict[str, Any] = Field(default_factory=dict)
    official_channel_evidence: Dict[str, Any] = Field(default_factory=dict)
    official_channel_confidence: str = "unverified"
    videos: List[VideoEvidence] = Field(default_factory=list)
    weekly_upload_frequency: float = 0.0
    recent_upload_surge: bool = False
    recurring_topics: List[str] = Field(default_factory=list)
    topic_counts: Dict[str, int] = Field(default_factory=dict, description="주제어별 등장 영상 수")
    weekly_timeline: List[WeeklyPoint] = Field(default_factory=list)
    format_performance: List[FormatPerformance] = Field(default_factory=list)
    message_signals: List[str] = Field(default_factory=list)
    cta_signals: List[str] = Field(default_factory=list)
    creator_vs_brand_mix: Dict[str, int] = Field(default_factory=dict)
    creative_fatigue_proxy: str = "insufficient data"
    response_change_pct: float = Field(default=0.0, description="전반기 대비 후반기 중앙 일평균 조회수 변화율(%)")


class YouTubeReport(BaseModel):
    """시나리오 공통 리포트 컨테이너."""

    report_type: str
    period: str
    channels: List[ChannelAnalysis] = Field(default_factory=list)
    comparative_analysis: str
    disclaimers: List[str]
    summary_markdown: str


# ------------------------------------------------------------------------------
# 📐 [표기 헬퍼 - 사람이 읽는 값으로 변환]
# ------------------------------------------------------------------------------
def _cell(value: Any, limit: int = 40) -> str:
    """Markdown 표 셀 안전 문자열로 정규화합니다.

    Args:
        value: 셀에 넣을 원본 값.
        limit: 최대 표시 길이. 초과분은 말줄임표로 절단합니다.

    Returns:
        구분자(`|`)와 줄바꿈이 제거된 표 셀 문자열.
    """
    text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip().replace("|", "\\|")
    if not text:
        return "N/A"
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _compact(value: float) -> str:
    """큰 수치를 한국어 단위(만/억)로 축약해 스캔 가능하게 만듭니다."""
    if value >= 100_000_000:
        return f"{value / 100_000_000:.1f}억"
    if value >= 10_000:
        return f"{value / 10_000:.1f}만"
    return f"{value:,.0f}"


def _percent(value: float) -> str:
    return f"{value:.2f}%"


def _median(values: Iterable[float]) -> float:
    collected = list(values)
    return float(median(collected)) if collected else 0.0


def _delta(new_value: float, old_value: float) -> str:
    """직전 구간 대비 변화율을 방향 기호와 함께 표기합니다."""
    if old_value <= 0:
        return "비교 불가"
    change = (new_value - old_value) / old_value * 100
    mark = "▲" if change > 0.5 else "▼" if change < -0.5 else "－"
    return f"{mark} {abs(change):.1f}%"


def _parse_time(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _day_label(value: str) -> str:
    moment = _parse_time(value)
    return moment.strftime("%m-%d") if moment else "N/A"


def _count_labels(counts: Dict[str, int], labels: Optional[Dict[str, str]] = None) -> str:
    """카테고리 카운트를 사람이 읽는 Markdown 셀 문자열로 만듭니다."""
    mapping = labels or {}
    return ", ".join(f"{mapping.get(name, name)} {count}건" for name, count in counts.items()) or "확인 불가"


def _topic_labels(channel: ChannelAnalysis) -> str:
    if not channel.recurring_topics:
        return "반복 주제 없음(표본 부족)"
    return ", ".join(f"{topic} {channel.topic_counts.get(topic, 0)}개 영상" for topic in channel.recurring_topics)


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]], aligns: Optional[Sequence[str]] = None) -> str:
    if aligns is None:
        aligns = [":---"] * len(headers)
    lines = [f"| {' | '.join(headers)} |", f"| {' | '.join(aligns)} |"]
    lines.extend(f"| {' | '.join(str(c) for c in r)} |" for r in rows)
    return "\n".join(lines)


def _video_link(video: Optional[VideoEvidence]) -> str:
    """제목을 링크로 감싸되 제목 안의 대괄호가 링크 문법을 깨지 않게 이스케이프합니다."""
    if not video:
        return "N/A"
    title = _cell(video.title, limit=34)
    if not video.url:
        return title
    return f"[{title.replace('[', chr(92) + '[').replace(']', chr(92) + ']')}]({video.url})"


def _top_video(videos: Sequence[VideoEvidence]) -> Optional[VideoEvidence]:
    return max(videos, key=lambda v: (v.engagement_rate, v.views)) if videos else None


# ------------------------------------------------------------------------------
# 🧮 [집계 로직]
# ------------------------------------------------------------------------------
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
        evidence.append(VideoEvidence(**{
            **video,
            **metric,
            "duration": duration,
            "content_format": content_format,
            "daily_average_views": metric.get("daily_views", 0),
        }))
    return evidence


def _strip_particle(token: str) -> str:
    for _ in range(2):
        if len(token) >= 3 and token[-1] in TOPIC_PARTICLES:
            token = token[:-1]
    return token


def _topics(videos: List[Dict[str, Any]], company: str = "") -> Tuple[List[str], Dict[str, int]]:
    owner = company.lower().strip()
    counts: Counter = Counter()
    for item in videos:
        text = f"{item.get('title', '')} {item.get('description', '')}".lower()
        seen = {
            t for raw in re.findall(r"[가-힣A-Za-z0-9]{2,}", text)
            if (t := _strip_particle(raw))
            and len(t) >= 2 and not t.isdigit()
            and t not in TOPIC_STOPWORDS and t not in MESSAGE_LEXICON and t not in CTA_LEXICON
            and (not owner or (t not in owner and owner not in t))
        }
        counts.update(seen)
    ranked = [(k, v) for k, v in counts.most_common(6) if v >= 2]
    return [k for k, _ in ranked], dict(ranked)


def _activity(videos: List[Dict[str, Any]], company: str = "") -> Dict[str, Any]:
    timestamps = [moment for moment in (_parse_time(item.get("published_at", "")) for item in videos) if moment]
    weekly, surge = 0.0, False
    if len(timestamps) >= 2:
        timestamps.sort()
        days = max(1, (timestamps[-1] - timestamps[0]).days)
        weekly = round(len(timestamps) / days * 7, 2)
        recent = sum(1 for value in timestamps if (timestamps[-1] - value).days <= 7)
        surge = recent >= 2 and recent > weekly * 1.5
    topics, topic_counts = _topics(videos, company)
    return {
        "weekly_upload_frequency": weekly,
        "recent_upload_surge": surge,
        "recurring_topics": topics,
        "topic_counts": topic_counts,
    }


def _week_sequence(start: Tuple[int, int, int], end: Tuple[int, int, int]) -> List[Tuple[int, int, int]]:
    seq, cur = [], start
    while cur <= end and len(seq) < MAX_TIMELINE_ROWS:
        seq.append(cur)
        y, m, w = cur
        cur = (y, m, w + 1) if w < 5 else (y + 1, 1, 1) if m == 12 else (y, m + 1, 1)
    return seq if end in seq else sorted({*seq, end})


def _weekly_timeline(evidence: List[VideoEvidence]) -> List[WeeklyPoint]:
    buckets: Dict[Tuple[int, int, int], List[VideoEvidence]] = defaultdict(list)
    for video in evidence:
        moment = _parse_time(video.published_at)
        if moment:
            buckets[(moment.year, moment.month, min((moment.day - 1) // 7 + 1, 5))].append(video)
    if not buckets:
        return []
    timeline = []
    for year, month, week in _week_sequence(min(buckets), max(buckets)):
        items = buckets.get((year, month, week), [])
        timeline.append(WeeklyPoint(
            week=f"{month}월 {week}주",
            uploads=len(items),
            median_views=_median(v.views for v in items),
            median_engagement_rate=_median(v.engagement_rate for v in items),
            median_daily_views=_median(v.daily_average_views for v in items),
        ))
    return timeline


def _format_performance(evidence: List[VideoEvidence]) -> List[FormatPerformance]:
    buckets: Dict[str, List[VideoEvidence]] = defaultdict(list)
    for video in evidence:
        buckets[video.content_format].append(video)
    performance = [
        FormatPerformance(
            content_format=name,
            videos=len(items),
            median_views=_median(v.views for v in items),
            median_engagement_rate=_median(v.engagement_rate for v in items),
            median_daily_views=_median(v.daily_average_views for v in items),
        )
        for name, items in buckets.items()
    ]
    return sorted(performance, key=lambda item: item.median_daily_views, reverse=True)


def _ad_trend_signals(
    videos: List[Dict[str, Any]], evidence: List[VideoEvidence], official_name: str = ""
) -> Dict[str, Any]:
    text = " ".join(f"{video.get('title', '')} {video.get('description', '')}" for video in videos).lower()
    messages = [word for word in MESSAGE_LEXICON if word in text]
    ctas = [word for word in CTA_LEXICON if word in text]
    origin = Counter(
        "brand" if official_name and video.channel_name == official_name else "creator" if video.channel_name else "unknown"
        for video in evidence
    )
    ordered = sorted(evidence, key=lambda video: video.published_at)
    fatigue = "insufficient data"
    change_pct = 0.0
    if len(ordered) >= 4:
        midpoint = len(ordered) // 2
        older = _median(v.daily_average_views for v in ordered[:midpoint])
        newer = _median(v.daily_average_views for v in ordered[midpoint:])
        change_pct = round((newer - older) / older * 100, 1) if older > 0 else 0.0
        fatigue = "possible fatigue" if newer < older * 0.7 else "recent response stronger" if newer > older * 1.3 else "stable"
    return {
        "message_signals": messages,
        "cta_signals": ctas,
        "creator_vs_brand_mix": dict(origin),
        "creative_fatigue_proxy": fatigue,
        "response_change_pct": change_pct,
        "weekly_timeline": _weekly_timeline(evidence),
        "format_performance": _format_performance(evidence),
    }


# ------------------------------------------------------------------------------
# 📄 [Markdown 렌더링 - 트렌드 판독 우선 배치]
# ------------------------------------------------------------------------------
def _trend_label(channel: ChannelAnalysis) -> str:
    label = TREND_LABELS.get(channel.creative_fatigue_proxy, channel.creative_fatigue_proxy)
    if channel.creative_fatigue_proxy == "insufficient data":
        return label
    return f"{label} ({channel.response_change_pct:+.1f}%)"


def _gap(first: ChannelAnalysis, second: ChannelAnalysis, first_val: float, second_val: float, kind: str) -> str:
    if first_val == second_val:
        return "동일"
    leader = first.company if first_val > second_val else second.company
    high, low = max(first_val, second_val), min(first_val, second_val)
    if kind == "count":
        return f"{_cell(leader, 16)} +{high - low:,.0f}건"
    if kind == "points":
        return f"{_cell(leader, 16)} +{high - low:.2f}%p"
    return f"{_cell(leader, 16)} {high / low:.1f}배" if low > 0 else f"{_cell(leader, 16)} 단독"


def _overview_block(report: YouTubeReport) -> str:
    channels = report.channels
    if not channels:
        return ""
    metrics = [
        ("분석 영상", lambda c: f"{len(c.videos):,}건", "count", lambda c: float(len(c.videos))),
        ("중앙 조회수", lambda c: _compact(_median(v.views for v in c.videos)), "ratio", lambda c: _median(v.views for v in c.videos)),
        ("중앙 참여율", lambda c: _percent(_median(v.engagement_rate for v in c.videos)), "points", lambda c: _median(v.engagement_rate for v in c.videos)),
        ("중앙 일평균 조회수", lambda c: _compact(_median(v.daily_average_views for v in c.videos)), "ratio", lambda c: _median(v.daily_average_views for v in c.videos)),
        ("주당 업로드(관측 구간)", lambda c: f"{c.weekly_upload_frequency:.2f}회", "ratio", lambda c: c.weekly_upload_frequency),
    ]
    if len(channels) == 1:
        c = channels[0]
        rows = [[label, renderer(c)] for label, renderer, _, _ in metrics]
        rows.extend([
            ["형식 구성", _cell(_count_labels(dict(Counter(v.content_format for v in c.videos))), 60)],
            ["최근 업로드 급증", "예" if c.recent_upload_surge else "아니오"],
            ["반응 추세", _trend_label(c)],
            ["최고 반응 영상", _video_link(_top_video(c.videos))],
        ])
        return _table(["항목", "값"], rows)

    headers = ["지표"] + [_cell(c.company, 16) for c in channels]
    aligns = [":---"] + ["---:"] * len(channels)
    if len(channels) == 2:
        headers.append("격차")
        aligns.append(":---")
    rows = []
    for label, renderer, kind, val_fn in metrics:
        row = [label] + [renderer(c) for c in channels]
        if len(channels) == 2:
            row.append(_gap(channels[0], channels[1], val_fn(channels[0]), val_fn(channels[1]), kind))
        rows.append(row)
    extra = [
        ("형식 구성", lambda c: _cell(_count_labels(dict(Counter(v.content_format for v in c.videos))), 40)),
        ("최근 업로드 급증", lambda c: "예" if c.recent_upload_surge else "아니오"),
        ("반응 추세", _trend_label),
        ("최고 반응 영상", lambda c: _video_link(_top_video(c.videos))),
    ]
    for label, fn in extra:
        row = [label] + [fn(c) for c in channels]
        if len(channels) == 2:
            row.append("-")
        rows.append(row)
    return _table(headers, rows, aligns)


def _timeline_block(report: YouTubeReport) -> str:
    sections = []
    multi = len(report.channels) > 1
    for channel in report.channels:
        if not channel.weekly_timeline:
            continue
        rows = []
        prev = 0.0
        for p in channel.weekly_timeline:
            if not p.uploads:
                rows.append([p.week, "0건", "-", "-", "-", "업로드 없음"])
                continue
            change = _delta(p.median_daily_views, prev) if prev else "기준 주차"
            rows.append([p.week, f"{p.uploads}건", _compact(p.median_views), _percent(p.median_engagement_rate), _compact(p.median_daily_views), change])
            prev = p.median_daily_views
        t = _table(["주차", "업로드", "중앙 조회수", "중앙 참여율", "중앙 일평균 조회수", "전주 대비"], rows, [":---", "---:", "---:", "---:", "---:", ":---"])
        sections.append(f"#### {_cell(channel.company, 30)}\n\n{t}" if multi else t)
    return "\n\n".join(sections)


def _format_block(report: YouTubeReport) -> str:
    multi = len(report.channels) > 1
    headers = (["대상"] if multi else []) + ["형식", "영상 수", "중앙 조회수", "중앙 참여율", "중앙 일평균 조회수"]
    aligns = ([":---"] if multi else []) + [":---", "---:", "---:", "---:", "---:"]
    rows = [
        ([_cell(c.company, 16)] if multi else []) + [
            item.content_format, f"{item.videos}건", _compact(item.median_views),
            _percent(item.median_engagement_rate), _compact(item.median_daily_views),
        ]
        for c in report.channels for item in c.format_performance
    ]
    return _table(headers, rows, aligns) if rows else ""


def _signal_block(report: YouTubeReport) -> str:
    multi = len(report.channels) > 1
    headers = (["대상"] if multi else []) + ["반복 주제", "반복 메시지", "CTA 신호", "채널 구성"]
    rows = [
        ([_cell(c.company, 16)] if multi else []) + [
            _cell(_topic_labels(c), 60),
            _cell(", ".join(c.message_signals) or "확인 불가", 40),
            _cell(", ".join(c.cta_signals) or "확인 불가", 40),
            _cell(_count_labels(c.creator_vs_brand_mix, ORIGIN_LABELS), 40),
        ]
        for c in report.channels
    ]
    return _table(headers, rows) if rows else ""


def _evidence_block(report: YouTubeReport) -> str:
    sections = []
    multi = len(report.channels) > 1
    for c in report.channels:
        if not c.videos:
            continue
        ranked = sorted(c.videos, key=lambda v: (v.engagement_rate, v.views), reverse=True)
        shown = sorted(ranked[:MAX_EVIDENCE_ROWS], key=lambda v: v.published_at, reverse=True)
        rows = [
            [_day_label(v.published_at), _video_link(v), v.content_format, f"{v.views:,}", _percent(v.engagement_rate), f"{v.daily_average_views:,.0f}"]
            for v in shown
        ]
        t = _table(["게시일", "제목", "형식", "조회수", "참여율", "일평균 조회수"], rows, [":---", ":---", ":---", "---:", "---:", "---:"])
        hidden = len(c.videos) - len(shown)
        if hidden > 0:
            t += f"\n\n_반응 상위 {MAX_EVIDENCE_ROWS}건만 표시했습니다. 외 {hidden}건은 구조화 데이터에 있습니다._"
        sections.append(f"#### {_cell(c.company, 30)}\n\n{t}" if multi else t)
    return "\n\n".join(sections)


def _channel_block(report: YouTubeReport) -> str:
    verified = [c for c in report.channels if c.selected_channel]
    if not verified:
        return ""
    rows = [
        [
            _cell(c.company, 16),
            "⚠️ LLM 선택 후보" if c.official_channel_confidence == "LLM-selected candidate" else "⚠️ 미검증",
            _cell(c.official_channel_evidence.get("channel_name") or c.selected_channel.get("channel_name", "")),
            _cell(c.official_channel_evidence.get("channel_url") or c.selected_channel.get("url", "")),
            _cell(c.official_channel_evidence.get("official_status_note", "API 후보 응답")),
        ]
        for c in verified
    ]
    return _table(["회사", "검증 상태", "채널명", "채널 URL", "검증 근거"], rows)


def _comparison_text(channels: List[ChannelAnalysis]) -> str:
    rows = []
    for c in channels:
        top = _top_video(c.videos)
        resp = f"참여율 {_percent(_median(v.engagement_rate for v in c.videos))} · 일평균 {_compact(_median(v.daily_average_views for v in c.videos))}" if c.videos else "분석 가능한 공개 지표 없음"
        msg = f"주제 {_topic_labels(c)} · 형식 {_count_labels(dict(Counter(v.content_format for v in c.videos)))}"
        hypo = f"'{_cell(top.title, 24)}'의 메시지·형식을 별도 크리에이티브 테스트군으로 검토" if top else "추가 영상 표본 수집 후 메시지·형식 테스트 설계"
        rows.append([_cell(c.company, 16), resp, _cell(msg, 60), hypo])
    if len(channels) == 2:
        shared = ", ".join(sorted(set(channels[0].recurring_topics) & set(channels[1].recurring_topics))) or "없음"
        distinct = ", ".join(sorted(set(channels[0].recurring_topics) ^ set(channels[1].recurring_topics))) or "없음"
        rows.append(["공통/차별 포인트", "-", _cell(f"공통 주제 {shared} · 차별 주제 {distinct}", 60), "공통 주제는 차별화 메시지·CTA 변형군으로, 차별 주제는 신규 가설군으로 검토"])
    return _table(["비교 대상", "공개 반응 신호", "메시지·형식 신호", "회사의 광고 기획 가설"], rows)


def _single_channel_planning_table(channel: ChannelAnalysis, mode: str) -> str:
    videos = channel.videos
    top = _top_video(videos)
    resp = f"참여율 {_percent(_median(v.engagement_rate for v in videos))} · 일평균 {_compact(_median(v.daily_average_views for v in videos))}" if videos else "분석 가능한 공개 지표 없음"
    mix = _count_labels(dict(Counter(v.content_format for v in videos)))
    if mode == "paid_promotion":
        rows = [
            ["크리에이티브 참고", _video_link(top), "반응이 확인된 표현·형식을 테스트 가설로 활용", "공개 반응은 유료 집행 성과가 아님; 별도 A/B 테스트 필요"],
            ["크리에이터 적합성", resp, "크리에이터 문체·신뢰를 활용한 제품 맥락화 가능", "채널 시청자가 목표 고객과 일치하는지 별도 검증 필요"],
            ["콘텐츠 형식", _cell(mix, 40), "Shorts/롱폼 조합으로 메시지 전달 방식 실험 가능", "형식별 도달·전환 차이는 현재 공개 데이터로 확인 불가"],
            ["고지·브랜드 통제", "유료 프로모션 포함 표시", "광고성 고지를 명확히 하여 투명성 확보", "메시지 통제·브랜드 안전성·계약 조건은 개별 검토 필요"],
        ]
        return f"#### 유료 프로모션 장단점 비교\n\n{_table(['유료 프로모션 판단 항목', '공개 콘텐츠 신호', '기대 장점', '리스크·검증 조건'], rows)}"
    rows = [
        ["최근 콘텐츠 전략", resp, _cell(f"주제 {_topic_labels(channel)} · 형식 {mix}", 60), "반복 주제·형식을 다음 콘텐츠 기획의 가설군으로 검토"],
        ["최고 반응 영상", _video_link(top), f"참여율 {_percent(top.engagement_rate)}" if top else "N/A", "메시지·CTA 변형을 별도 A/B 테스트로 검증"],
    ]
    return _table(["분석 대상", "공개 반응 신호", "콘텐츠 신호", "광고·콘텐츠 기획 가설"], rows)


def _headline(report: YouTubeReport) -> str:
    total = sum(len(c.videos) for c in report.channels)
    verified = [c for c in report.channels if c.selected_channel]
    status = "⚠️ 공식 채널 미검증 후보" if verified else "해당 없음(키워드 탐색)"
    return f"**분석 기간** {report.period} · **분석 영상** {total}건 · **채널 검증** {status}"


def _render(report: YouTubeReport) -> str:
    blocks = [
        ("한눈에 보기", _overview_block(report)),
        ("기간 내 반응 추이", _timeline_block(report)),
        ("콘텐츠 형식별 성과", _format_block(report)),
        ("메시지·CTA 신호", _signal_block(report)),
        ("영상 근거", _evidence_block(report)),
        ("광고 기획 가설", report.comparative_analysis),
        ("공식 채널 후보 검증", _channel_block(report)),
        ("API 제약사항 및 준수 고지", "\n".join(f"{i}. {d}" for i, d in enumerate(report.disclaimers, 1))),
    ]
    lines = [f"# 🎬 {report.report_type}", "", _headline(report), ""]
    if not any(c.videos for c in report.channels):
        lines.extend(["> 분석 가능한 공개 영상 표본이 없습니다. 기간 또는 키워드를 넓혀 다시 실행하십시오.", ""])
    for idx, (title, body) in enumerate([b for b in blocks if b[1].strip()], 1):
        lines.extend([f"## {idx}. {title}", "", body, ""])
        if title == "광고 기획 가설":
            lines.extend(["공개 반응 신호는 광고비 또는 광고 효율을 뜻하지 않습니다. 실제 집행 전 별도 A/B 테스트가 필요합니다.", ""])
    report.summary_markdown = "\n".join(lines).rstrip()
    return f"```json\n{report.model_dump_json(indent=2)}\n```\n\n{report.summary_markdown}"


# ------------------------------------------------------------------------------
# 🎬 [시나리오 1] 경쟁사 광고 콘텐츠 비교
# ------------------------------------------------------------------------------
class CompetitorComparisonParams(BaseModel):
    company_a: str = Field(description="첫 번째 비교 회사명")
    company_b: str = Field(description="두 번째 비교 회사명")
    start_date: str = Field(description="분석 시작일, YYYY-MM-DD")
    end_date: str = Field(description="분석 종료일, YYYY-MM-DD")


class CompetitorComparisonScenario(BaseScenario):
    name = "youtube_competitor_comparison"
    description = "두 회사 공식 YouTube 채널의 광고 후보 콘텐츠 공개 반응을 동일 기간으로 비교한다."
    parameters_schema = CompetitorComparisonParams
    required_tool_names = ["find_youtube_channel", "get_channel_details", "get_channel_videos", "get_video_metrics"]

    def execute(self, params: CompetitorComparisonParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        analyses = []
        for company in (params.company_a, params.company_b):
            candidates = _rows(_run(tools, "find_youtube_channel", company_name=company))
            selected = _select_channel(candidates, context)
            details = _run(tools, "get_channel_details", channel_id=selected.get("channel_id", ""))
            videos = _rows(_run(tools, "get_channel_videos", channel_id=selected.get("channel_id", ""), published_after=f"{params.start_date}T00:00:00Z", published_before=f"{params.end_date}T23:59:59Z", keyword="광고"))
            metrics = _rows(_run(tools, "get_video_metrics", video_ids=_video_ids(videos)))
            evidence = _evidence(videos, metrics)
            official_name = details.get("channel_name", "") if isinstance(details, dict) else ""
            analyses.append(ChannelAnalysis(company=company, selected_channel=selected, official_channel_evidence=details if isinstance(details, dict) else {}, official_channel_confidence="LLM-selected candidate" if (context or {}).get("llm") else "unverified", videos=evidence, **_activity(videos, company), **_ad_trend_signals(videos, evidence, official_name)))
        report = YouTubeReport(report_type=f"{params.company_a} vs {params.company_b} YouTube 광고 콘텐츠 비교", period=f"{params.start_date} ~ {params.end_date}", channels=analyses, comparative_analysis=_comparison_text(analyses), disclaimers=DISCLAIMERS, summary_markdown="")
        return _render(report)


# ------------------------------------------------------------------------------
# 🎬 [시나리오 2] 유료 프로모션 포함 표시 콘텐츠 탐색
# ------------------------------------------------------------------------------
class PaidPromotionParams(BaseModel):
    keyword: str = Field(description="탐색할 제품군 키워드")
    start_date: str = Field(default_factory=lambda: str(date.today() - timedelta(days=30)), description="분석 시작일, YYYY-MM-DD")


class PaidPromotionScenario(BaseScenario):
    name = "youtube_paid_promotion_discovery"
    description = "유료 프로모션 포함 표시 YouTube 콘텐츠의 공개 반응을 탐색한다."
    parameters_schema = PaidPromotionParams
    required_tool_names = ["search_paid_promotion_videos", "get_video_metrics"]

    def execute(self, params: PaidPromotionParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        videos = _rows(_run(tools, "search_paid_promotion_videos", keyword=params.keyword, published_after=f"{params.start_date}T00:00:00Z"))
        metrics = _rows(_run(tools, "get_video_metrics", video_ids=_video_ids(videos)))
        evidence = sorted(_evidence(videos, metrics), key=lambda video: (video.engagement_rate, video.views), reverse=True)
        analysis = ChannelAnalysis(company=params.keyword, videos=evidence, **_activity(videos, params.keyword), **_ad_trend_signals(videos, evidence))
        report = YouTubeReport(report_type=f"{params.keyword} 유료 프로모션 포함 표시 콘텐츠", period=f"{params.start_date} ~ 현재", channels=[analysis], comparative_analysis=_single_channel_planning_table(analysis, "paid_promotion") + "\n\n유료 프로모션 포함 표시는 YouTube 광고 집행 영상을 뜻하지 않습니다.", disclaimers=DISCLAIMERS + ["유료 프로모션 포함 표시는 업로더 고지이며 YouTube 광고 집행 여부가 아닙니다."], summary_markdown="")
        return _render(report)


# ------------------------------------------------------------------------------
# 🎬 [시나리오 3] 경쟁사 최근 콘텐츠 전략 추적
# ------------------------------------------------------------------------------
class CompetitorStrategyParams(BaseModel):
    company: str = Field(description="분석할 경쟁사명")
    start_date: str = Field(default_factory=lambda: str(date.today() - timedelta(days=30)), description="분석 시작일, YYYY-MM-DD")


class CompetitorStrategyScenario(BaseScenario):
    name = "youtube_competitor_strategy"
    description = "경쟁사 공식 YouTube 채널의 최근 업로드에서 제품·메시지 변화를 추적한다."
    parameters_schema = CompetitorStrategyParams
    required_tool_names = ["find_youtube_channel", "get_channel_details", "get_competitor_recent_uploads", "get_video_metrics"]

    def execute(self, params: CompetitorStrategyParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        candidates = _rows(_run(tools, "find_youtube_channel", company_name=params.company))
        selected = _select_channel(candidates, context)
        details = _run(tools, "get_channel_details", channel_id=selected.get("channel_id", ""))
        videos = _rows(_run(tools, "get_competitor_recent_uploads", channel_id=selected.get("channel_id", ""), published_after=f"{params.start_date}T00:00:00Z"))
        metrics = _rows(_run(tools, "get_video_metrics", video_ids=_video_ids(videos)))
        evidence = _evidence(videos, metrics)
        official_name = details.get("channel_name", "") if isinstance(details, dict) else ""
        analysis = ChannelAnalysis(company=params.company, selected_channel=selected, official_channel_evidence=details if isinstance(details, dict) else {}, official_channel_confidence="LLM-selected candidate" if (context or {}).get("llm") else "unverified", videos=evidence, **_activity(videos, params.company), **_ad_trend_signals(videos, evidence, official_name))
        report = YouTubeReport(report_type=f"{params.company} 최근 콘텐츠 전략", period=f"{params.start_date} ~ 현재", channels=[analysis], comparative_analysis=_single_channel_planning_table(analysis, "strategy") + f"\n\n주당 업로드 {analysis.weekly_upload_frequency:.2f}회, 최근 급증 {'감지' if analysis.recent_upload_surge else '미감지'}. 높은 조회수만으로 광고 성과를 단정하지 않습니다.", disclaimers=DISCLAIMERS, summary_markdown="")
        return _render(report)
