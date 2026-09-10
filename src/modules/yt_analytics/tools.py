# ==============================================================================
# 🟡 [Step 3 - 노란점] LangChain 도구(@tool) 정의 계층
# • 역할: LLM이 호출할 채널 통계 조회 및 댓글 수집 도구를 정의합니다.
# ➔ 다음 단계: 🟢 [Step 4] context.py 로 이동하여 통계/댓글 분석 지침을 작성하세요.
# ==============================================================================

from langchain_core.tools import tool
from .client import YouTubeAnalyticsClient

client = YouTubeAnalyticsClient()


@tool
def get_channel_stats(channel_id: str) -> str:
    """Get subscriber count, total views, and video count of a YouTube channel by channel_id."""
    try:
        data = client.get_channel_info(channel_id)
        items = data.get("items", [])
        if not items:
            return f"채널 ID '{channel_id}'에 대한 정보를 찾을 수 없습니다."
        stats = items[0].get("statistics", {})
        return (
            f"[채널 통계 ({channel_id})]\n"
            f"- 구독자 수: {int(stats.get('subscriberCount', 0)):,}명\n"
            f"- 총 조회수: {int(stats.get('viewCount', 0)):,}회\n"
            f"- 업로드 영상 수: {stats.get('videoCount', 0)}개"
        )
    except Exception as e:
        return f"채널 통계 조회 중 오류: {str(e)}"


@tool
def get_video_comments(video_id: str, max_comments: int = 10) -> str:
    """Retrieve top comments from a YouTube video to analyze viewer reactions."""
    try:
        data = client.get_comments(video_id, max_comments)
        items = data.get("items", [])
        if not items:
            return "댓글이 없거나 조회할 수 없습니다."
        comments = []
        for it in items:
            c = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            author = c.get("authorDisplayName", "익명")
            text = c.get("textDisplay", "")
            comments.append(f"- {author}: {text}")
        return "\n".join(comments)
    except Exception as e:
        return f"댓글 수집 실패: {str(e)}"


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

