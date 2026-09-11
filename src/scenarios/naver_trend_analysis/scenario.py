import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from src.core.scenario import BaseScenario

_TITLE_RE = re.compile(r"^\[(.+?)\]$")
_POINT_RE = re.compile(r"^\s*-\s*([\d-]+)(?:\s*\(([^)]+)\))?:\s*([\d.]+)\s*$")
_CANDIDATE_CODE_RE = re.compile(r"category_code=(\d+)")

_GENDER_KR = {"m": "남성", "f": "여성"}

# 차트용 원본 도구 결과: app.py가 실행 직후 읽어가며, 매 execute() 시작 시 초기화된다.
LAST_RUN_TOOL_RESULTS: Dict[str, str] = {}


def _run(tools: Dict[str, BaseTool], name: str, **kwargs: Any) -> str:
    tool = tools.get(name)
    result = tool.invoke(kwargs) if tool else f"{name} 도구를 사용할 수 없습니다."
    if isinstance(result, str):
        LAST_RUN_TOOL_RESULTS[name] = result
    return result


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


def _resolve_category_or_error(
    tools: Dict[str, BaseTool],
    search_term: str,
    given_code: str,
    scenario_title: str,
    missing_term_msg: str,
    action_desc: str = "조회를",
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """category_code 자동 조회·검증 및 에러 조기 반환 헬퍼."""
    if not search_term or not search_term.strip():
        return None, None, f"### {scenario_title}\n❌ {missing_term_msg}"
    category_code, code_note = _resolve_category_code(tools, search_term, given_code)
    if not category_code:
        note_block = f"{code_note}\n\n" if code_note else ""
        return None, None, (
            f"### {scenario_title}\n"
            f"{note_block}"
            f"❌ category_code를 확정하지 못해 {action_desc} 진행할 수 없습니다. "
            "정확한 네이버쇼핑 분야명이나 category_code를 알려주세요."
        )
    return category_code, code_note, None


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


def _top_segment_from_series(raw_text: str) -> Optional[Tuple[str, float]]:
    """raw_text 시계열 데이터에서 가장 관심도가 높은 (세그먼트, ratio)를 추출한다."""
    candidates = [_top_segment(pts) for pts in _parse_series(raw_text).values()]
    valid = [c for c in candidates if c is not None]
    return max(valid, key=lambda c: c[1]) if valid else None


def _format_disclaimers(disclaimers: List[str]) -> List[str]:
    return [f"{i}. {d}" for i, d in enumerate(disclaimers, 1)]


def _build_overview(title: str, items: List[Tuple[str, str]]) -> List[str]:
    return [
        f"# 📊 {title}\n",
        "### 1. 조회 개요",
        *(f"- {k}: {v}" for k, v in items),
        "",
    ]


def _series_table(
    series: Dict[str, List[Tuple[str, Optional[str], float]]],
    group_header: Optional[str] = None,
) -> List[str]:
    """{title: [(period, group, ratio), ...]}를 마크다운 표 라인들로 변환한다."""
    if not series:
        return ["_(데이터 없음)_"]
    if group_header:
        lines = [f"| 항목 | 구간 | {group_header} | ratio |", "| :--- | :--- | :---: | ---: |"]
        for title, points in series.items():
            for period, group, ratio in points:
                group_disp = _GENDER_KR.get(group, group or "-") if group_header == "성별" else f"{group}대" if group else "-"
                lines.append(f"| {title} | {period} | {group_disp} | {ratio} |")
    else:
        lines = ["| 항목 | 구간 | ratio |", "| :--- | :--- | ---: |"]
        for title, points in series.items():
            for period, _group, ratio in points:
                lines.append(f"| {title} | {period} | {ratio} |")
    return lines


def _build_new_product_trend_report(
    display_name: str,
    category_code: str,
    start_date: str,
    end_date: str,
    category_result: str,
    overall_result: str,
    keyword_result: str,
) -> str:
    """신제품 키워드 트렌드 조사 결과를 표·섹션 중심의 마크다운 리포트로 조립한다."""
    keyword_series = _parse_series(keyword_result)
    direction_lines = [f"- {title}: {_trend_direction(points)}" for title, points in keyword_series.items()]
    rising = [t for t, p in keyword_series.items() if _trend_direction(p).startswith("상승")]
    falling = [t for t, p in keyword_series.items() if _trend_direction(p).startswith("하락")]
    steady = [t for t, p in keyword_series.items() if _trend_direction(p).startswith("보합")]

    conclusion = []
    if direction_lines:
        conclusion.extend(direction_lines)
        conclusion.append("")
        if rising:
            conclusion.append(f"- **상승 키워드**: {', '.join(rising)}")
        if falling:
            conclusion.append(f"- **하락 키워드**: {', '.join(falling)}")
        if steady:
            conclusion.append(f"- **보합 키워드**: {', '.join(steady)}")
    else:
        conclusion.append("데이터 부족으로 추세 판정 불가")

    lines = [
        *_build_overview(
            f"[{display_name}] 신제품 키워드 트렌드 조사 리포트",
            [("분야", f"{display_name} (category_code={category_code})"), ("조회 기간", f"{start_date} ~ {end_date}")],
        ),
        "### 2. 분야 전체 클릭 트렌드 (네이버쇼핑 영역)",
        *_series_table(_parse_series(category_result)),
        "",
        "### 3. 통합검색 기준 키워드 전체 관심도",
        *_series_table(_parse_series(overall_result)),
        "",
        "### 4. 쇼핑 영역 기준 세부 키워드 비교",
        *_series_table(keyword_series),
        "",
        "### 5. 추세 판정 및 결론",
        *conclusion,
        "",
        "### 6. 데이터 해석 시 유의사항 (Disclaimers)",
        *_format_disclaimers([
            "ratio는 조회 구간 내 최댓값을 100으로 한 상대값이며 절대 검색량을 의미하지 않습니다.",
            "통합검색 기준 관심도(3번)와 네이버쇼핑 영역 기준 관심도(2·4번)는 서로 다른 모수이므로 직접 비교하지 않습니다.",
            "데이터에 없는 키워드나 수치는 지어내지 않았습니다.",
        ]),
    ]
    return "\n".join(lines)


def _build_target_audience_report(
    display_name: str,
    keyword: str,
    category_code: str,
    target_gender: str,
    target_age: str,
    start_date: str,
    end_date: str,
    category_gender: str,
    category_age: str,
    keyword_gender: str,
    keyword_age: str,
    checks: List[str],
) -> str:
    """타겟 오디언스 검증 결과를 표·섹션 중심의 마크다운 리포트로 조립한다."""
    target_kr = f"{_GENDER_KR.get(target_gender, target_gender)} · {target_age}대"
    mismatches = [c for c in checks if "⚠️" in c]
    if not checks:
        verdict = "데이터가 부족해 타겟 적합성을 판단하기 어렵습니다."
    elif not mismatches:
        verdict = f"설정하신 타겟({target_kr})이 실제 검색·클릭 데이터와 대체로 일치합니다."
    elif len(mismatches) == len(checks):
        verdict = f"설정하신 타겟({target_kr})은 실제 검색·클릭 데이터와 맞지 않습니다."
    else:
        verdict = f"설정하신 타겟({target_kr})이 일부 기준에서는 맞지만 다른 기준에서는 어긋나는 혼재된 결과입니다."

    lines = [
        *_build_overview(
            f"[{display_name} / {keyword}] 타겟 오디언스 검증 리포트",
            [
                ("분야", f"{display_name} (category_code={category_code})"),
                ("검증 키워드", keyword),
                ("설정 타겟", target_kr),
                ("조회 기간", f"{start_date} ~ {end_date}"),
            ],
        ),
        "### 2. 분야 전체 기준 실제 관심도",
        "**성별**",
        *_series_table(_parse_series(category_gender), group_header="성별"),
        "",
        "**연령대**",
        *_series_table(_parse_series(category_age), group_header="연령대"),
        "",
        f"### 3. '{keyword}' 키워드 기준 실제 관심도",
        "**성별**",
        *_series_table(_parse_series(keyword_gender), group_header="성별"),
        "",
        "**연령대**",
        *_series_table(_parse_series(keyword_age), group_header="연령대"),
        "",
        "### 4. 타겟 일치 여부 판정",
        *(checks if checks else ["판정 불가 (데이터 없음)"]),
        "",
        "### 5. 종합 결론",
        verdict,
        "",
        "### 6. 데이터 해석 시 유의사항 (Disclaimers)",
        *_format_disclaimers([
            "ages 파라미터는 10세 단위로만 제공되어 그 이상의 세분화(예: 24세 단일 연령)는 불가능합니다.",
            "ratio는 조회 구간 내 최댓값을 100으로 한 상대값이며 절대적인 검색량이나 구매자 수가 아닙니다.",
            "특정 구간의 일시적 변동만으로 타겟이 틀렸다고 성급히 단정하지 않습니다.",
        ]),
    ]
    return "\n".join(lines)


def _build_keyword_segmentation_report(
    keyword: str,
    category_code: str,
    start_date: str,
    end_date: str,
    gender_result: str,
    age_result: str,
    gender_top: Optional[Tuple[str, float]],
    age_top: Optional[Tuple[str, float]],
) -> str:
    """키워드 성별·연령 타겟팅 세분화 결과를 표·섹션 중심의 마크다운 리포트로 조립한다."""
    if gender_top or age_top:
        gender_part = _GENDER_KR.get(gender_top[0], gender_top[0]) if gender_top else "판단 불가"
        age_part = f"{age_top[0]}대" if age_top else "판단 불가"
        suggestion = [f"- 광고 타겟팅은 **{gender_part}** · **{age_part}**를 중심으로 설정하는 것이 데이터상 가장 부합합니다."]
    else:
        suggestion = ["- 데이터가 부족해 타겟팅 제안을 하기 어렵습니다."]

    lines = [
        *_build_overview(
            f"'{keyword}' 검색자 성별·연령대 분포 리포트",
            [("키워드", f"{keyword} (category_code={category_code})"), ("조회 기간", f"{start_date} ~ {end_date}")],
        ),
        "### 2. 성별 분포",
        *_series_table(_parse_series(gender_result), group_header="성별"),
    ]
    if gender_top:
        gender_kr = _GENDER_KR.get(gender_top[0], gender_top[0])
        lines.append(f"\n최고 관심 세그먼트: **{gender_kr}** (ratio {gender_top[1]})")
    lines.extend([
        "",
        "### 3. 연령대별 분포",
        *_series_table(_parse_series(age_result), group_header="연령대"),
    ])
    if age_top:
        lines.append(f"\n최고 관심 세그먼트: **{age_top[0]}대** (ratio {age_top[1]})")
    lines.extend([
        "",
        "### 4. 타겟팅 제안",
        *suggestion,
        "- 관심도가 낮게 나온 세그먼트라도 광고 타겟에서 완전히 배제할 근거로 보기는 어렵습니다.",
        "",
        "### 5. 데이터 해석 시 유의사항 (Disclaimers)",
        *_format_disclaimers([
            "ratio는 조회 구간 내 최댓값을 100으로 한 상대값이며 절대적인 검색량이나 구매자 수가 아닙니다.",
            "성별과 연령별 분포는 서로 구분되며, 둘을 임의로 결합해 새로운 수치를 만들지 않습니다.",
        ]),
    ])
    return "\n".join(lines)


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
    keywords: str = Field(
        description=(
            "비교할 세부 키워드, 쉼표로 구분 (예: '수분스킨,저자극스킨,맨즈스킨'), 최대 5개. "
            "사용자가 명시적인 비교 키워드 목록 없이 특정 신제품명만 언급했다면(예: '신제품 러닝화 마케팅'), "
            "그 제품명 자체를 keywords에 채우십시오 (예: '러닝화'). 이 필드를 절대 비워두지 마십시오."
        )
    )
    start_date: str = Field(default_factory=_default_start, description="분석 시작일, YYYY-MM-DD (기본: 최근 3개월)")
    end_date: str = Field(default_factory=_default_end, description="분석 종료일, YYYY-MM-DD")

    @field_validator("keywords")
    @classmethod
    def _reject_empty_keywords(cls, v: str) -> str:
        # 라우터(LLM)가 질의에 분명히 언급된 세부 키워드(예: '러닝화')를 놓치고 keywords를
        # 빈 문자열로 채우는 경우가 있다. 이때 category_name으로 조용히 대체하면 사용자가
        # 요청한 키워드와 다른 대상이 분석/차트에 나오므로, 차라리 검증 실패로 처리해
        # 일반 에이전트로 폴백시킨다 (agent.py의 기존 폴백 경로, 코어 수정 없이 동작).
        if not v or not v.strip():
            raise ValueError("keywords가 비어 있습니다 (라우터가 세부 키워드 추출에 실패함).")
        return v


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
        LAST_RUN_TOOL_RESULTS.clear()
        kw_list = [k.strip() for k in params.keywords.split(",") if k.strip()]
        search_term = _pick_search_term(params.category_name, *kw_list)
        display_name = params.category_name or search_term or "(분야 미지정)"

        category_code, code_note, err = _resolve_category_or_error(
            tools, search_term, params.category_code,
            f"[{display_name}] 신제품 키워드 트렌드 조사" if search_term else "신제품 키워드 트렌드 조사",
            "category_name과 keywords가 모두 비어 있어 카테고리를 조회할 수 없습니다. 분야명이나 상품 키워드를 알려주세요.",
            "분야/키워드별 조회를",
        )
        if err:
            return err

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

        note_block = f"{code_note}\n\n" if code_note else ""
        report = _build_new_product_trend_report(
            display_name=display_name,
            category_code=category_code,
            start_date=params.start_date,
            end_date=params.end_date,
            category_result=category_result,
            overall_result=overall_result,
            keyword_result=keyword_result,
        )
        return f"{note_block}{report}"


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
        LAST_RUN_TOOL_RESULTS.clear()
        search_term = _pick_search_term(params.category_name, params.keyword)
        display_name = params.category_name or search_term or "(분야 미지정)"

        category_code, code_note, err = _resolve_category_or_error(
            tools, search_term, params.category_code,
            f"[{display_name} / {params.keyword}] 타겟 오디언스 검증" if search_term else "타겟 오디언스 검증",
            "category_name과 keyword가 모두 비어 있어 카테고리를 조회할 수 없습니다. 분야명이나 상품 키워드를 알려주세요.",
        )
        if err:
            return err

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
            top = _top_segment_from_series(raw_text)
            if top is None:
                checks.append(f"- {label}: 판단 불가 (데이터 없음)")
            elif top[0] == target:
                checks.append(f"- {label}: ✅ 실제 최고 관심 세그먼트 '{top[0]}'(ratio {top[1]})가 타겟과 일치")
            else:
                checks.append(f"- {label}: ⚠️ 실제 최고 관심 세그먼트는 '{top[0]}'(ratio {top[1]})이나, 설정한 타겟은 '{target}'이라 불일치")

        note_block = f"{code_note}\n\n" if code_note else ""
        report = _build_target_audience_report(
            display_name=display_name,
            keyword=params.keyword,
            category_code=category_code,
            target_gender=params.target_gender,
            target_age=params.target_age,
            start_date=params.start_date,
            end_date=params.end_date,
            category_gender=category_gender,
            category_age=category_age,
            keyword_gender=keyword_gender,
            keyword_age=keyword_age,
            checks=checks,
        )
        return f"{note_block}{report}"


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
        LAST_RUN_TOOL_RESULTS.clear()
        kw = params.keyword.strip() if params.keyword else ""
        category_code, code_note, err = _resolve_category_or_error(
            tools, kw, params.category_code,
            f"'{params.keyword}' 키워드 타겟팅 세분화" if kw else "키워드 타겟팅 세분화",
            "keyword가 비어 있어 조회할 수 없습니다. 검색 키워드를 알려주세요.",
        )
        if err:
            return err

        date_kwargs = {"start_date": params.start_date, "end_date": params.end_date}
        gender_result = _run(tools, "get_shopping_keyword_gender_trend", category_code=category_code, keyword=params.keyword, **date_kwargs)
        age_result = _run(tools, "get_shopping_keyword_age_trend", category_code=category_code, keyword=params.keyword, **date_kwargs)

        gender_top = _top_segment_from_series(gender_result)
        age_top = _top_segment_from_series(age_result)

        note_block = f"{code_note}\n\n" if code_note else ""
        report = _build_keyword_segmentation_report(
            keyword=params.keyword,
            category_code=category_code,
            start_date=params.start_date,
            end_date=params.end_date,
            gender_result=gender_result,
            age_result=age_result,
            gender_top=gender_top,
            age_top=age_top,
        )
        return f"{note_block}{report}"
