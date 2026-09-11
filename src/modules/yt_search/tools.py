# ==============================================================================
# 🟡 [Step 3 - 노란점] LangChain 도구(@tool) 정의 계층
# • 역할: LLM이 호출할 유튜브 영상 검색 및 자막 추출 도구를 정의합니다.
# ➔ 다음 단계: 🟢 [Step 4] context.py 로 이동하여 유튜브 검색 지침을 작성하세요.
# ==============================================================================

from langchain_core.tools import tool
from .client import YouTubeSearchClient

client = YouTubeSearchClient()


# @tool
# def search_youtube_videos(query: str, max_results: int = 5) -> str:
#     """Search YouTube for videos related to query. Returns video titles, IDs, and descriptions."""
#     try:
#         data = client.search_videos(query=query, max_results=max_results)
#         items = data.get("items", [])
#         if not items:
#             return "유튜브 검색 결과가 없습니다."
#         output = []
#         for it in items:
#             vid = it.get("id", {}).get("videoId", "N/A")
#             snip = it.get("snippet", {})
#             output.append(
#                 f"- 제목: {snip.get('title')}\n"
#                 f"  영상ID: {vid}\n"
#                 f"  채널: {snip.get('channelTitle')}\n"
#                 f"  설명: {snip.get('description')}"
#             )
#         return "\n\n".join(output)
#     except Exception as e:
#         return f"유튜브 검색 중 오류 발생: {str(e)}"


# @tool
# def get_video_transcript(video_id: str) -> str:
#     """Extract transcript or summary text of a YouTube video given its video_id."""
#     try:
#         return client.get_transcript(video_id)
#     except Exception as e:
#         return f"자막 추출 실패: {str(e)}"

def _format_videos(data: dict) -> str:
    items = data.get("items", [])
    if not items:
        return "조건에 맞는 영상이 없습니다."
    rows = []
    for item in items:
        identifier = item.get("id", {})
        snippet = item.get("snippet", {})
        if identifier.get("channelId"):
            rows.append(f"- 채널: {snippet.get('title', 'N/A')}\n  채널ID: {identifier['channelId']}\n  URL: https://www.youtube.com/channel/{identifier['channelId']}")
        else:
            rows.append(
                f"- 제목: {snippet.get('title', 'N/A')}\n  채널: {snippet.get('channelTitle', 'N/A')}\n"
                f"  URL: https://www.youtube.com/watch?v={identifier.get('videoId', 'N/A')}\n"
                f"  게시일: {snippet.get('publishedAt', 'N/A')}"
            )
    return "\n\n".join(rows)


@tool
def find_youtube_channel(company: str, max_results: int = 5) -> str:
    """Find candidate official YouTube channels for a company; verify official status before analysis."""
    return _format_videos(client.find_channels(company, max_results))


@tool
def get_channel_videos(channel_id: str, start_date: str, end_date: str, max_results: int = 10) -> str:
    """Get advertising-candidate videos from a channel in a YYYY-MM-DD date range for content analysis."""
    return _format_videos(client.search_videos(
        "광고", max_results, channel_id, f"{start_date}T00:00:00Z", f"{end_date}T23:59:59Z"
    ))


@tool
def get_competitor_recent_uploads(channel_id: str, start_date: str, max_results: int = 10) -> str:
    """Get recent uploads from an identified official competitor channel from YYYY-MM-DD onward."""
    return _format_videos(client.search_videos("", max_results, channel_id, f"{start_date}T00:00:00Z"))


@tool
def search_paid_promotion_videos(query: str, start_date: str, max_results: int = 10) -> str:
    """Search videos marked as containing paid product placement from YYYY-MM-DD onward; this is not ad-spend data."""
    return _format_videos(client.search_videos(
        query, max_results, published_after=f"{start_date}T00:00:00Z", paid_product_placement=True
    ))


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
