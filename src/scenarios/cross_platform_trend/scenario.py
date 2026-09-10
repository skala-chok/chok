import logging
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from src.core.scenario import BaseScenario

logger = logging.getLogger(__name__)


class CrossPlatformTrendParams(BaseModel):
    """크로스 플랫폼 트렌드 분석에 필요한 파라미터."""

    keyword: str = Field(description="분석할 주요 키워드 또는 상품명")
    start_date: str = Field(
        default="2026-01-01",
        description="분석 시작일 (YYYY-MM-DD)",
    )
    end_date: str = Field(
        default="2026-03-01",
        description="분석 종료일 (YYYY-MM-DD)",
    )


class CrossPlatformTrendScenario(BaseScenario):
    """네이버 쇼핑 트렌드와 유튜브 검색 결과를 결합하여 크로스 플랫폼 분석을 수행하는 시나리오."""

    @property
    def name(self) -> str:
        return "cross_platform_trend"

    @property
    def description(self) -> str:
        return (
            "네이버 쇼핑 트렌드 데이터와 유튜브 영상 검색 결과를 교차 분석하여 "
            "특정 키워드/제품의 검색 관심도 추이와 영상 콘텐츠 반응을 종합 리포트로 도출하는 전문 시나리오"
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return CrossPlatformTrendParams

    @property
    def required_tool_names(self) -> List[str]:
        return ["get_shopping_trends", "search_youtube_videos"]

    def execute(
        self,
        params: CrossPlatformTrendParams,
        tools: Dict[str, BaseTool],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """네이버 트렌드와 유튜브 검색을 순차 체이닝하여 종합 인사이트를 생성합니다."""
        logger.info("[시나리오 실행: %s] 대상 키워드: %s", self.name, params.keyword)
        context = context or {}
        llm = context.get("llm")

        # Step 1: 네이버 쇼핑 트렌드 수집
        trend_tool = tools.get("get_shopping_trends")
        trend_result = "네이버 트렌드 도구를 사용할 수 없습니다."
        if trend_tool:
            try:
                trend_result = trend_tool.invoke({
                    "keywords": params.keyword,
                    "start_date": params.start_date,
                    "end_date": params.end_date,
                })
                logger.debug("Step 1 (네이버 트렌드) 완료: %s", trend_result[:100])
            except Exception as e:
                logger.warning("Step 1 (네이버 트렌드) 호출 실패: %s", e)
                trend_result = f"네이버 트렌드 조회 실패: {e}"

        # Step 2: 유튜브 관련 영상 수집
        yt_tool = tools.get("search_youtube_videos")
        yt_result = "유튜브 검색 도구를 사용할 수 없습니다."
        if yt_tool:
            try:
                yt_result = yt_tool.invoke({
                    "query": params.keyword,
                    "max_results": 3,
                })
                logger.debug("Step 2 (유튜브 영상 검색) 완료: %s", yt_result[:100])
            except Exception as e:
                logger.warning("Step 2 (유튜브 검색) 호출 실패: %s", e)
                yt_result = f"유튜브 영상 검색 실패: {e}"

        # Step 3: LLM을 통한 크로스 인사이트 종합 리포트 생성
        if llm:
            prompt = ChatPromptTemplate.from_messages([
                (
                    "system",
                    "당신은 이커머스 및 미디어 트렌드 전문 분석가입니다.\n"
                    "네이버 쇼핑 트렌드 지표와 유튜브 검색 결과를 바탕으로 다각도 크로스 분석 리포트를 작성하십시오.\n"
                    "리포트 구성:\n"
                    "1. [개요 및 핵심 요약]\n"
                    "2. [네이버 쇼핑 검색 트렌드 분석]\n"
                    "3. [유튜브 미디어 반응 분석]\n"
                    "4. [종합 마케팅/비즈니스 시사점]",
                ),
                (
                    "human",
                    "키워드: {keyword}\n"
                    "분석 기간: {start_date} ~ {end_date}\n\n"
                    "[네이버 쇼핑 트렌드 데이터]\n{trend_data}\n\n"
                    "[유튜브 관련 영상 데이터]\n{yt_data}",
                ),
            ])
            chain = prompt | llm
            try:
                ai_response = chain.invoke({
                    "keyword": params.keyword,
                    "start_date": params.start_date,
                    "end_date": params.end_date,
                    "trend_data": trend_result,
                    "yt_data": yt_result,
                })
                report_content = ai_response.content if hasattr(ai_response, "content") else str(ai_response)
                return report_content
            except Exception as e:
                logger.warning("Step 3 (LLM 리포트 생성) 실패: %s -> 기본 데이터 포맷팅 반환", e)

        # Fallback: LLM 미사용 또는 실패 시 원본 수집 데이터 정렬 반환
        return (
            f"### [{params.keyword}] 크로스 플랫폼 트렌드 분석 결과\n\n"
            f"**분석 기간**: {params.start_date} ~ {params.end_date}\n\n"
            f"#### 1. 네이버 쇼핑 트렌드\n{trend_result}\n\n"
            f"#### 2. 유튜브 관련 영상\n{yt_result}"
        )
