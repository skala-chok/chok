# ==============================================================================
# 🟢 [Step 4 - 초록점] Instagram 모듈 시스템 프롬프트 컨텍스트 계층
# • 역할: LLM이 인스타그램 도구를 호출할 때 준수해야 하는 제약과 모범 프롬프트를 주입합니다.
# ==============================================================================

from src.core.base import BaseContextProvider


class InstagramContextProvider(BaseContextProvider):
    """Instagram Graph API 도구 사용을 위한 시스템 프롬프트 가이드라인 제공."""

    def get_system_prompt_snippet(self) -> str:
        return (
            "- 인스타그램 해시태그 및 경쟁사 프로필 조회가 필요할 때 'instagram' 도구들을 사용하십시오.\n"
            "- [해시태그 정규화]: 'search_hashtag_id' 호출 시 공백과 '#'을 제거한 정규화 키워드를 사용하고, 사용자에게 정규화 사실을 안내하십시오.\n"
            "- [최신글과 인기글의 구분]: 'get_hashtag_recent_media'(최근 24시간 실시간 유입)와 'get_hashtag_top_media'(누적 인기 기준선)를 절대 뭉쳐서 표현하지 마십시오.\n"
            "- [조회수 지표 부재]: Instagram Graph API(business_discovery)는 타 계정 미디어의 '조회수(View count)'를 일절 제공하지 않습니다. 절대 조회수를 생성하지 말고, 좋아요/댓글 기반 참여율로 분석하십시오.\n"
            "- [계정 핸들 추측 금지]: 경쟁사 인스타그램 핸들을 임의로 추측하지 말고, 확인되지 않으면 사용자에게 재확인을 요청하십시오.\n"
            "- [유료 광고/광고비 한계]: Graph API로 광고비 집행액이나 유료 광고 여부를 확인할 수 없음을 사용자에게 밝히십시오.\n"
            "- [시계열 추이 한계]: recent_media는 최근 24시간 데이터만 제공하므로 한 달 단위의 시계열 추세를 단정하지 마십시오."
        )
