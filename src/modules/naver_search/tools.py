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
