from langchain_core.tools import tool
from .client import NaverSearchClient

client = NaverSearchClient()


@tool
def search_naver_blog(query: str, display: int = 5, sort: str = "sim") -> str:
    """Search Naver blogs for reviews, tutorials, and personal experiences. sort can be 'sim' or 'date'."""
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
    """Search Naver News for latest press articles and breaking news. sort can be 'sim' or 'date'."""
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

