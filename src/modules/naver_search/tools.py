# ==============================================================================
# 🟡 [Step 3 - 노란점] LangChain 도구(@tool) 정의 계층
# • 역할: LLM이 호출할 도구 함수를 정의하고, Step 1의 client를 호출합니다.
# • 팁: LLM은 함수의 docstring과 타입 힌트만 보고 도구를 선택하므로 구체적으로 작성하세요.
# ➔ 다음 단계: 🟢 [Step 4] context.py 로 이동하여 시스템 프롬프트 지침을 작성하세요.
# ==============================================================================

from langchain_core.tools import tool

from .client import NaverSearchClient

client = NaverSearchClient()


@tool
def search_naver_blog(query: str, display: int = 5, sort: str = "sim") -> str:
    """네이버 블로그에서 실사용 후기, 튜토리얼, 개인 경험담을 검색합니다.

    Args:
        query: 검색할 핵심 키워드.
        display: 반환할 결과 개수 (1~10, 기본값 5).
        sort: 정렬 방식. 'sim'(정확도순) 또는 'date'(최신순).

    Returns:
        검색 결과 요약 문자열. OpenAPI 호출이 실패하면 클라이언트가 폴백(Fallback Mock)
        데이터를 반환하며, 그 외 예외 발생 시 오류 메시지 문자열을 반환합니다.
    """
    try:
        data = client.search_blog(query=query, display=display, sort=sort)
        items = data.get("items", [])
        if not items:
            return "네이버 블로그 검색 결과가 없습니다."
        output = []
        for it in items:
            output.append(f"- 제목: {it.get('title')}\n  링크: {it.get('link')}\n  내용: {it.get('description')}")
        return "\n\n".join(output)
    except Exception as e:
        return f"네이버 블로그 검색 실패: {str(e)}"


@tool
def search_naver_news(query: str, display: int = 5, sort: str = "sim") -> str:
    """네이버 뉴스에서 최신 보도 기사와 속보를 검색합니다.

    Args:
        query: 검색할 핵심 키워드.
        display: 반환할 결과 개수 (1~10, 기본값 5).
        sort: 정렬 방식. 'sim'(정확도순) 또는 'date'(최신순).

    Returns:
        검색 결과 요약 문자열. OpenAPI 호출이 실패하면 클라이언트가 폴백(Fallback Mock)
        데이터를 반환하며, 그 외 예외 발생 시 오류 메시지 문자열을 반환합니다.
    """
    try:
        data = client.search_news(query=query, display=display, sort=sort)
        items = data.get("items", [])
        if not items:
            return "네이버 뉴스 검색 결과가 없습니다."
        output = []
        for it in items:
            output.append(f"- 제목: {it.get('title')}\n  링크: {it.get('link')}\n  요약: {it.get('description')}")
        return "\n\n".join(output)
    except Exception as e:
        return f"네이버 뉴스 검색 실패: {str(e)}"

