import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.core.scenario import BaseScenario

_TITLE_RE = re.compile(r"^\[(.+?)\]$")
_POINT_RE = re.compile(r"^\s*-\s*([\d-]+)(?:\s*\(([^)]+)\))?:\s*([\d.]+)\s*$")
_CANDIDATE_CODE_RE = re.compile(r"category_code=(\d+)")


def _run(tools: Dict[str, BaseTool], name: str, **kwargs: Any) -> str:
    tool = tools.get(name)
    return tool.invoke(kwargs) if tool else f"{name} 도구를 사용할 수 없습니다."


def _resolve_category_code(tools: Dict[str, BaseTool], search_term: str, given_code: str) -> Tuple[str, Optional[str]]:
    """라우터(LLM)가 추측한 category_code를 find_naver_category_code로 실제 검증/정정한다.

    라우터는 Tool 호출 없이 파라미터를 직접 추측하기 때문에, Pydantic Field의 예시 숫자를
    그대로 베끼거나 존재하지 않는 코드를 만들어내는 경우가 있다. 이 함수는 그 값을 절대
    그대로 신뢰하지 않고, search_term(분야명 또는 키워드)으로 실제 후보를 다시 조회해서
    given_code가 그 후보에 없으면 조회된 코드로 교체한다.

    Returns:
        (사용할 category_code, 정정/실패 시 사용자에게 보여줄 안내 문구 또는 None).
    """
    raw = _run(tools, "find_naver_category_code", keyword=search_term)
    candidates = _CANDIDATE_CODE_RE.findall(raw)
    if not candidates:
        note = (
            f"⚠️ '{search_term}'에 대한 category_code를 자동 조회로 검증하지 못했습니다 "
            f"(조회 결과 없음). 제공된 코드({given_code or '없음'})를 그대로 사용하며, 정확하지 않을 수 있습니다."
        )
        return given_code, note
    if given_code and given_code in candidates:
        return given_code, None
    corrected = candidates[0]
    if given_code:
        note = f"⚠️ category_code 자동 정정: 추정된 코드({given_code})는 '{search_term}'의 실제 카테고리와 일치하지 않아 조회된 코드({corrected})로 교체했습니다."
    else:
        note = f"ℹ️ category_code가 주어지지 않아 '{search_term}' 키워드로 자동 조회한 코드({corrected})를 사용합니다."
    if len(candidates) > 1:
        note += f" (다른 후보: {', '.join(candidates[1:])})"
    return corrected, note


def _pick_search_term(*candidates: str) -> str:
    """category_name 등 1순위 후보가 비어 있으면 다음 후보(키워드 등)로 넘어간다."""
    for c in candidates:
        if c and c.strip():
            return c.strip()
    return ""


def _parse_series(text: str) -> Dict[str, List[Tuple[str, Optional[str], float]]]:
    """get_shopping_*_trend 계열 Tool이 반환하는 텍스트를 {title: [(period, group, ratio), ...]}로 역파싱한다."""
    series: Dict[str, List[Tuple[str, Optional[str], float]]] = {}
    current_title: Optional[str] = None
    for line in text.splitlines():
        title_match = _TITLE_RE.match(line.strip())
        if title_match:
            current_title = title_match.group(1)
            series[current_title] = []
            continue
        point_match = _POINT_RE.match(line)
        if point_match and current_title is not None:
            period, group, ratio = point_match.groups()
            series[current_title].append((period, group, float(ratio)))
    return series


def _trend_direction(points: List[Tuple[str, Optional[str], float]]) -> str:
    """구간 시작 대비 종료 시점의 ratio 변화로 추세를 판정한다 (±5 이내는 보합)."""
    if len(points) < 2:
        return "판단 불가 (구간 내 데이터 부족)"
    first_ratio = points[0][2]
    last_ratio = points[-1][2]
    diff = last_ratio - first_ratio
    if diff > 5:
        return f"상승 ({first_ratio} → {last_ratio})"
    if diff < -5:
        return f"하락 ({first_ratio} → {last_ratio})"
    return f"보합 ({first_ratio} → {last_ratio})"


def _top_segment(points: List[Tuple[str, Optional[str], float]]) -> Optional[Tuple[str, float]]:
    """group별(성별/연령대) 최댓값을 비교해 가장 관심도가 높은 세그먼트를 찾는다."""
    grouped: Dict[str, float] = {}
    for _period, group, ratio in points:
        if group is None:
            continue
        grouped[group] = max(grouped.get(group, 0.0), ratio)
    if not grouped:
        return None
    top_group = max(grouped, key=grouped.get)
    return top_group, grouped[top_group]


def _default_start() -> str:
    return str(date.today() - timedelta(days=90))


def _default_end() -> str:
    return str(date.today())


class NewProductKeywordTrendParams(BaseModel):
    category_name: str = Field(
        default="", description="네이버쇼핑 분야명 (예: '스킨/토너'). 모르면 비워둬도 됩니다 (keywords로 대신 조회)."
    )
    category_code: str = Field(
        default="",
        description=(
            "네이버쇼핑 분야 코드. 정확한 숫자를 모르면 절대 추측해서 채우지 말고 빈 문자열로 두십시오 "
            "(시나리오 실행 시 category_name으로 자동 조회·검증됩니다)."
        ),
    )
    keywords: str = Field(description="비교할 세부 키워드, 쉼표로 구분 (예: '수분스킨,저자극스킨,맨즈스킨'), 최대 5개")
    start_date: str = Field(default_factory=_default_start, description="분석 시작일, YYYY-MM-DD (기본: 최근 3개월)")
    end_date: str = Field(default_factory=_default_end, description="분석 종료일, YYYY-MM-DD")


class NewProductKeywordTrendScenario(BaseScenario):
    """신제품 마케팅 준비를 위해 분야 전체 트렌드와 세부 키워드 관심도를 함께 조사한다."""

    @property
    def name(self) -> str:
        return "naver_new_product_keyword_trend"

    @property
    def description(self) -> str:
        return "신제품 마케팅을 준비할 때 네이버쇼핑 분야 트렌드와 통합검색·쇼핑 영역 기준 세부 키워드 관심도를 함께 조사한다."

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return NewProductKeywordTrendParams

    @property
    def required_tool_names(self) -> List[str]:
        return [
            "find_naver_category_code",
            "get_shopping_category_trend",
            "get_shopping_trends",
            "get_shopping_keyword_trend",
        ]

    def execute(
        self,
        params: NewProductKeywordTrendParams,
        tools: Dict[str, BaseTool],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        kw_list = [k.strip() for k in params.keywords.split(",") if k.strip()]
        search_term = _pick_search_term(params.category_name, *kw_list)
        display_name = params.category_name or search_term or "(분야 미지정)"

        if not search_term:
            return (
                "### 신제품 키워드 트렌드 조사\n"
                "❌ category_name과 keywords가 모두 비어 있어 카테고리를 조회할 수 없습니다. "
                "분야명이나 상품 키워드를 알려주세요."
            )

        category_code, code_note = _resolve_category_code(tools, search_term, params.category_code)
        if not category_code:
            note_block = f"{code_note}\n\n" if code_note else ""
            return (
                f"### [{display_name}] 신제품 키워드 트렌드 조사\n"
                f"{note_block}"
                "❌ category_code를 확정하지 못해 분야/키워드별 조회를 진행할 수 없습니다. "
                "정확한 네이버쇼핑 분야명이나 category_code를 알려주세요."
            )

        category_arg = f"{display_name}:{category_code}"
        category_result = _run(
            tools, "get_shopping_category_trend",
            categories=category_arg, start_date=params.start_date, end_date=params.end_date,
        )

        overall_keywords = params.keywords if kw_list else search_term
        overall_result = _run(
            tools, "get_shopping_trends",
            keywords=overall_keywords, start_date=params.start_date, end_date=params.end_date,
        )

        kw_pairs = ",".join(f"{kw}:{kw}" for kw in kw_list) if kw_list else f"{search_term}:{search_term}"
        keyword_result = _run(
            tools, "get_shopping_keyword_trend",
            category_code=category_code, keywords=kw_pairs,
            start_date=params.start_date, end_date=params.end_date,
        )

        keyword_series = _parse_series(keyword_result)
        direction_lines = [f"- {title}: {_trend_direction(points)}" for title, points in keyword_series.items()]
        direction_summary = "\n".join(direction_lines) if direction_lines else "- 판단 불가 (데이터 없음)"

        note_block = f"{code_note}\n\n" if code_note else ""
        return (
            f"### [{display_name}] 신제품 키워드 트렌드 조사\n"
            f"{note_block}"
            f"기간: {params.start_date} ~ {params.end_date} | 사용된 category_code: {category_code}\n\n"
            f"#### 1. 분야 전체 트렌드 (쇼핑 영역)\n{category_result}\n\n"
            f"#### 2. 통합검색 기준 키워드 전체 관심도\n{overall_result}\n\n"
            f"#### 3. 쇼핑 영역 기준 세부 키워드 비교\n{keyword_result}\n\n"
            f"#### 4. 추세 판정 (구간 시작 대비 종료 시점, ±5 이내는 보합)\n{direction_summary}\n\n"
            "ratio는 조회 구간 내 최댓값을 100으로 정규화한 상대값이며, 절대 검색량이 아닙니다. "
            "통합검색 기준과 쇼핑 영역 기준은 서로 다른 모수이므로 직접 비교하지 마십시오."
        )


class TargetAudienceValidationParams(BaseModel):
    category_name: str = Field(
        default="", description="네이버쇼핑 분야명 (예: '스킨/토너'). 모르면 비워둬도 됩니다 (keyword로 대신 조회)."
    )
    category_code: str = Field(
        default="",
        description=(
            "네이버쇼핑 분야 코드. 정확한 숫자를 모르면 절대 추측해서 채우지 말고 빈 문자열로 두십시오 "
            "(시나리오 실행 시 category_name으로 자동 조회·검증됩니다)."
        ),
    )
    keyword: str = Field(description="검증할 대표 키워드 (예: '수분스킨')")
    target_gender: str = Field(description="설정한 타겟 성별. 'm'(남성) 또는 'f'(여성)")
    target_age: str = Field(description="설정한 타겟 연령대. '10'~'60' 중 하나")
    start_date: str = Field(default_factory=_default_start, description="분석 시작일, YYYY-MM-DD (기본: 최근 3개월)")
    end_date: str = Field(default_factory=_default_end, description="분석 종료일, YYYY-MM-DD")


class TargetAudienceValidationScenario(BaseScenario):
    """설정한 타겟 오디언스(성별·연령)가 실제 검색 관심도 데이터와 맞는지 검증한다."""

    @property
    def name(self) -> str:
        return "naver_target_audience_validation"

    @property
    def description(self) -> str:
        return "특정 상품/키워드에 설정한 타겟 오디언스(성별·연령)가 실제 네이버쇼핑 검색·구매 관심도와 맞는지 검증한다."

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return TargetAudienceValidationParams

    @property
    def required_tool_names(self) -> List[str]:
        return [
            "find_naver_category_code",
            "get_shopping_category_gender_trend",
            "get_shopping_category_age_trend",
            "get_shopping_keyword_gender_trend",
            "get_shopping_keyword_age_trend",
        ]

    def execute(
        self,
        params: TargetAudienceValidationParams,
        tools: Dict[str, BaseTool],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        search_term = _pick_search_term(params.category_name, params.keyword)
        display_name = params.category_name or search_term or "(분야 미지정)"

        if not search_term:
            return (
                "### 타겟 오디언스 검증\n"
                "❌ category_name과 keyword가 모두 비어 있어 카테고리를 조회할 수 없습니다. "
                "분야명이나 상품 키워드를 알려주세요."
            )

        category_code, code_note = _resolve_category_code(tools, search_term, params.category_code)
        if not category_code:
            note_block = f"{code_note}\n\n" if code_note else ""
            return (
                f"### [{display_name} / {params.keyword}] 타겟 오디언스 검증\n"
                f"{note_block}"
                "❌ category_code를 확정하지 못해 조회를 진행할 수 없습니다. "
                "정확한 네이버쇼핑 분야명이나 category_code를 알려주세요."
            )

        date_kwargs = {"start_date": params.start_date, "end_date": params.end_date}

        category_gender = _run(tools, "get_shopping_category_gender_trend", category_code=category_code, **date_kwargs)
        category_age = _run(tools, "get_shopping_category_age_trend", category_code=category_code, **date_kwargs)
        keyword_gender = _run(tools, "get_shopping_keyword_gender_trend", category_code=category_code, keyword=params.keyword, **date_kwargs)
        keyword_age = _run(tools, "get_shopping_keyword_age_trend", category_code=category_code, keyword=params.keyword, **date_kwargs)

        checks = []
        for label, raw_text, target in (
            ("분야 전체 - 성별", category_gender, params.target_gender),
            ("분야 전체 - 연령", category_age, params.target_age),
            (f"'{params.keyword}' 키워드 - 성별", keyword_gender, params.target_gender),
            (f"'{params.keyword}' 키워드 - 연령", keyword_age, params.target_age),
        ):
            series = _parse_series(raw_text)
            top = None
            for points in series.values():
                candidate = _top_segment(points)
                if candidate and (top is None or candidate[1] > top[1]):
                    top = candidate
            if top is None:
                checks.append(f"- {label}: 판단 불가 (데이터 없음)")
            elif top[0] == target:
                checks.append(f"- {label}: ✅ 실제 최고 관심 세그먼트 '{top[0]}'(ratio {top[1]})가 타겟과 일치")
            else:
                checks.append(f"- {label}: ⚠️ 실제 최고 관심 세그먼트는 '{top[0]}'(ratio {top[1]})이나, 설정한 타겟은 '{target}'이라 불일치")

        note_block = f"{code_note}\n\n" if code_note else ""
        return (
            f"### [{display_name} / {params.keyword}] 타겟 오디언스 검증\n"
            f"{note_block}"
            f"설정한 타겟: 성별={params.target_gender}, 연령대={params.target_age}\n"
            f"기간: {params.start_date} ~ {params.end_date} | 사용된 category_code: {category_code}\n\n"
            f"#### 1. 분야 전체 성별 트렌드\n{category_gender}\n\n"
            f"#### 2. 분야 전체 연령별 트렌드\n{category_age}\n\n"
            f"#### 3. '{params.keyword}' 키워드 성별 트렌드\n{keyword_gender}\n\n"
            f"#### 4. '{params.keyword}' 키워드 연령별 트렌드\n{keyword_age}\n\n"
            f"#### 5. 타겟 일치 여부 검증\n" + "\n".join(checks) + "\n\n"
            "ages는 10세 단위(10~60)로만 제공되며, ratio는 구간 내 상대값이라 특정 구간의 일시적 변동만으로 "
            "타겟이 틀렸다고 단정할 수 없습니다."
        )


class KeywordAudienceSegmentationParams(BaseModel):
    category_code: str = Field(
        default="",
        description=(
            "네이버쇼핑 분야 코드. 정확한 숫자를 모르면 절대 추측해서 채우지 말고 빈 문자열로 두십시오 "
            "(시나리오 실행 시 keyword로 자동 조회·검증됩니다)."
        ),
    )
    keyword: str = Field(description="분포를 확인할 검색 키워드")
    start_date: str = Field(default_factory=_default_start, description="분석 시작일, YYYY-MM-DD (기본: 최근 3개월)")
    end_date: str = Field(default_factory=_default_end, description="분석 종료일, YYYY-MM-DD")


class KeywordAudienceSegmentationScenario(BaseScenario):
    """특정 키워드를 실제로 검색하는 사람들의 성별·연령대 분포를 세분화하여 제공한다."""

    @property
    def name(self) -> str:
        return "naver_keyword_audience_segmentation"

    @property
    def description(self) -> str:
        return "광고 타겟팅을 위해 특정 검색 키워드의 성별·연령대별 관심도 분포를 세분화하여 보여준다."

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return KeywordAudienceSegmentationParams

    @property
    def required_tool_names(self) -> List[str]:
        return ["find_naver_category_code", "get_shopping_keyword_gender_trend", "get_shopping_keyword_age_trend"]

    def execute(
        self,
        params: KeywordAudienceSegmentationParams,
        tools: Dict[str, BaseTool],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not params.keyword or not params.keyword.strip():
            return "### 키워드 타겟팅 세분화\n❌ keyword가 비어 있어 조회할 수 없습니다. 검색 키워드를 알려주세요."

        category_code, code_note = _resolve_category_code(tools, params.keyword, params.category_code)
        if not category_code:
            note_block = f"{code_note}\n\n" if code_note else ""
            return (
                f"### '{params.keyword}' 키워드 타겟팅 세분화\n"
                f"{note_block}"
                "❌ category_code를 확정하지 못해 조회를 진행할 수 없습니다. "
                "정확한 네이버쇼핑 분야명이나 category_code를 알려주세요."
            )

        date_kwargs = {"start_date": params.start_date, "end_date": params.end_date}
        gender_result = _run(tools, "get_shopping_keyword_gender_trend", category_code=category_code, keyword=params.keyword, **date_kwargs)
        age_result = _run(tools, "get_shopping_keyword_age_trend", category_code=category_code, keyword=params.keyword, **date_kwargs)

        gender_top = None
        for points in _parse_series(gender_result).values():
            candidate = _top_segment(points)
            if candidate and (gender_top is None or candidate[1] > gender_top[1]):
                gender_top = candidate

        age_top = None
        for points in _parse_series(age_result).values():
            candidate = _top_segment(points)
            if candidate and (age_top is None or candidate[1] > age_top[1]):
                age_top = candidate

        gender_line = f"- 가장 관심도 높은 성별: {gender_top[0]} (ratio {gender_top[1]})" if gender_top else "- 판단 불가 (데이터 없음)"
        age_line = f"- 가장 관심도 높은 연령대: {age_top[0]}대 (ratio {age_top[1]})" if age_top else "- 판단 불가 (데이터 없음)"

        note_block = f"{code_note}\n\n" if code_note else ""
        return (
            f"### '{params.keyword}' 키워드 타겟팅 세분화\n"
            f"{note_block}"
            f"기간: {params.start_date} ~ {params.end_date} | 사용된 category_code: {category_code}\n\n"
            f"#### 1. 성별 분포\n{gender_result}\n\n"
            f"#### 2. 연령대별 분포\n{age_result}\n\n"
            f"#### 3. 요약\n{gender_line}\n{age_line}\n\n"
            "ratio는 구간 내 최댓값을 100으로 한 상대값이며 절대 검색량·구매자 수가 아닙니다. "
            "특정 세그먼트가 높다고 해서 다른 세그먼트를 광고 타겟에서 배제해야 한다는 뜻은 아닙니다."
        )
