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

