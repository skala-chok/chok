# ==============================================================================
# 🟡 [Step 3 - 노란점] Instagram LangChain @tool 정의 계층
# • 역할: 해시태그 ID 검색, 최신글/인기글 수집, 경쟁사 비즈니스 프로필 조회를 제공합니다.
# • 통과 기준: 공백/# 정규화 명시, 조회수 미제공 고지, 24시간 한계 및 시계열 부재 고지 등.
# ==============================================================================

import json
from langchain_core.tools import tool
from .client import InstagramApiClient

client = InstagramApiClient()


@tool
def search_hashtag_id(query: str) -> str:
    """인스타그램 해시태그의 고유 ID를 검색합니다.
    입력된 키워드에서 '#' 및 공백을 제거하여 정규화(q=...)한 후 조회합니다.

    Args:
        query: 검색할 해시태그 (예: '#성남 맛집', '분당맛집')
    """
    raw_query = query.strip()
    normalized_query = raw_query.lstrip("#").replace(" ", "")

    normalization_notice = (
        f"[정규화 안내] 입력값 '{raw_query}'에서 '#'과 공백을 제거하여 "
        f"'q={normalized_query}'로 인스타그램 해시태그 ID를 조회합니다."
    )

    try:
        data = client.search_hashtag(normalized_query)
        items = data.get("data", [])
        if not items:
            return (
                f"{normalization_notice}\n"
                f"해시태그 '{normalized_query}'에 대한 ID를 찾을 수 없습니다.\n"
                f"※ 안내: Instagram Graph API는 7일 롤링 기간 동안 최대 30개의 해시태그만 조회할 수 있습니다."
            )

        hashtag_id = items[0].get("id")
        tag_name = items[0].get("name", normalized_query)

        return (
            f"{normalization_notice}\n"
            f"• 해시태그명: #{tag_name}\n"
            f"• 해시태그 ID: {hashtag_id}\n\n"
            f"※ 제약 안내:\n"
            f"1. 해시태그 쿼터 제한: 7일 롤링 30개 초과 시 조회가 제한됩니다.\n"
            f"2. 작성자 정보 미포함: 해시태그 조회 결과에는 작성자 계정/가게 정보가 포함되지 않으므로 임의 추측하지 마십시오."
        )
    except Exception as e:
        return f"{normalization_notice}\n해시태그 ID 검색 실패: {str(e)}"


@tool
def get_hashtag_recent_media(hashtag_id: str) -> str:
    """지정된 해시태그 ID의 '최근 유입 게시물(recent_media, 현재 24시간 온도)' 목록을 조회합니다.
    최신글과 인기글은 엄격히 구분되며, 24시간 이전의 장기 시계열 추이는 제공되지 않습니다.

    Args:
        hashtag_id: search_hashtag_id로 획득한 해시태그 고유 ID
    """
    try:
        data = client.get_hashtag_recent_media(hashtag_id)
        items = data.get("data", [])
        if not items:
            return (
                f"해시태그 ID({hashtag_id})의 최근 24시간 내 게시물이 없습니다.\n"
                f"※ 통계 안내: 최근 24시간 게시물 수가 0건이므로 급상승 여부를 통계적으로 판단할 수 없습니다."
            )

        lines = [
            f"### [최신글 (recent_media)] 해시태그 ID: {hashtag_id}",
            f"• 수집 건수: {len(items)}건 (최근 24시간 윈도우 한정)",
            "• 게시물 목록:",
        ]

        total_likes = 0
        total_comments = 0
        for idx, it in enumerate(items, 1):
            likes = it.get("like_count", 0)
            comments = it.get("comments_count", 0)
            total_likes += likes
            total_comments += comments
            caption = it.get("caption", "내용 없음").replace("\n", " ")
            short_caption = caption[:70] + "..." if len(caption) > 70 else caption
            lines.append(
                f"  {idx}. [ID: {it.get('id')}] 좋아요: {likes:,}개 | 댓글: {comments:,}개 | 타입: {it.get('media_type')}\n"
                f"     - 캡션: \"{short_caption}\"\n"
                f"     - 링크: {it.get('permalink')}\n"
                f"     - 시간: {it.get('timestamp')}"
            )

        avg_eng = (total_likes + total_comments) / len(items)
        lines.append(f"\n• 최근 24시간 평균 참여도 (좋아요+댓글): {avg_eng:.2f}")

        sample_notice = ""
        if len(items) < 5:
            sample_notice = "\n⚠️ [표본 유의] 24시간 내 게시물 수가 5건 미만으로 적어 통계적 급상승을 단정하기에 표본이 부족합니다."

        disclaimer = (
            "\n※ API 제약 고지:\n"
            "1. recent_media는 최근 24시간 게시물만 반환하며 기간별 시계열 추이를 제공하지 않습니다.\n"
            "2. 게시물 작성자 정보는 포함되지 않으므로 특정 상호나 계정을 임의로 단정할 수 없습니다."
        )

        return "\n".join(lines) + sample_notice + disclaimer
    except Exception as e:
        return f"해시태그 최신글 조회 실패: {str(e)}"


@tool
def get_hashtag_top_media(hashtag_id: str) -> str:
    """지정된 해시태그 ID의 '누적 인기 게시물(top_media, 비교 기준선 baseline)' 목록을 조회합니다.

    Args:
        hashtag_id: search_hashtag_id로 획득한 해시태그 고유 ID
    """
    try:
        data = client.get_hashtag_top_media(hashtag_id)
        items = data.get("data", [])
        if not items:
            return f"해시태그 ID({hashtag_id})의 인기 게시물 결과가 없습니다."

        lines = [
            f"### [누적 인기글 (top_media - 비교 기준선)] 해시태그 ID: {hashtag_id}",
            f"• 수집 건수: {len(items)}건",
            "• 기준선 게시물 목록:",
        ]

        total_likes = 0
        total_comments = 0
        for idx, it in enumerate(items, 1):
            likes = it.get("like_count", 0)
            comments = it.get("comments_count", 0)
            total_likes += likes
            total_comments += comments
            caption = it.get("caption", "내용 없음").replace("\n", " ")
            short_caption = caption[:70] + "..." if len(caption) > 70 else caption
            lines.append(
                f"  {idx}. [ID: {it.get('id')}] 좋아요: {likes:,}개 | 댓글: {comments:,}개 | 타입: {it.get('media_type')}\n"
                f"     - 캡션: \"{short_caption}\"\n"
                f"     - 링크: {it.get('permalink')}\n"
                f"     - 시간: {it.get('timestamp')}"
            )

        avg_eng = (total_likes + total_comments) / len(items)
        lines.append(f"\n• 누적 인기글 평균 참여도 기준선 (좋아요+댓글): {avg_eng:.2f}")

        disclaimer = (
            "\n※ 안내: 인기글(top_media)은 알고리즘에 의해 집계된 장기 누적 기준선이며, 최신 유입(recent_media)과 엄격히 구분됩니다."
        )
        return "\n".join(lines) + disclaimer
    except Exception as e:
        return f"해시태그 인기글 조회 실패: {str(e)}"


@tool
def get_competitor_profile(username: str) -> str:
    """경쟁사 인스타그램 공식 비즈니스/크리에이터 계정의 프로필 지표(팔로워, 소개, 웹사이트)와 최근 게시물 목록을 조회합니다.
    (주의: 조회수는 API 미제공 지표이며, 좋아요/댓글 기반 참여율로 분석합니다.)

    Args:
        username: 조회할 계정 핸들 (예: 'nike', '재슐랭가이드', '@' 제외)
    """
    clean_username = username.strip().lstrip("@")
    if not clean_username:
        return "조회할 인스타그램 계정 핸들이 입력되지 않았습니다."

    try:
        data = client.get_business_discovery(clean_username)
        bd = data.get("business_discovery")
        if not bd:
            return (
                f"계정 '@{clean_username}'의 비즈니스 프로필을 조회할 수 없습니다.\n"
                f"※ 실패 원인: 해당 계정이 비즈니스/크리에이터 계정이 아니거나, 정확한 핸들이 아닐 수 있습니다. "
                f"계정명을 추측하지 마시고 사용자에게 정확한 핸들을 확인하십시오."
            )

        name = bd.get("name", clean_username)
        bio = bd.get("biography", "(소개 없음)")
        website = bd.get("website", "(웹사이트 없음)")
        followers = bd.get("followers_count", 0)
        follows = bd.get("follows_count", 0)
        media_count = bd.get("media_count", 0)
        media_items = bd.get("media", {}).get("data", [])

        lines = [
            f"### [경쟁사 공식 프로필] @{clean_username} ({name})",
            f"• 공식 채널 검증: Bio=\"{bio}\" | Web=\"{website}\"",
            f"• 팔로워: {followers:,}명 | 팔로우: {follows:,}명 | 총 게시물: {media_count:,}개",
            f"• 수집된 최근 게시물: {len(media_items)}건 (API 페이지네이션 범위 내 한정)",
            "",
            "• 최근 게시물 상세 내역 (타임스탬프 및 참여도):",
        ]

        total_eng = 0
        timestamps = []
        for idx, m in enumerate(media_items, 1):
            likes = m.get("like_count", 0)
            comments = m.get("comments_count", 0)
            total_eng += (likes + comments)
            ts = m.get("timestamp", "")
            if ts:
                timestamps.append(ts)
            caption = m.get("caption", "내용 없음").replace("\n", " ")
            lines.append(
                f"  {idx}. [ID: {m.get('id')}] 좋아요: {likes:,}개 | 댓글: {comments:,}개 | 일시: {ts}\n"
                f"     - 캡션: \"{caption}\"\n"
                f"     - 링크: {m.get('permalink')}"
            )

        avg_eng_rate = 0.0
        if followers > 0 and media_items:
            avg_eng_rate = ((total_eng / len(media_items)) / followers) * 100

        lines.append(f"\n• 팔로워 대비 평균 참여율(Engagement Rate): {avg_eng_rate:.3f}%")
        lines.append(f"• 게시물 타임스탬프 목록 (빈도 계산용): {json.dumps(timestamps)}")

        disclaimer = (
            "\n※ 지표 및 권한 고지:\n"
            "1. 조회수(View Count) 부재: Instagram Graph API(business_discovery)는 타 계정 미디어의 조회수를 제공하지 않으므로, 좋아요/댓글 참여율로 대체 분석합니다.\n"
            "2. 광고비 및 집행 여부 확인 불가: 광고비 집행액 및 유료 광고 여부는 확인 불가하며, timestamp는 캠페인 개시 시점의 프록시입니다.\n"
            "3. 범위 한계: 반환된 게시물은 최근 N건일 뿐 계정 전체 이력이 아닙니다."
        )

        return "\n".join(lines) + disclaimer
    except Exception as e:
        return f"경쟁사 프로필 조회 실패 (@{clean_username}): {str(e)}"
