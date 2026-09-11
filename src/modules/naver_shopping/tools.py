# ==============================================================================
# 🟡 [Step 3 - 노란점] LangChain 도구(@tool) 정의 계층
# • 역할: LLM이 호출할 쇼핑 검색 및 데이터랩 트렌드 도구를 정의합니다.
# ➔ 다음 단계: 🟢 [Step 4] context.py 로 이동하여 쇼핑 지침을 작성하세요.
# ==============================================================================

from typing import Any, Dict

from langchain_core.tools import tool

from .client import NaverShoppingClient

client = NaverShoppingClient()


@tool
def get_shopping_trends(keywords: str, start_date: str, end_date: str) -> str:
    """네이버 통합검색 기준 검색어 관심도 추이를 조회합니다.

    Args:
        keywords: 쉼표로 구분된 기준 키워드 문자열, 최대 5개 (예: '아이폰16, 갤럭시S24').
        start_date: 조회 시작일 (YYYY-MM-DD, 2016-01-01 이후).
        end_date: 조회 종료일 (YYYY-MM-DD).

    Returns:
        키워드별 기간 전체의 상대 검색비율 시계열 요약 문자열 (추세 판단을 위해 전체 구간을
        반환합니다). OpenAPI 호출이 실패하면 클라이언트가 폴백(Fallback Mock) 데이터를
        반환하며, 그 외 예외 발생 시 오류 메시지 문자열을 반환합니다.
    """
    try:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        if not kw_list:
            return "키워드가 제공되지 않았습니다."
        data = client.get_datalab_trend(kw_list, start_date, end_date)
        results = data.get("results", [])
        if not results:
            return "트렌드 조회 결과가 없습니다."
        return _format_trend_results(data)
    except Exception as e:
        return f"트렌드 분석 조회 실패: {str(e)}"


# ==============================================================================
# [Tool 추가 영역]
# 새로운 도구(Tool)를 정의하려면 이 영역 아래에 @tool 데코레이터를 사용하여 함수를 추가하시면 됩니다.
# 작성 예시:
# @tool
# def my_new_tool(param: str) -> str:
#     """도구에 대한 상세 설명을 작성하세요."""
#     # 로직 구현
#     return "결과 문자열"
#
# ※ 주의: 새로 작성한 tool은 module.py의 get_tools() 반환 리스트에도 반드시 등록해 주세요.
# ==============================================================================


def _parse_pairs(raw: str) -> Dict[str, str]:
    """'이름:값,이름:값' 형식 문자열을 {이름: 값} 딕셔너리로 변환."""
    pairs = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, value = chunk.partition(":")
        if not value:
            raise ValueError(f"'{chunk}'는 '이름:값' 형식이 아닙니다.")
        pairs[name.strip()] = value.strip()
    return pairs


def _format_trend_results(data: Dict[str, Any]) -> str:
    results = data.get("results", [])
    if not results:
        return "쇼핑 인사이트 조회 결과가 없습니다."
    lines = []
    for res in results:
        title = res.get("title")
        lines.append(f"[{title}]")
        for pt in res.get("data", []):
            if "group" in pt:
                lines.append(f"  - {pt.get('period')} ({pt.get('group')}): {pt.get('ratio')}")
            else:
                lines.append(f"  - {pt.get('period')}: {pt.get('ratio')}")
    return "\n".join(lines)


@tool
def get_shopping_category_trend(
    categories: str, start_date: str, end_date: str, time_unit: str = "month"
) -> str:
    """네이버쇼핑 분야(카테고리)별 클릭 트렌드를 최대 3개까지 비교 조회합니다.

    Args:
        categories: '분야명:분야코드' 쌍을 콤마로 구분한 문자열 (최대 3개). 예: "패션의류:50000000,화장품/미용:50000002"
        start_date: 조회 시작일 (YYYY-MM-DD, 2017-08-01 이후)
        end_date: 조회 종료일 (YYYY-MM-DD)
        time_unit: 'date', 'week', 'month' 중 하나 (기본값 'month')

    Returns:
        분야별 클릭 추이 요약 문자열. OpenAPI 호출이 실패하면 클라이언트가 폴백(Fallback Mock)
        데이터를 반환하며, 그 외 예외(잘못된 categories 형식 등) 발생 시 오류 메시지 문자열을 반환합니다.
    """
    try:
        cat_map = _parse_pairs(categories)
        data = client.get_category_trend(cat_map, start_date, end_date, time_unit)
        return _format_trend_results(data)
    except Exception as e:
        return f"분야별 트렌드 조회 실패: {str(e)}"


@tool
def get_shopping_category_gender_trend(
    category_code: str, start_date: str, end_date: str, time_unit: str = "month"
) -> str:
    """네이버쇼핑 특정 분야(카테고리)의 성별(남/여) 클릭 트렌드를 조회합니다.

    Args:
        category_code: 네이버쇼핑 분야 코드 (예: "50000000")
        start_date: 조회 시작일 (YYYY-MM-DD)
        end_date: 조회 종료일 (YYYY-MM-DD)
        time_unit: 'date', 'week', 'month' 중 하나 (기본값 'month')

    Returns:
        성별 클릭 추이 요약 문자열. OpenAPI 호출이 실패하면 클라이언트가 폴백(Fallback Mock)
        데이터를 반환하며, 그 외 예외 발생 시 오류 메시지 문자열을 반환합니다.
    """
    try:
        data = client.get_category_gender_trend(category_code, start_date, end_date, time_unit)
        return _format_trend_results(data)
    except Exception as e:
        return f"분야 성별 트렌드 조회 실패: {str(e)}"


@tool
def get_shopping_category_age_trend(
    category_code: str, start_date: str, end_date: str, time_unit: str = "month"
) -> str:
    """네이버쇼핑 특정 분야(카테고리)의 연령대별 클릭 트렌드를 조회합니다.

    Args:
        category_code: 네이버쇼핑 분야 코드 (예: "50000000")
        start_date: 조회 시작일 (YYYY-MM-DD)
        end_date: 조회 종료일 (YYYY-MM-DD)
        time_unit: 'date', 'week', 'month' 중 하나 (기본값 'month')

    Returns:
        연령대별 클릭 추이 요약 문자열. OpenAPI 호출이 실패하면 클라이언트가 폴백(Fallback Mock)
        데이터를 반환하며, 그 외 예외 발생 시 오류 메시지 문자열을 반환합니다.
    """
    try:
        data = client.get_category_age_trend(category_code, start_date, end_date, time_unit)
        return _format_trend_results(data)
    except Exception as e:
        return f"분야 연령별 트렌드 조회 실패: {str(e)}"


@tool
def get_shopping_keyword_trend(
    category_code: str, keywords: str, start_date: str, end_date: str, time_unit: str = "month"
) -> str:
    """네이버쇼핑 특정 분야 내에서 검색 키워드별 클릭 트렌드를 최대 5개까지 비교 조회합니다.

    Args:
        category_code: 네이버쇼핑 분야 코드 (예: "50000000")
        keywords: '이름:검색어' 쌍을 콤마로 구분한 문자열 (최대 5개). 예: "린넨원피스:린넨원피스,코트:코트"
        start_date: 조회 시작일 (YYYY-MM-DD)
        end_date: 조회 종료일 (YYYY-MM-DD)
        time_unit: 'date', 'week', 'month' 중 하나 (기본값 'month')

    Returns:
        키워드별 클릭 추이 요약 문자열. OpenAPI 호출이 실패하면 클라이언트가 폴백(Fallback Mock)
        데이터를 반환하며, 그 외 예외(잘못된 keywords 형식 등) 발생 시 오류 메시지 문자열을 반환합니다.
    """
    try:
        kw_map = _parse_pairs(keywords)
        data = client.get_category_keyword_trend(category_code, kw_map, start_date, end_date, time_unit)
        return _format_trend_results(data)
    except Exception as e:
        return f"키워드별 트렌드 조회 실패: {str(e)}"


@tool
def get_shopping_keyword_gender_trend(
    category_code: str, keyword: str, start_date: str, end_date: str, time_unit: str = "month"
) -> str:
    """네이버쇼핑 특정 분야 내 특정 검색 키워드의 성별(남/여) 클릭 트렌드를 조회합니다.

    Args:
        category_code: 네이버쇼핑 분야 코드 (예: "50000000")
        keyword: 검색 키워드 (예: "린넨원피스")
        start_date: 조회 시작일 (YYYY-MM-DD)
        end_date: 조회 종료일 (YYYY-MM-DD)
        time_unit: 'date', 'week', 'month' 중 하나 (기본값 'month')

    Returns:
        키워드 성별 클릭 추이 요약 문자열. OpenAPI 호출이 실패하면 클라이언트가 폴백(Fallback Mock)
        데이터를 반환하며, 그 외 예외 발생 시 오류 메시지 문자열을 반환합니다.
    """
    try:
        data = client.get_keyword_gender_trend(category_code, keyword, start_date, end_date, time_unit)
        return _format_trend_results(data)
    except Exception as e:
        return f"키워드 성별 트렌드 조회 실패: {str(e)}"


@tool
def get_shopping_keyword_age_trend(
    category_code: str, keyword: str, start_date: str, end_date: str, time_unit: str = "month"
) -> str:
    """네이버쇼핑 특정 분야 내 특정 검색 키워드의 연령대별 클릭 트렌드를 조회합니다.

    Args:
        category_code: 네이버쇼핑 분야 코드 (예: "50000000")
        keyword: 검색 키워드 (예: "린넨원피스")
        start_date: 조회 시작일 (YYYY-MM-DD)
        end_date: 조회 종료일 (YYYY-MM-DD)
        time_unit: 'date', 'week', 'month' 중 하나 (기본값 'month')

    Returns:
        키워드 연령대별 클릭 추이 요약 문자열. OpenAPI 호출이 실패하면 클라이언트가 폴백(Fallback Mock)
        데이터를 반환하며, 그 외 예외 발생 시 오류 메시지 문자열을 반환합니다.
    """
    try:
        data = client.get_keyword_age_trend(category_code, keyword, start_date, end_date, time_unit)
        return _format_trend_results(data)
    except Exception as e:
        return f"키워드 연령별 트렌드 조회 실패: {str(e)}"

