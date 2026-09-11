import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.core.scenario import BaseScenario


def _ids(output: str, pattern: str) -> List[str]:
    return re.findall(pattern, output)


def _run(tools: Dict[str, BaseTool], name: str, **kwargs: Any) -> str:
    tool = tools.get(name)
    return tool.invoke(kwargs) if tool else f"{name} 도구를 사용할 수 없습니다."


class CompetitorComparisonParams(BaseModel):
    company_a: str = Field(description="첫 번째 비교 회사명")
    company_b: str = Field(description="두 번째 비교 회사명")
    start_date: str = Field(description="분석 시작일, YYYY-MM-DD")
    end_date: str = Field(description="분석 종료일, YYYY-MM-DD")


class CompetitorComparisonScenario(BaseScenario):
    @property
    def name(self) -> str:
        return "youtube_competitor_comparison"

    @property
    def description(self) -> str:
        return "두 회사의 공식 YouTube 채널 광고 콘텐츠를 동일 기간의 공개 반응 지표로 비교한다."

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return CompetitorComparisonParams

    @property
    def required_tool_names(self) -> List[str]:
        return ["find_youtube_channel", "get_channel_videos", "get_video_metrics"]

    def execute(self, params: CompetitorComparisonParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        channels = [_run(tools, "find_youtube_channel", company=company) for company in (params.company_a, params.company_b)]
        channel_ids = [_ids(result, r"채널ID: ([\\w-]+)")[0] if _ids(result, r"채널ID: ([\\w-]+)") else "" for result in channels]
        videos = [_run(tools, "get_channel_videos", channel_id=channel_id, start_date=params.start_date, end_date=params.end_date) for channel_id in channel_ids]
        metrics = [_run(tools, "get_video_metrics", video_ids=_ids(result, r"watch\\?v=([\\w-]+)")) for result in videos]
        return (
            f"### {params.company_a} vs {params.company_b} YouTube 광고 콘텐츠 비교\n"
            f"기간: {params.start_date} ~ {params.end_date} (동일 기간 적용)\n\n"
            f"#### {params.company_a} 공식 채널 후보\n{channels[0]}\n{videos[0]}\n{metrics[0]}\n\n"
            f"#### {params.company_b} 공식 채널 후보\n{channels[1]}\n{videos[1]}\n{metrics[1]}\n\n"
            "참여율과 일평균 조회수는 공개 반응 지표입니다. 광고비 또는 광고 효율을 뜻하지 않습니다."
        )


class PaidPromotionParams(BaseModel):
    keyword: str = Field(description="탐색할 제품군 키워드")
    start_date: str = Field(default_factory=lambda: str(date.today() - timedelta(days=30)), description="분석 시작일, YYYY-MM-DD")


class PaidPromotionScenario(BaseScenario):
    @property
    def name(self) -> str:
        return "youtube_paid_promotion_discovery"

    @property
    def description(self) -> str:
        return "제품군의 최근 유료 프로모션 포함 표시 YouTube 콘텐츠와 공개 반응 지표를 탐색한다."

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return PaidPromotionParams

    @property
    def required_tool_names(self) -> List[str]:
        return ["search_paid_promotion_videos", "get_video_metrics"]

    def execute(self, params: PaidPromotionParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        videos = _run(tools, "search_paid_promotion_videos", query=params.keyword, start_date=params.start_date)
        metrics = _run(tools, "get_video_metrics", video_ids=_ids(videos, r"watch\\?v=([\\w-]+)"))
        return (
            f"### {params.keyword} 유료 프로모션 포함 표시 콘텐츠\n기간: {params.start_date} ~ 현재\n\n"
            f"{videos}\n\n공개 반응 지표\n{metrics}\n\n"
            "이 결과는 유료 프로모션 포함으로 표시된 콘텐츠이며, YouTube 광고 집행 영상 또는 광고 성과를 뜻하지 않습니다."
        )


class CompetitorStrategyParams(BaseModel):
    company: str = Field(description="분석할 경쟁사명")
    start_date: str = Field(default_factory=lambda: str(date.today() - timedelta(days=30)), description="분석 시작일, YYYY-MM-DD")


class CompetitorStrategyScenario(BaseScenario):
    @property
    def name(self) -> str:
        return "youtube_competitor_strategy"

    @property
    def description(self) -> str:
        return "경쟁사 공식 YouTube 채널의 최근 업로드에서 제품, 메시지, 소구점 변화를 추적한다."

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return CompetitorStrategyParams

    @property
    def required_tool_names(self) -> List[str]:
        return ["find_youtube_channel", "get_competitor_recent_uploads", "get_video_metrics"]

    def execute(self, params: CompetitorStrategyParams, tools: Dict[str, BaseTool], context: Optional[Dict[str, Any]] = None) -> str:
        channels = _run(tools, "find_youtube_channel", company=params.company)
        channel_ids = _ids(channels, r"채널ID: ([\\w-]+)")
        videos = _run(tools, "get_competitor_recent_uploads", channel_id=channel_ids[0] if channel_ids else "", start_date=params.start_date)
        metrics = _run(tools, "get_video_metrics", video_ids=_ids(videos, r"watch\\?v=([\\w-]+)"))
        return (
            f"### {params.company} 최근 콘텐츠 전략\n기간: {params.start_date} ~ 현재\n\n"
            f"공식 채널 후보\n{channels}\n\n최근 업로드\n{videos}\n\n공개 반응 지표\n{metrics}\n\n"
            "반복 제품명·주제·소구점은 위 영상 제목과 설명을 기준으로 해석하십시오. 높은 조회수는 실제 광고 성과를 단정하지 않습니다."
        )
