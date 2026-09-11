# ==============================================================================
# 🌈 [Scenario 개발 레인보우 로드맵]
# 🔴 [Step 1 - 빨간점] Pydantic 파라미터 스키마 정의 (LLM 라우터가 추출할 인자 규격)
# 🟠 [Step 2 - 주황점] BaseScenario 상속 및 메타데이터(name, description, required_tool_names) 선언
# 🟡 [Step 3 - 노란점] execute() 내 정예 도구 순차/병렬 체이닝 파이프라인 작성
# 🟢 [Step 4 - 초록점] LLM 크로스 인사이트 리포트 생성 및 예외 폴백 처리
# 🔵 [Step 5 - 파란점] tests/core/test_scenario.py 에 단위 테스트 추가
# ==============================================================================

import logging
import re
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from src.core.scenario import BaseScenario

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# 🔴 [Step 1 - 빨간점] Pydantic 파라미터 스키마 정의
# ------------------------------------------------------------------------------
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


# ------------------------------------------------------------------------------
# 🟠 [Step 2 - 주황점] BaseScenario 상속 및 메타데이터 선언
# ------------------------------------------------------------------------------
class CrossPlatformTrendScenario(BaseScenario):
    """네이버 쇼핑 트렌드, 유튜브 영상 및 인스타그램 해시태그를 결합하여 크로스 플랫폼 분석을 수행하는 시나리오."""

    @property
    def name(self) -> str:
        return "cross_platform_trend"

    @property
    def description(self) -> str:
        return (
            "네이버 쇼핑 트렌드 데이터, 유튜브 영상 검색 결과, 인스타그램 해시태그 소셜 반응을 교차 분석하여 "
            "특정 키워드/제품의 검색 관심도 추이와 영상 콘텐츠 및 SNS 반응을 종합 리포트로 도출하는 전문 시나리오"
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return CrossPlatformTrendParams

    @property
    def required_tool_names(self) -> List[str]:
        return [
            "get_shopping_trends",
            "search_youtube_videos",
            "search_hashtag_id",
            "get_hashtag_top_media",
        ]

    # --------------------------------------------------------------------------
    # 🟡 [Step 3 - 노란점] execute() 내 정예 도구 체이닝 & 🟢 [Step 4 - 초록점] 종합 리포트
    # --------------------------------------------------------------------------
    def execute(
        self,
        params: CrossPlatformTrendParams,
        tools: Dict[str, BaseTool],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """네이버 트렌드, 유튜브 검색, 인스타그램 해시태그를 순차 체이닝하여 종합 인사이트를 생성합니다."""
        context = context or {}
        llm = context.get("llm")

        # 🟡 [Step 3-1] 도구 호출: 네이버 쇼핑 트렌드 수집
        trend_tool = tools.get("get_shopping_trends")
        trend_result = "네이버 트렌드 도구를 사용할 수 없습니다."
        if trend_tool:
            try:
                trend_result = trend_tool.invoke({
                    "keywords": params.keyword,
                    "start_date": params.start_date,
                    "end_date": params.end_date,
                })
                logger.debug("Step 3-1 (네이버 트렌드) 완료: %s", trend_result[:100] if isinstance(trend_result, str) else trend_result)
            except Exception as e:
                logger.warning("Step 3-1 (네이버 트렌드) 호출 실패: %s", e)
                trend_result = f"네이버 트렌드 조회 실패: {e}"

        # 🟡 [Step 3-2] 도구 호출: 유튜브 관련 영상 수집
        yt_tool = tools.get("search_youtube_videos")
        yt_result = "유튜브 검색 도구를 사용할 수 없습니다."
        if yt_tool:
            try:
                yt_result = yt_tool.invoke({
                    "query": params.keyword,
                    "max_results": 3,
                })
                logger.debug("Step 3-2 (유튜브 영상 검색) 완료: %s", yt_result[:100] if isinstance(yt_result, str) else yt_result)
            except Exception as e:
                logger.warning("Step 3-2 (유튜브 검색) 호출 실패: %s", e)
                yt_result = f"유튜브 영상 검색 실패: {e}"

        # 🟡 [Step 3-3] 도구 호출: 인스타그램 해시태그 인기 반응 수집
        ig_search_tool = tools.get("search_hashtag_id")
        ig_top_tool = tools.get("get_hashtag_top_media")
        ig_result = "인스타그램 도구를 사용할 수 없습니다."

        clean_tag = params.keyword.strip().lstrip("#").replace(" ", "")
        hashtag_id = None

        if ig_search_tool:
            try:
                search_res = ig_search_tool.invoke({"query": clean_tag})
                id_match = re.search(r"해시태그 ID:\s*([0-9a-zA-Z_]+)", str(search_res))
                if id_match:
                    hashtag_id = id_match.group(1).strip()
                logger.debug("Step 3-3 (인스타그램 해시태그 ID 조회) 완료: ID=%s", hashtag_id)
            except Exception as e:
                logger.warning("Step 3-3 (인스타그램 ID 조회) 호출 실패: %s", e)

        if not hashtag_id:
            hashtag_id = f"ht_{clean_tag}"

        if ig_top_tool:
            try:
                top_res = ig_top_tool.invoke({"hashtag_id": hashtag_id})
                ig_result = str(top_res)
                logger.debug("Step 3-3 (인스타그램 인기 미디어) 완료: %s", ig_result[:100])
            except Exception as e:
                logger.warning("Step 3-3 (인스타그램 미디어 조회) 호출 실패: %s", e)
                ig_result = f"인스타그램 해시태그 반응 조회 실패: {e}"

        # 🟢 [Step 4 - 초록점] LLM을 통한 크로스 인사이트 종합 리포트 생성
        if llm:
            prompt = ChatPromptTemplate.from_messages([
                (
                    "system",
                    "당신은 이커머스 및 미디어 트렌드 전문 분석가입니다.\n"
                    "네이버 쇼핑 트렌드 지표, 유튜브 검색 결과, 인스타그램 해시태그 소셜 반응을 바탕으로 다각도 크로스 분석 리포트를 작성하십시오.\n"
                    "리포트 구성:\n"
                    "1. [개요 및 핵심 요약]\n"
                    "2. [네이버 쇼핑 검색 트렌드 분석]\n"
                    "3. [유튜브 미디어 반응 분석]\n"
                    "4. [인스타그램 해시태그 소셜 반응 분석]\n"
                    "5. [종합 마케팅/비즈니스 시사점]",
                ),
                (
                    "human",
                    "키워드: {keyword}\n"
                    "분석 기간: {start_date} ~ {end_date}\n\n"
                    "[네이버 쇼핑 트렌드 데이터]\n{trend_data}\n\n"
                    "[유튜브 관련 영상 데이터]\n{yt_data}\n\n"
                    "[인스타그램 해시태그 소셜 반응 데이터]\n{ig_data}",
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
                    "ig_data": ig_result,
                })
                report_content = ai_response.content if hasattr(ai_response, "content") else str(ai_response)
                return report_content
            except Exception as e:
                logger.warning("Step 4 (LLM 리포트 생성) 실패: %s -> 기본 데이터 포맷팅 반환", e)

        # Fallback: LLM 미사용 또는 실패 시 원본 수집 데이터 정렬 반환
        return (
            f"### [{params.keyword}] 크로스 플랫폼 트렌드 분석 결과\n\n"
            f"**분석 기간**: {params.start_date} ~ {params.end_date}\n\n"
            f"#### 1. 네이버 쇼핑 트렌드\n{trend_result}\n\n"
            f"#### 2. 유튜브 관련 영상\n{yt_result}\n\n"
            f"#### 3. 인스타그램 해시태그 반응\n{ig_result}"
        )
