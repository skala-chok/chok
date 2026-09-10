from langchain_core.tools import tool
from .client import YouTubeSearchClient

client = YouTubeSearchClient()


@tool
def search_youtube_videos(query: str, max_results: int = 5) -> str:
    """Search YouTube for videos related to query. Returns video titles, IDs, and descriptions."""
    try:
        data = client.search_videos(query=query, max_results=max_results)
        items = data.get("items", [])
        if not items:
            return "유튜브 검색 결과가 없습니다."
        output = []
        for it in items:
            vid = it.get("id", {}).get("videoId", "N/A")
            snip = it.get("snippet", {})
            output.append(
                f"- 제목: {snip.get('title')}\n"
                f"  영상ID: {vid}\n"
                f"  채널: {snip.get('channelTitle')}\n"
                f"  설명: {snip.get('description')}"
            )
        return "\n\n".join(output)
    except Exception as e:
        return f"유튜브 검색 중 오류 발생: {str(e)}"


@tool
def get_video_transcript(video_id: str) -> str:
    """Extract transcript or summary text of a YouTube video given its video_id."""
    try:
        return client.get_transcript(video_id)
    except Exception as e:
        return f"자막 추출 실패: {str(e)}"
