import re
from langchain_core.tools import tool
from .client import NaverShoppingClient

client = NaverShoppingClient()


@tool
def search_naver_shopping(query: str, display: int = 5, sort: str = "sim") -> str:
    """Search Naver Shopping for products, lowest price (lprice), and store information. sort: 'sim', 'date', 'asc', 'dsc'."""
    try:
        data = client.search_shop(query=query, display=display, sort=sort)
        items = data.get("items", [])
        if not items:
            return "네이버 쇼핑 검색 결과가 없습니다."
        output = []
        for it in items:
            title = re.sub(r"<.*?>", "", it.get("title", ""))
            price_val = it.get("lprice")
            try:
                price = int(price_val or 0)
            except (ValueError, TypeError):
                price = 0
            if price <= 0:
                continue
            price_str = f"{price:,}원"
            output.append(
                f"- 상품명: {title}\n  최저가: {price_str}\n  쇼핑몰: {it.get('mallName')}\n  링크: {it.get('link')}"
            )
        if not output:
            return "네이버 쇼핑 검색 결과가 없습니다."
        return "\n\n".join(output)
    except Exception as e:
        return f"네이버 쇼핑 검색 실패: {str(e)}"


@tool
def get_shopping_trends(keywords: str, start_date: str, end_date: str) -> str:
    """Query Naver Datalab search trend ratio for comma-separated keywords between start_date and end_date (YYYY-MM-DD)."""
    try:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        if not kw_list:
            return "키워드가 제공되지 않았습니다."
        data = client.get_datalab_trend(kw_list, start_date, end_date)
        results = data.get("results", [])
        if not results:
            return "트렌드 조회 결과가 없습니다."
        summary = []
        for res in results:
            title = res.get("title")
            data_pts = res.get("data", [])
            last_pt = data_pts[-1].get("ratio") if data_pts else "N/A"
            summary.append(f"- 키워드 '{title}': 최근 기간 상대 검색비율 {last_pt}%")
        return "\n".join(summary)
    except Exception as e:
        return f"트렌드 분석 조회 실패: {str(e)}"
