from src.core.base import BaseContextProvider


class YouTubeSearchContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- YouTube 영상 검색이 필요할 때 'search_youtube_videos'를 호출하십시오.\n"
            "- 영상의 상세 내용이나 강의 스크립트가 필요한 경우 먼저 검색 후 얻은 영상ID로 'get_video_transcript'를 호출하십시오."
        )
