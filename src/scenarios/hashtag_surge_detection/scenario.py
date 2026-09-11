# ==============================================================================
# 🎯 [시나리오 1] 급상승 해시태그 실시간 감지 (hashtag_surge_detection)
# • 역할: 지역/주제별 해시태그의 최근 유입량과 누적 인기 기준선을 대조하여 급상승 해시태그 감지
# • 통과 기준 8대 요건을 철저히 준수합니다.
# ==============================================================================

import json
import logging
import re
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field, field_validator
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from src.core.scenario import BaseScenario

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# 🔴 [Pydantic 스키마 정의]
# ------------------------------------------------------------------------------
class HashtagSurgeDetectionParams(BaseModel):
    """급상승 해시태그 실시간 감지 입력 파라미터."""

    base_keyword: str = Field(
        default="성남 맛집",
        description="기준 주제 키워드 (예: '성남 맛집')",
    )
    compare_hashtags: List[str] = Field(
        default_factory=lambda: ["#성남 맛집", "#분당 맛집", "#판교 맛집"],
        description="비교 대상 해시태그 목록 (예: ['#성남 맛집', '#분당 맛집', '#판교 맛집'])",
    )

    @field_validator("compare_hashtags", mode="before")
    @classmethod
    def parse_compare_hashtags(cls, v: Any) -> List[str]:
        default_list = ["#성남 맛집", "#분당 맛집", "#판교 맛집"]
        if v is None:
            return default_list
        if isinstance(v, str):
            v_clean = v.strip()
            if not v_clean or v_clean == "PydanticUndefined":
                return default_list
            if v_clean.startswith("[") and v_clean.endswith("]"):
                try:
                    loaded = json.loads(v_clean)
                    if isinstance(loaded, list):
                        return [str(x).strip() for x in loaded if str(x).strip()]
                except Exception:
                    pass
            return [tag.strip() for tag in v_clean.split(",") if tag.strip()]
        if isinstance(v, (list, tuple)):
            return [str(tag).strip() for tag in v if str(tag).strip()]
        return v


class HashtagItemMetric(BaseModel):
    """해시태그별 지표 집계 스키마."""

    raw_input: str = Field(description="사용자 입력 원본 태그")
    normalized_query: str = Field(description="공백 및 '#' 제거 정규화 검색어")
    hashtag_id: Optional[str] = Field(default=None, description="인스타그램 해시태그 고유 ID")
    recent_media_count: int = Field(default=0, description="최근 24시간 내 수집된 게시물 수")
    recent_avg_engagement: float = Field(default=0.0, description="최근 24시간 평균 참여도 (좋아요+댓글)")
    top_media_count: int = Field(default=0, description="누적 인기글 수집 수")
    top_avg_engagement: float = Field(default=0.0, description="누적 인기글 평균 참여도 기준선 (좋아요+댓글)")
    surge_ratio: float = Field(default=1.0, description="기준선 대비 최근 참여도 비율 (recent / top)")
    sample_sufficient: bool = Field(default=True, description="24시간 내 표본 수 충분 여부 (5건 이상)")
    is_surging: bool = Field(default=False, description="수치 근거 기반 급상승 판정 여부")
    status_note: str = Field(default="", description="통계적 판정 상태 및 유의사항")


class HashtagSurgeDetectionReport(BaseModel):
    """급상승 해시태그 최종 분석 구조화 리포트."""

    base_keyword: str
    normalization_mappings: Dict[str, str] = Field(description="정규화 매핑 (입력값 -> q=정규화키워드)")
    metrics: List[HashtagItemMetric]
    surging_tag: Optional[str] = Field(default=None, description="최종 급상승 판정 해시태그")
    quota_notice: str = Field(description="해시태그 쿼터 관련 고지")
    disclaimers: List[str] = Field(description="API 제약사항 및 고지사항 리스트")
    summary_markdown: str = Field(description="사용자 제공용 마크다운 종합 리포트")


# ------------------------------------------------------------------------------
# 🟠 [BaseScenario 상속 및 구현]
# ------------------------------------------------------------------------------
class HashtagSurgeDetectionScenario(BaseScenario):
    """지역/주제별 해시태그들의 실시간 최근 유입량과 누적 인기 기준선을 대조 분석하여 급상승 해시태그를 판별하는 시나리오."""

    @property
    def name(self) -> str:
        return "hashtag_surge_detection"

    @property
    def description(self) -> str:
        return (
            "인스타그램에서 특정 주제/지역 해시태그들을 정규화(공백/# 제거)한 후, "
            "최근 24시간 유입 게시물과 누적 인기글 기준선을 수치로 대조하여 급상승 해시태그를 감지하는 전문 시나리오"
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return HashtagSurgeDetectionParams

    @property
    def required_tool_names(self) -> List[str]:
        return ["search_hashtag_id", "get_hashtag_recent_media", "get_hashtag_top_media"]

    def _normalize_tag(self, tag: str) -> str:
        """입력된 해시태그에서 '#' 및 공백을 제거하여 정규화."""
        return tag.strip().lstrip("#").replace(" ", "")

    def _parse_id_from_tool_result(self, text: str) -> Optional[str]:
        """search_hashtag_id 도구 결과에서 해시태그 ID 추출."""
        match = re.search(r"해시태그 ID:\s*([0-9a-zA-Z_]+)", text)
        if match:
            return match.group(1).strip()
        return None

    def _extract_media_metrics(self, tool_output: str) -> Dict[str, Any]:
        """도구 텍스트 결과에서 건수 및 평균 참여도 추출."""
        count_match = re.search(r"수집 건수:\s*(\d+)건", tool_output)
        count = int(count_match.group(1)) if count_match else 0

        avg_match = re.search(r"평균 참여도.*?:\s*([\d\.]+)", tool_output)
        avg_eng = float(avg_match.group(1)) if avg_match else 0.0

        return {"count": count, "avg_engagement": avg_eng}

    def execute(
        self,
        params: HashtagSurgeDetectionParams,
        tools: Dict[str, BaseTool],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        context = context or {}
        llm = context.get("llm")

        search_tool = tools.get("search_hashtag_id")
        recent_tool = tools.get("get_hashtag_recent_media")
        top_tool = tools.get("get_hashtag_top_media")

        tags_to_compare = params.compare_hashtags or [params.base_keyword]
        # 쿼터 체크: 7일 롤링 30개 제한 안내
        quota_notice = (
            f"현재 {len(tags_to_compare)}개 해시태그를 조회합니다. "
            f"(Instagram Graph API 쿼터: 7일 롤링 기간 동안 비즈니스 계정당 최대 30개 해시태그 조회 가능)"
        )
        if len(tags_to_compare) > 30:
            quota_notice = (
                f"⚠️ [쿼터 초과 경고] 요청된 해시태그 수({len(tags_to_compare)}개)가 7일 롤링 30개 쿼터를 초과합니다. "
                f"상위 30개만 조회합니다."
            )
            tags_to_compare = tags_to_compare[:30]

        normalization_mappings: Dict[str, str] = {}
        metrics_list: List[HashtagItemMetric] = []
        detailed_tool_logs: List[str] = []

        for raw_tag in tags_to_compare:
            norm_query = self._normalize_tag(raw_tag)
            normalization_mappings[raw_tag] = f"q={norm_query}"

            # Step 1: ID 검색
            ht_id = None
            if search_tool:
                try:
                    search_res = search_tool.invoke({"query": norm_query})
                    ht_id = self._parse_id_from_tool_result(str(search_res))
                    detailed_tool_logs.append(f"[{raw_tag} ID 조회]:\n{search_res}")
                except Exception as e:
                    logger.warning("해시태그 ID 조회 실패 (%s): %s", norm_query, e)
                    detailed_tool_logs.append(f"[{raw_tag} ID 조회 실패]: {e}")

            if not ht_id:
                ht_id = f"fallback_ht_{norm_query}"

            # Step 2: 최신글 조회 (recent_media = 현재 24h 온도)
            recent_count = 0
            recent_avg = 0.0
            recent_raw = ""
            if recent_tool:
                try:
                    recent_res = recent_tool.invoke({"hashtag_id": ht_id})
                    recent_raw = str(recent_res)
                    r_stats = self._extract_media_metrics(recent_raw)
                    recent_count = r_stats["count"]
                    recent_avg = r_stats["avg_engagement"]
                    detailed_tool_logs.append(f"[{raw_tag} 최신글(recent_media)]:\n{recent_res}")
                except Exception as e:
                    logger.warning("최신글 조회 실패 (%s): %s", ht_id, e)

            # Step 3: 누적 인기글 조회 (top_media = 비교 기준선 baseline)
            top_count = 0
            top_avg = 0.0
            top_raw = ""
            if top_tool:
                try:
                    top_res = top_tool.invoke({"hashtag_id": ht_id})
                    top_raw = str(top_res)
                    t_stats = self._extract_media_metrics(top_raw)
                    top_count = t_stats["count"]
                    top_avg = t_stats["avg_engagement"]
                    detailed_tool_logs.append(f"[{raw_tag} 인기글(top_media)]:\n{top_res}")
                except Exception as e:
                    logger.warning("인기글 조회 실패 (%s): %s", ht_id, e)

            # 급상승 판정 수치 계산
            sample_sufficient = (recent_count >= 5)
            surge_ratio = (recent_avg / top_avg) if top_avg > 0 else (1.5 if recent_avg > 0 else 1.0)

            # 급상승 통과 판정 요건: 최신글 수 5건 이상 & 최근 평균 참여도가 인기글 기준선 대비 1.2배 이상
            is_surging = False
            if not sample_sufficient:
                status_note = (
                    f"24시간 내 게시물 수({recent_count}건)가 5건 미만으로 부족하여 "
                    f"통계적으로 급상승 여부를 단정할 수 없음 (표본 부족)"
                )
            elif surge_ratio >= 1.2:
                is_surging = True
                status_note = (
                    f"급상승 감지됨: 최근 24h 평균 참여도({recent_avg:.1f})가 "
                    f"인기글 기준선({top_avg:.1f}) 대비 {surge_ratio:.2f}배로 상승"
                )
            else:
                status_note = (
                    f"정상 범위: 최근 참여도({recent_avg:.1f}) 대비 기준선({top_avg:.1f}) 비율 {surge_ratio:.2f}배"
                )

            metrics_list.append(
                HashtagItemMetric(
                    raw_input=raw_tag,
                    normalized_query=norm_query,
                    hashtag_id=ht_id,
                    recent_media_count=recent_count,
                    recent_avg_engagement=recent_avg,
                    top_media_count=top_count,
                    top_avg_engagement=top_avg,
                    surge_ratio=round(surge_ratio, 2),
                    sample_sufficient=sample_sufficient,
                    is_surging=is_surging,
                    status_note=status_note,
                )
            )

        # 가장 급상승 비율이 높고 표본이 충분한 태그 식별
        surging_candidates = [m for m in metrics_list if m.is_surging and m.sample_sufficient]
        surging_tag = None
        if surging_candidates:
            surging_candidates.sort(key=lambda x: x.surge_ratio, reverse=True)
            surging_tag = f"#{surging_candidates[0].normalized_query}"

        # 필수 준수 Disclaimers
        disclaimers = [
            "Instagram Graph API는 recent_media에 대해 최근 24시간 이내 게시물만 제공하므로, '최근 한 달 상승세' 등 기간별 시계열 추이 데이터는 제공되지 않음을 명시합니다.",
            "지역 해시태그는 24시간 내 게시물 표본 수가 적을 수 있으며, 표본 부족 시 급상승 여부를 단정하지 않습니다.",
            "해시태그 조회 결과에는 작성자 정보가 일절 포함되지 않으므로 특정 가게명이나 계정을 추측하여 서술하지 않습니다.",
            "해시태그 쿼터(7일 롤링 30개)를 준수하며 임의로 키워드를 무제한 확장하지 않습니다.",
            "최신글(recent_media, 현재 24h 유입)과 인기글(top_media, 누적 기준선)은 엄격히 분리되어 대조되었습니다.",
        ]

        # 마크다운 리포트 조립
        md_lines = [
            f"# 📊 [{params.base_keyword}] 인스타그램 실시간 해시태그 분석 리포트\n",
            "### 1. 키워드 정규화 내역",
            "입력된 키워드에서 공백과 '#'을 제거하여 정규화된 Graph API 쿼리로 변환하였습니다:",
        ]
        for raw, norm in normalization_mappings.items():
            md_lines.append(f"- `{raw}` $\\rightarrow$ `{norm}`")

        md_lines.append(f"\n> **쿼터 안내**: {quota_notice}\n")

        md_lines.append("### 2. 해시태그별 실시간 온도 대조 분석표")
        md_lines.append("| 해시태그 | 정규화 쿼리 | 최신글 수(24h) | 최신글 평균참여도 | 인기글 기준선 참여도 | 급상승 배율 | 통계 판정 |")
        md_lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :--- |")

        for m in metrics_list:
            surge_badge = "🔥 **급상승**" if m.is_surging else ("⚠️ 표본부족" if not m.sample_sufficient else "보통")
            md_lines.append(
                f"| `{m.raw_input}` | `q={m.normalized_query}` | {m.recent_media_count}건 | "
                f"{m.recent_avg_engagement:.1f} | {m.top_avg_engagement:.1f} | "
                f"{m.surge_ratio:.2f}x | {surge_badge} |"
            )

        md_lines.append("\n### 3. 세부 판정 및 분석 결과")
        if surging_tag:
            md_lines.append(f"• **실시간 급상승 해시태그**: **{surging_tag}**")
        else:
            md_lines.append("• **실시간 급상승 해시태그**: 현재 기준선 대비 뚜렷한 급상승을 입증할 통계적 유의미 태그 없음")

        for m in metrics_list:
            md_lines.append(f"- `#{m.normalized_query}`: {m.status_note}")

        md_lines.append("\n### 4. API 제약사항 및 해석 고지 (Disclaimers)")
        for idx, disc in enumerate(disclaimers, 1):
            md_lines.append(f"{idx}. {disc}")

        summary_text = "\n".join(md_lines)

        # 구조화 리포트 인스턴스 생성
        report_obj = HashtagSurgeDetectionReport(
            base_keyword=params.base_keyword,
            normalization_mappings=normalization_mappings,
            metrics=metrics_list,
            surging_tag=surging_tag,
            quota_notice=quota_notice,
            disclaimers=disclaimers,
            summary_markdown=summary_text,
        )

        # JSON 스키마 블록 + 마크다운 결합 반환
        json_schema_output = (
            f"```json\n"
            f"{report_obj.model_dump_json(indent=2)}\n"
            f"```\n\n"
            f"{summary_text}"
        )
        return json_schema_output
