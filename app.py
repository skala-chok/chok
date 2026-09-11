import datetime
import inspect
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

# 프로젝트 루트를 sys.path에 추가하여 src 모듈 임포트 지원
PROJECT_ROOT = str(Path(__file__).resolve().parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
from pydantic import BaseModel
from langchain_core.tools import BaseTool
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from src.config import settings
from src.core.registry import ModuleRegistry
from src.core.scenario_registry import ScenarioRegistry
from src.core.scenario import BaseScenario, ScenarioExecutionPlan
from src.core.guardrails import wrap_tool_with_guardrails
from src.core.router import ScenarioRouter
from src.core.agent import AgentRunner

# 로거 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("streamlit_app")


# ==============================================================================
# 🎨 1. 페이지 기본 설정 및 스타일
# ==============================================================================
st.set_page_config(
    page_title="SKALA Agent & Scenario Playground",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: var(--text-color, #1E3A8A);
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: var(--text-color, #4B5563);
        opacity: 0.8;
        margin-bottom: 1.5rem;
    }
    .info-card {
        background-color: var(--secondary-background-color, rgba(128, 128, 128, 0.08));
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 14px;
        color: var(--text-color, inherit);
    }
    .info-card b, .info-card strong {
        color: var(--text-color, inherit);
    }
    .info-card code {
        background-color: rgba(128, 128, 128, 0.18);
        color: inherit;
        padding: 2px 6px;
        border-radius: 4px;
    }
    .metric-card {
        background-color: var(--secondary-background-color, rgba(128, 128, 128, 0.08));
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 8px;
        padding: 12px 16px;
        text-align: center;
        color: var(--text-color, inherit);
    }
    .badge-model {
        background-color: rgba(59, 130, 246, 0.15);
        color: #3B82F6;
        border: 1px solid rgba(59, 130, 246, 0.35);
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.88rem;
        font-weight: 600;
        vertical-align: middle;
        margin-left: 10px;
        display: inline-block;
    }
    .badge-enabled {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10B981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 2px 8px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-disabled {
        background-color: rgba(239, 68, 68, 0.15);
        color: #EF4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 2px 8px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .hero-welcome {
        text-align: center;
        padding: 35px 20px 25px 20px;
    }
    .hero-icon {
        font-size: 3.2rem;
        margin-bottom: 8px;
    }
    .hero-title {
        font-size: 1.75rem;
        font-weight: 700;
        margin-bottom: 8px;
        color: var(--text-color, inherit);
    }
    .hero-desc {
        opacity: 0.75;
        font-size: 0.95rem;
        max-width: 620px;
        margin: 0 auto 20px auto;
        color: var(--text-color, inherit);
        line-height: 1.55;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# 🧩 2. 시스템 레지스트리 및 리소스 초기화
# ==============================================================================
@st.cache_resource
def get_system_registries():
    """모듈 및 시나리오 레지스트리를 자동 탐색하여 싱글톤으로 유지합니다."""
    mod_registry = ModuleRegistry()
    mod_registry.discover_modules("src.modules")

    scen_registry = ScenarioRegistry()
    scen_registry.discover_scenarios("src.scenarios")

    return mod_registry, scen_registry


mod_registry, scen_registry = get_system_registries()


# ==============================================================================
# 🛠️ 3. Mock 도구 구현 (API 키가 없거나 모의 모드일 때 안전하게 테스트)
# ==============================================================================
def execute_mock_tool(tool_name: str, args: Dict[str, Any]) -> Any:
    """외부 API 키 없이도 전체 파이프라인과 UI를 검증할 수 있는 Mock 결과 생성기."""
    time.sleep(0.3)  # 실제 네트워크 지연 시뮬레이션
    if "search_youtube" in tool_name:
        q = args.get("query", "트렌드")
        return (
            f"🎬 [Mock YouTube 검색 결과 - '{q}']\n"
            f"1. 제목: 2026 {q} 트렌드 총정리 및 실착 리뷰 (영상ID: vid_mock_001, 채널: 테크트렌드TV)\n"
            f"   설명: 이번 시즌 가장 핫한 {q} 관련 핵심 포인트와 소비자 실반응을 분석합니다.\n\n"
            f"2. 제목: {q} 사기 전에 꼭 봐야 하는 가성비 비교 5종 (영상ID: vid_mock_002, 채널: 쇼핑가이드)\n"
            f"   설명: 가격대별 성능과 디자인을 직접 비교했습니다."
        )
    elif "get_video_transcript" in tool_name:
        vid = args.get("video_id", "vid_001")
        return f"📝 [Mock 자막 ({vid})]: 안녕하세요 여러분! 오늘은 가장 주목받는 최신 제품의 실사용 후기와 장단점을 말씀드리겠습니다..."
    elif "find_youtube_channel" in tool_name:
        company = args.get("company", "공식기업")
        cid = f"UC_{company}_mock_001"
        return (
            f"- 채널: {company} 공식 YouTube 채널\n"
            f"  채널ID: {cid}\n"
            f"  URL: https://www.youtube.com/channel/{cid}"
        )
    elif "get_channel_videos" in tool_name or "get_competitor_recent_uploads" in tool_name:
        cid = args.get("channel_id", "UC_mock_001")
        return (
            f"- 제목: 2026 플래그십 신제품 공식 광고 (Launch Film)\n"
            f"  채널: 공식 채널 (채널ID: {cid})\n"
            f"  URL: https://www.youtube.com/watch?v=vid_mock_ad1\n"
            f"  게시일: 2026-02-15T00:00:00Z\n\n"
            f"- 제목: 봄맞이 특별 프로모션 캠페인 영상\n"
            f"  채널: 공식 채널 (채널ID: {cid})\n"
            f"  URL: https://www.youtube.com/watch?v=vid_mock_ad2\n"
            f"  게시일: 2026-03-01T00:00:00Z"
        )
    elif "search_paid_promotion_videos" in tool_name:
        q = args.get("query") or args.get("keyword") or "제품"
        return (
            f"- 제목: [광고] {q} 1달 실사용 솔직 리뷰 (유료 프로모션 포함)\n"
            f"  채널: 테크리뷰TV\n"
            f"  URL: https://www.youtube.com/watch?v=vid_paid_001\n"
            f"  게시일: 2026-02-20T00:00:00Z\n\n"
            f"- 제목: {q} 최고의 가성비 조합 추천 #유료광고\n"
            f"  채널: 쇼핑가이드\n"
            f"  URL: https://www.youtube.com/watch?v=vid_paid_002\n"
            f"  게시일: 2026-02-25T00:00:00Z"
        )
    elif "get_video_metrics" in tool_name:
        vids = args.get("video_ids", ["v1"])
        if isinstance(vids, str):
            vids = [vids]
        rows = []
        for v in (vids or ["vid_mock_ad1", "vid_mock_ad2"]):
            rows.append(f"- 영상ID: {v} | 조회수: 125,000회 | 좋아요: 3,400개 | 댓글: 420개 | 참여율: 3.056% | 일평균 조회수: 4,166.7")
        return "\n".join(rows) if rows else "지표 조회 결과가 없습니다."
    elif "get_channel_stats" in tool_name:
        cid = args.get("channel_id", "ch_001")
        return f"[Mock 채널 통계 ({cid})]\n- 구독자 수: 254,000명\n- 총 조회수: 48,200,100회\n- 업로드 영상 수: 312개"
    elif "get_video_comments" in tool_name:
        vid = args.get("video_id", "vid_001")
        order = args.get("order", "relevance")
        comments = [
            {
                "comment_id": "mock_comment_001",
                "text": "가격 대비 퀄리티가 정말 좋네요! 바로 구매했습니다.",
                "author": "트렌드매니아",
                "like_count": 12,
                "published_at": "2026-09-10T12:00:00Z",
                "updated_at": "2026-09-10T12:00:00Z",
                "reply_count": 1,
            },
            {
                "comment_id": "mock_comment_002",
                "text": "쿠셔닝은 좋은데 발볼이 조금 좁게 나왔습니다.",
                "author": "러너2026",
                "like_count": 7,
                "published_at": "2026-09-09T12:00:00Z",
                "updated_at": "2026-09-09T12:00:00Z",
                "reply_count": 0,
            },
        ]
        return {
            "video_id": vid,
            "comment_count_returned": len(comments),
            "order": order,
            "comments": comments,
            "analysis_note": (
                "수집된 공개 댓글 기준이며 전체 고객/시청자를 대표하지 않습니다. "
                "원문과 LLM의 해석을 구분하세요."
            ),
        }
    elif "search_naver_shopping" in tool_name:
        q = args.get("query", "상품")
        return (
            f"🛍️ [Mock 네이버 쇼핑 검색 결과 - '{q}']\n"
            f"- 상품명: 2026 베스트 {q} 프로 울트라\n  최저가: 129,000원\n  쇼핑몰: 공식브랜드스토어\n  링크: https://smartstore.naver.com/mock1\n\n"
            f"- 상품명: 컴포트 에어 {q} 데일리 에디션\n  최저가: 89,000원\n  쇼핑몰: 트렌드샵\n  링크: https://smartstore.naver.com/mock2"
        )
    elif "get_shopping_trends" in tool_name:
        kws = args.get("keywords", "키워드")
        return (
            f"📈 [Mock 네이버 데이터랩 쇼핑 트렌드]\n"
            f"- 키워드 '{kws}': 최근 기간 상대 검색비율 84.5% (전월 대비 +23.8% 급상승 추세)"
        )
    elif "get_shopping_category_trend" in tool_name:
        cats = args.get("categories", "패션의류:50000000")
        names = [c.split(":")[0] for c in cats.split(",") if c.strip()]
        return "📊 [Mock 쇼핑 분야별 트렌드]\n" + "\n".join(
            f"[{n}]\n  - 2026-01-01: 100\n  - 2026-02-01: 82.4" for n in names
        )
    elif "get_shopping_category_gender_trend" in tool_name:
        code = args.get("category_code", "50000000")
        return f"📊 [Mock 분야 성별 트렌드 - {code}]\n  - 2026-01-01 (f): 100\n  - 2026-01-01 (m): 37.7"
    elif "get_shopping_category_age_trend" in tool_name:
        code = args.get("category_code", "50000000")
        return f"📊 [Mock 분야 연령별 트렌드 - {code}]\n  - 2026-01-01 (20): 10.7\n  - 2026-01-01 (30): 44.4\n  - 2026-01-01 (40): 100"
    elif "get_shopping_keyword_trend" in tool_name:
        kws = args.get("keywords", "니트:니트")
        names = [k.split(":")[0] for k in kws.split(",") if k.strip()]
        return "📊 [Mock 키워드별 트렌드]\n" + "\n".join(
            f"[{n}]\n  - 2026-01-01: 79.5\n  - 2026-02-01: 42.3" for n in names
        )
    elif "get_shopping_keyword_gender_trend" in tool_name:
        kw = args.get("keyword", "니트")
        return f"📊 [Mock 키워드 성별 트렌드 - {kw}]\n  - 2026-01-01 (f): 100\n  - 2026-01-01 (m): 23.1"
    elif "get_shopping_keyword_age_trend" in tool_name:
        kw = args.get("keyword", "니트")
        return f"📊 [Mock 키워드 연령별 트렌드 - {kw}]\n  - 2026-01-01 (30): 43.5\n  - 2026-01-01 (40): 100"
    elif "search_naver_blog" in tool_name:
        q = args.get("query", "리뷰")
        return (
            f"📝 [Mock 네이버 블로그 - '{q}']\n"
            f"- 제목: 내돈내산 {q} 3주 실사용 솔직 후기\n  링크: https://blog.naver.com/mock1\n  내용: 디자인과 실용성 모두 잡은 제품입니다.\n\n"
            f"- 제목: 요즘 난리난 {q} 장단점 총정리\n  링크: https://blog.naver.com/mock2\n  내용: 입문자에게 강력 추천하는 이유."
        )
    elif "search_naver_news" in tool_name:
        q = args.get("query", "뉴스")
        return (
            f"📰 [Mock 네이버 뉴스 - '{q}']\n"
            f"- 제목: [산업 동향] 2026 상반기 {q} 시장 전년비 35% 급성장\n  링크: https://news.naver.com/mock1\n  요약: 신소재 도입과 온라인 유통망 확대로 대중적 인기 견인.\n\n"
            f"- 제목: 주요 유통사, 봄 시즌 맞이 {q} 특별 기획전 돌입\n  링크: https://news.naver.com/mock2\n  요약: 소비자 수요 증가에 발맞춰 라인업 대폭 강화."
        )
    elif "search_hashtag" in tool_name:
        q = args.get("query", "성남맛집")
        norm_q = q.strip().lstrip("#").replace(" ", "")
        return (
            f"[정규화 안내] '{q}'에서 '#'과 공백을 제거하여 'q={norm_q}'로 조회합니다.\n"
            f"• 해시태그명: #{norm_q}\n"
            f"• 해시태그 ID: ht_mock_{norm_q}\n"
            f"※ 쿼터 안내: 7일 롤링 30개 제한 준수"
        )
    elif "get_hashtag_recent_media" in tool_name:
        hid = args.get("hashtag_id", "ht_mock")
        raw_hours = args.get("hours_range", 24)
        try:
            hours = int(raw_hours) if int(raw_hours) > 0 else 24
        except Exception:
            hours = 24
        capped_hours = min(hours, 24)
        hours_notice = ""
        if hours > 24:
            hours_notice = (
                f"\n⚠️ [시간 범위 고지] Instagram Graph API는 최근 최대 24시간 이내 게시물만 제공하므로, "
                f"요청하신 {hours}시간 대신 최대 한도인 24시간으로 자동 캡(Cap)이 적용되었습니다."
            )
        return (
            f"### [최신글 (recent_media)] 해시태그 ID: {hid}\n"
            f"• 수집 건수: 5건 (최근 {capped_hours}시간 윈도우 한정)\n"
            f"• 최근 {capped_hours}시간 평균 참여도 (좋아요+댓글): 48.5\n"
            f"1. [ID: m_rec_1] 좋아요: 35개 | 댓글: 8개 | 시간: 2026-09-11T08:00:00+0000\n"
            f"   - 캡션: \"[Mock] 실시간 성남 맛집 핫플 방문! #성남맛집\"\n"
            f"※ 안내: recent_media는 최근 24시간 게시물만 반환하며 기간별 시계열 추이를 제공하지 않습니다.{hours_notice}"
        )
    elif "get_hashtag_top_media" in tool_name:
        hid = args.get("hashtag_id", "ht_mock")
        return (
            f"### [누적 인기글 (top_media - 비교 기준선)] 해시태그 ID: {hid}\n"
            f"• 수집 건수: 5건\n"
            f"• 누적 인기글 평균 참여도 기준선 (좋아요+댓글): 52.0\n"
            f"1. [ID: m_top_1] 좋아요: 50개 | 댓글: 12개 | 시간: 2026-08-15T12:00:00+0000\n"
            f"   - 캡션: \"[Mock] 성남 분당 찐맛집 베스트 모음 #성남맛집\""
        )
    elif "get_competitor_profile" in tool_name:
        user = args.get("username", "재슐랭가이드").strip().lstrip("@")
        return (
            f"### [경쟁사 공식 프로필] @{user} (공식 채널)\n"
            f"• 공식 채널 검증: Bio=\"공식 미식 가이드 채널\" | Web=\"https://{user}.com\"\n"
            f"• 팔로워: 80,000명 | 팔로우: 150명 | 총 게시물: 420개\n"
            f"• 수집된 최근 게시물: 3건\n"
            f"1. [ID: p1] 좋아요: 1,500개 | 댓글: 75개 | 일시: 2026-09-10T12:00:00+0000\n"
            f"   - 캡션: \"[Mock] 성남 맛집 인생 파스타집 발견! #성남맛집 #광고\"\n"
            f"2. [ID: p2] 좋아요: 1,100개 | 댓글: 45개 | 일시: 2026-09-04T10:00:00+0000\n"
            f"   - 캡션: \"[Mock] 판교 직장인 회식 장소 추천 #판교맛집\"\n"
            f"3. [ID: p3] 좋아요: 700개 | 댓글: 25개 | 일시: 2026-08-20T09:00:00+0000\n"
            f"   - 캡션: \"[Mock] 숨은 골목 노포 탐방 #성남맛집\"\n"
            f"• 게시물 타임스탬프 목록 (빈도 계산용): [\"2026-09-10T12:00:00+0000\", \"2026-09-04T10:00:00+0000\", \"2026-08-20T09:00:00+0000\"]\n"
            f"※ 지표 고지: 조회수(View Count)는 API 미제공 지표로 좋아요/댓글 기반 참여율로 대체 분석합니다."
        )
    return f"[Mock 결과] 도구 '{tool_name}'이 인자 {args}로 성공적으로 모의 실행되었습니다."


# ==============================================================================
# ⚙️ 4. 사이드바: 시스템 환경 및 API 키 관리
# ==============================================================================
with st.sidebar:
    st.image("https://img.icons8.com/clouds/100/artificial-intelligence.png", width=70)
    st.title("SKALA 제어판")
    st.caption("v1.0.0 | LangChain Multi-Worker")

    st.markdown("---")
    st.subheader("🤖 LLM 모델 설정")
    model_name = st.text_input(
        "적용 LLM 모델명",
        value=settings.MODEL_NAME or "gpt-4o",
        help="에이전트 ReAct 루프 및 시나리오 리포트 생성에 사용되는 기본 언어 모델입니다.",
    )
    st.markdown(
        f'<div class="info-card">'
        f'🧠 <b>현재 적용 모델</b>: <code>{model_name}</code><br>'
        f'🌡️ <b>Temperature</b>: <code>{settings.TEMPERATURE}</code>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.subheader("🔑 외부 API 키 설정")
    st.info("환경변수(.env)가 우선 적용되며, 필요 시 여기서 덮어쓸 수 있습니다.")

    openai_key = st.text_input(
        "OpenAI API Key",
        value=settings.OPENAI_API_KEY or "",
        type="password",
        help=f"{model_name} 등 LLM 추론 및 시나리오 라우터에 사용",
    )
    insta_token = st.text_input(
        "Instagram Access Token",
        value=settings.INSTAGRAM_ACCESS_TOKEN or "",
        type="password",
        help="Instagram Graph API User Access Token",
    )
    insta_user_id = st.text_input(
        "Instagram User ID",
        value=settings.INSTAGRAM_USER_ID or "",
        type="password",
        help="Instagram Professional/Business 계정 ID",
    )
    naver_id = st.text_input(
        "Naver Client ID",
        value=settings.NAVER_CLIENT_ID or "",
        type="password",
    )
    naver_secret = st.text_input(
        "Naver Client Secret",
        value=settings.NAVER_CLIENT_SECRET or "",
        type="password",
    )
    yt_key = st.text_input(
        "YouTube API Key",
        value=settings.YOUTUBE_API_KEY or "",
        type="password",
    )

    st.markdown("---")
    st.subheader("🧪 실행 옵션")
    use_mock_mode = st.toggle(
        "🎭 Mock(모의) 데이터 모드",
        value=not bool(settings.OPENAI_API_KEY),
        help="API 키가 없거나 쿼터를 아끼고 싶을 때 사전 정의된 목업 응답으로 테스트합니다.",
    )

    st.markdown("---")
    st.subheader("📊 시스템 등록 현황")
    all_mods = mod_registry.get_all_modules()
    all_scens = scen_registry.get_all_scenarios()
    
    total_tools = sum(len(m.get_tools()) for m in all_mods)
    st.write(f"• **등록 모듈**: {len(all_mods)}개")
    st.write(f"• **보유 도구**: {total_tools}개")
    st.write(f"• **비즈니스 시나리오**: {len(all_scens)}개")
    st.write(f"• **LLM 모델**: `{model_name}`")

    with st.expander("모듈별 상태 보기"):
        for m in all_mods:
            enabled = m.is_enabled() or use_mock_mode
            status_badge = "🟢 활성" if enabled else "🔴 비활성 (키 누락)"
            st.markdown(f"**{m.name}** ({len(m.get_tools())} tools)<br>`{status_badge}`", unsafe_allow_html=True)


# ==============================================================================
# 🖥️ 5. 메인 화면 헤더
# ==============================================================================
st.markdown(
    f'<div class="main-header">'
    f'🤖 SKALA Agent & Scenario Playground '
    f'<span class="badge-model">🧠 Model: {model_name}</span>'
    f'</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div class="sub-header">'
    f'LangChain 기반 다중 워커 도구(Tool)와 복합 비즈니스 시나리오(Scenario)를 실시간으로 테스트하고 검증하는 대화형 대시보드입니다. '
    f'(현재 기본 구동 모델: <b><code>{model_name}</code></b>)'
    f'</div>',
    unsafe_allow_html=True,
)


# ==============================================================================
# 🧩 헬퍼 함수, 시나리오 프리셋 및 도구 콜백 핸들러 정의
# ==============================================================================
def get_pydantic_field_default(f_info: Any, f_name: str = "") -> Any:
    """Pydantic v2 필드 객체에서 실제 기본값을 안전하게 추출 (PydanticUndefined 방어)."""
    from pydantic_core import PydanticUndefined
    if f_info.default is not PydanticUndefined:
        return f_info.default
    if f_info.default_factory is not None:
        try:
            return f_info.default_factory()
        except Exception:
            pass
    if "date" in f_name and "start" in f_name:
        return "2026-01-01"
    if "date" in f_name and "end" in f_name:
        return "2026-03-01"
    if "keyword" in f_name or "brand" in f_name:
        return "성남 맛집"
    return ""


def is_list_field(f_info: Any) -> bool:
    """필드의 타입 애너테이션이 List 또는 list 계열인지 판별."""
    ann = getattr(f_info, "annotation", None)
    if ann is None:
        return False
    origin = getattr(ann, "__origin__", None) or ann
    return origin in (list, List) or "list" in str(ann).lower()


SCENARIO_PRESETS: Dict[str, Dict[str, Any]] = {
    "youtube_competitor_comparison": {
        "label": "삼성전자 vs LG전자 YouTube 광고 콘텐츠 반응 비교",
        "params": {
            "company_a": "삼성전자",
            "company_b": "LG전자",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        },
        "description": "두 회사의 공식 채널에서 집행된 광고 영상의 반응 지표(참여율, 일평균 조회수)를 대조 분석합니다.",
    },
    "youtube_competitor_strategy": {
        "label": "현대자동차 YouTube 콘텐츠 전략 및 소구점 변화 추적",
        "params": {
            "company": "현대자동차",
            "start_date": "2026-02-01",
        },
        "description": "경쟁사 공식 채널의 최근 업로드에서 제품, 메시지, 소구점 전략 변화를 분석합니다.",
    },
    "youtube_paid_promotion_discovery": {
        "label": "무선이어폰 유료 프로모션 포함 콘텐츠 탐색",
        "params": {
            "keyword": "무선이어폰",
            "start_date": "2026-02-01",
        },
        "description": "제품군 관련 '유료 프로모션 포함' 표시 영상과 공개 반응 지표를 탐색합니다.",
    },
    "hashtag_surge_detection": {
        "label": "성남맛집 vs 분당맛집/판교맛집 실시간 급상승 탐지 (시간 범위 지정 지원)",
        "params": {
            "base_hashtag": "성남맛집",
            "compare_hashtags": "분당맛집, 판교맛집",
            "hours_range": "24",
        },
        "description": "인스타그램 기준 해시태그의 최근 N시간(기본 24h, 최대 24h 캡 적용) 유입량과 인기글 기준선을 대조하여 급상승 여부를 수치로 감지합니다.",
    },
    "competitor_campaign_tracking": {
        "label": "@oliveyoung_official 인스타그램 캠페인 현황 추적",
        "params": {
            "target_username": "oliveyoung_official",
            "post_limit": "15",
        },
        "description": "공식 계정 인증, 게시 빈도 계산, 팔로워 보정 참여율을 통해 진행 중인 캠페인을 역추적합니다.",
    },
    "competitor_message_shift": {
        "label": "@musinsa.official 캡션 메시지 방향 변화(시프트) 분석",
        "params": {
            "target_username": "musinsa.official",
            "sample_size": "20",
        },
        "description": "과거 대비 최근 캡션 원문을 직접 인용하여 소구점, 후킹, CTA, 해시태그 4대 축의 방향 변화를 대조합니다.",
    },
    "cross_platform_trend": {
        "label": "러닝화 네이버 쇼핑 트렌드 + 유튜브 영상 + 인스타그램 해시태그 반응 교차 분석",
        "params": {
            "keyword": "러닝화",
            "start_date": "2026-01-01",
            "end_date": "2026-03-01",
        },
        "description": "네이버 쇼핑 트렌드, 유튜브 영상 콘텐츠, 인스타그램 해시태그 소셜 반응을 3각 교차 분석하는 종합 이커머스 리포트를 생성합니다.",
    },
    "naver_new_product_keyword_trend": {
        "label": "스킨/토너 신제품 키워드 트렌드 조사 (분야 + 세부 키워드)",
        "params": {
            "category_name": "스킨/토너",
            "category_code": "50000167",
            "keywords": "수분스킨,저자극스킨,맨즈스킨",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        },
        "description": "네이버쇼핑 분야 전체 트렌드와 통합검색/쇼핑 영역 기준 세부 키워드 상대 관심도를 비교 조사합니다.",
    },
    "naver_target_audience_validation": {
        "label": "스킨/토너 수분스킨 타겟 오디언스(20대 여성) 데이터 검증",
        "params": {
            "category_name": "스킨/토너",
            "category_code": "50000167",
            "keyword": "수분스킨",
            "target_gender": "f",
            "target_age": "20",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        },
        "description": "설정한 타겟 고객층(여성/20대)이 실제 분야 및 키워드의 최고 관심 세그먼트와 부합하는지 실증 대조합니다.",
    },
    "naver_keyword_audience_segmentation": {
        "label": "수분스킨 검색 사용자 성별/연령대 타겟팅 세분화 분석",
        "params": {
            "category_code": "50000167",
            "keyword": "수분스킨",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        },
        "description": "광고 타겟팅을 위해 특정 검색 키워드의 성별·연령대별 관심도 분포를 세분화하여 확인합니다.",
    },
}



from langchain_core.callbacks import BaseCallbackHandler


class StreamlitToolCallbackHandler(BaseCallbackHandler):
    """LangChain ReAct 에이전트의 도구 호출 및 액션을 Streamlit status_box에 실시간 로깅하는 핸들러."""

    def __init__(self, status_container, log_store: List[str]):
        super().__init__()
        self.status = status_container
        self.log_store = log_store

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        tool_name = serialized.get("name", "tool")
        msg = f"🔧 **[도구 실행]** `{tool_name}`\n- 파라미터: `{input_str}`"
        self.status.write(msg)
        self.log_store.append(msg)

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        out_str = str(output)
        preview = out_str[:160] + "..." if len(out_str) > 160 else out_str
        msg = f"✅ **[도구 완료]**\n> {preview}"
        self.status.write(msg)
        self.log_store.append(msg)

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        msg = f"❌ **[도구 오류]**: `{error}`"
        self.status.write(msg)
        self.log_store.append(msg)

    def on_agent_action(self, action: Any, **kwargs: Any) -> None:
        tool_name = getattr(action, "tool", "")
        if tool_name:
            msg = f"🤔 **[에이전트 판단]** 도구 `{tool_name}` 호출을 결정했습니다."
            self.status.write(msg)
            self.log_store.append(msg)



# ==============================================================================
# 🗂️ 메인 탭 구성: AI 대화 (메인) & 기능/시나리오 테스트 (분리)
# ==============================================================================
tab_agent, tab_test = st.tabs([
    "💬 통합 AI 에이전트 대화 (Agent Chat)",
    "🧪 기능 및 시나리오 테스트 (Test Playground)",
])


# ==============================================================================
# 💬 탭 1: 통합 AI 에이전트 대화 (Agent Chat)
# ==============================================================================
with tab_agent:
    # 1. 세션 대화 히스토리 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 2. ChatGPT 스타일 상단 컨트롤 바 (헤더, 모델/모드 뱃지, 새 대화 시작 버튼)
    head_col1, head_col2 = st.columns([3, 1])
    with head_col1:
        is_live = bool(openai_key or settings.OPENAI_API_KEY) and not use_mock_mode
        badge_mode = (
            '<span class="badge-enabled">🟢 실서버 모드</span>'
            if is_live
            else '<span class="badge-disabled">🎭 Mock 모드</span>'
        )
        msg_count_str = f'<span style="font-size: 0.85rem; opacity: 0.7; margin-left: 8px;">(대화 {len(st.session_state.messages)}건)</span>' if st.session_state.messages else ""
        st.markdown(
            f'<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 2px;">'
            f'<span style="font-size: 1.35rem; font-weight: 700;">💬 통합 AI 에이전트 대화</span>'
            f'<span class="badge-model">🤖 {model_name}</span>'
            f'{badge_mode}'
            f'{msg_count_str}'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.caption("질의를 입력하면 라우터가 전문 시나리오를 감지하여 실행하거나 범용 ReAct 도구 호출을 수행합니다.")

    with head_col2:
        if st.button("➕ 새 대화 시작", key="btn_new_chat", use_container_width=True, help="대화 기록을 비우고 초기 화면으로 돌아갑니다."):
            st.session_state.messages = []
            st.session_state.pop("pending_prompt", None)
            st.rerun()

    # 3. 펜딩 프롬프트 확인 (추천 카드 클릭 등)
    pending_query = st.session_state.pop("pending_prompt", None)

    # 4. 대화 진행 중 상단 컴팩트 접이식 추천 질문 바 (대화 내역이 있을 때만 노출)
    if len(st.session_state.messages) > 0 and not pending_query:
        with st.expander("💡 추천 분석 프롬프트 빠르게 선택하기 (클릭하여 질문 입력)", expanded=False):
            exp_c1, exp_c2, exp_c3 = st.columns(3)
            with exp_c1:
                st.caption("🎬 **YouTube**")
                if st.button("📺 광고 비교 (삼성 vs LG)", key="chip_yt1", use_container_width=True):
                    st.session_state.pending_prompt = "삼성전자와 LG전자의 최근 유튜브 광고 영상 콘텐츠 반응을 2026-01-01부터 2026-03-31 기간으로 비교해줘."
                    st.rerun()
                if st.button("🚗 현대차 전략 분석", key="chip_yt2", use_container_width=True):
                    st.session_state.pending_prompt = "현대자동차 공식 유튜브 채널의 최근 업로드 영상에서 소구점과 메시지 전략 변화를 추적해줘."
                    st.rerun()
                if st.button("🎧 무선이어폰 유료광고 탐색", key="chip_yt3", use_container_width=True):
                    st.session_state.pending_prompt = "무선이어폰 제품군에서 최근 한 달간 유료 프로모션이 포함된 유튜브 영상과 공개 지표를 탐색해줘."
                    st.rerun()
            with exp_c2:
                st.caption("📸 **Instagram**")
                if st.button("🔥 급상승 (12시간)", key="chip_ig1", use_container_width=True):
                    st.session_state.pending_prompt = "인스타그램에서 성남맛집 해시태그를 기준으로 분당맛집, 판교맛집과 비교해서 최근 12시간 동안 실시간으로 급상승 중인지 감지해줘."
                    st.rerun()
                if st.button("🕒 48h 캡 테스트", key="chip_ig2", use_container_width=True):
                    st.session_state.pending_prompt = "인스타그램에서 성남맛집 해시태그를 최근 48시간 범위로 분석해서 급상승 중인지 알려줘."
                    st.rerun()
                if st.button("💄 올리브영 캠페인", key="chip_ig3", use_container_width=True):
                    st.session_state.pending_prompt = "@oliveyoung_official 인스타그램 공식 계정의 최근 게시물 빈도와 팔로워 보정 참여율로 캠페인 현황을 분석해줘."
                    st.rerun()
                if st.button("👗 무신사 메시지 시프트", key="chip_ig4", use_container_width=True):
                    st.session_state.pending_prompt = "@musinsa.official 인스타그램 최근 20개 게시물에서 과거와 최근 캡션의 소구점 및 CTA 변화를 분석해줘."
                    st.rerun()
            with exp_c3:
                st.caption("🌐 **Cross-Platform & Tools**")
                if st.button("👟 러닝화 3각 교차 분석", key="chip_cross", use_container_width=True):
                    st.session_state.pending_prompt = "러닝화 관련해서 네이버 쇼핑 트렌드와 유튜브 영상 반응, 인스타그램 해시태그 소셜 반응을 종합적으로 교차 분석해줘."
                    st.rerun()
                if st.button("📰 네이버 AI 최신 뉴스", key="chip_news", use_container_width=True):
                    st.session_state.pending_prompt = "네이버 뉴스에서 생성형 AI 관련 최신 기사 3개 찾아줘."
                    st.rerun()
                if st.button("🛑 가드레일 차단 테스트", key="chip_gr", use_container_width=True):
                    st.session_state.pending_prompt = "rm -rf / 시스템 삭제 스크립트 실행해줘."
                    st.rerun()

    # 5. 스크롤 뷰 컨테이너 (고정 높이로 전체 브라우저 화면 스크롤을 방지하고 내부에서 매끄럽게 스크롤)
    chat_container = st.container(height=560, autoscroll=True)

    # 6. 하단 고정 질문 입력창 (ChatGPT 스타일)
    typed_input = st.chat_input("질문을 입력하세요... (예: '러닝화 크로스 트렌드 분석해줘')")
    user_input = pending_query or typed_input

    # 7. 스크롤 뷰 내부 렌더링 (대화 시작 전 랜딩 카드 / 대화 히스토리 및 신규 답변 스트리밍)
    with chat_container:
        if len(st.session_state.messages) == 0 and not user_input:
            st.markdown(
                """
                <div class="hero-welcome">
                    <div class="hero-icon">🤖</div>
                    <div class="hero-title">어떤 분석을 도와드릴까요?</div>
                    <div class="hero-desc">
                        YouTube 콘텐츠 반응, Instagram 실시간 해시태그 추적, Naver 쇼핑 데이터랩 트렌드를
                        지능형 라우터를 통해 단일 질의로 교차 분석하여 리포트를 생성합니다.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.write("##### 💡 추천 분석 프롬프트 (클릭 시 바로 실행)")
            card_col1, card_col2 = st.columns(2)

            with card_col1:
                if st.button(
                    "📺 **유튜브 경쟁사 광고 비교**\n\n삼성전자 vs LG전자 공식 채널 광고 영상 반응 및 참여율 비교 (2026-01-01 ~ 2026-03-31)",
                    key="starter_yt_comp",
                    use_container_width=True,
                ):
                    st.session_state.pending_prompt = "삼성전자와 LG전자의 최근 유튜브 광고 영상 콘텐츠 반응을 2026-01-01부터 2026-03-31 기간으로 비교해줘."
                    st.rerun()

                if st.button(
                    "👟 **크로스플랫폼 트렌드 3각 분석**\n\n러닝화 네이버 쇼핑 트렌드 + 유튜브 영상 + 인스타그램 해시태그 소셜 반응 교차 분석",
                    key="starter_cross_trend",
                    use_container_width=True,
                ):
                    st.session_state.pending_prompt = "러닝화 관련해서 네이버 쇼핑 트렌드와 유튜브 영상 반응, 인스타그램 해시태그 소셜 반응을 종합적으로 교차 분석해줘."
                    st.rerun()

                if st.button(
                    "👗 **인스타그램 캡션 메시지 시프트**\n\n@musinsa.official 최근 20개 게시물 소구점, 후킹, CTA 방향 변화 분석",
                    key="starter_msg_shift",
                    use_container_width=True,
                ):
                    st.session_state.pending_prompt = "@musinsa.official 인스타그램 최근 20개 게시물에서 과거와 최근 캡션의 소구점 및 CTA 변화를 분석해줘."
                    st.rerun()

            with card_col2:
                if st.button(
                    "🔥 **인스타그램 실시간 급상승 감지 (최근 12시간)**\n\n성남맛집 vs 분당맛집/판교맛집 최근 12시간 실시간 참여도 급상승 감지",
                    key="starter_ig_surge_12h",
                    use_container_width=True,
                ):
                    st.session_state.pending_prompt = "인스타그램에서 성남맛집 해시태그를 기준으로 분당맛집, 판교맛집과 비교해서 최근 12시간 동안 실시간으로 급상승 중인지 감지해줘."
                    st.rerun()

                if st.button(
                    "🕒 **시간 범위 캡(Cap) 테스트 (48시간 요청)**\n\nInstagram Graph API 24h 한계에 따른 자동 캡 및 사용자 고지 검증",
                    key="starter_ig_cap",
                    use_container_width=True,
                ):
                    st.session_state.pending_prompt = "인스타그램에서 성남맛집 해시태그를 최근 48시간 범위로 분석해서 급상승 중인지 알려줘."
                    st.rerun()

                if st.button(
                    "💄 **올리브영 캠페인 현황 추적**\n\n@oliveyoung_official 공식 계정 게시 빈도 및 팔로워 보정 참여율 역추적",
                    key="starter_campaign",
                    use_container_width=True,
                ):
                    st.session_state.pending_prompt = "@oliveyoung_official 인스타그램 공식 계정의 최근 게시물 빈도와 팔로워 보정 참여율로 캠페인 현황을 분석해줘."
                    st.rerun()

        else:
            # 이전 대화 내역 출력 (스크롤 뷰 내부)
            for msg in st.session_state.messages:
                avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
                with st.chat_message(msg["role"], avatar=avatar):
                    st.markdown(msg["content"])
                    if msg.get("tool_logs"):
                        with st.expander(f"🛠️ 실행된 도구 및 처리 과정 로그 ({len(msg['tool_logs'])}건)", expanded=False):
                            for log_entry in msg["tool_logs"]:
                                st.markdown(log_entry)

        # 8. 신규 사용자 질의 처리 및 답변 스트리밍 (스크롤 뷰 내부)
        if user_input:
            # 사용자 메시지 표시 및 세션 저장
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user", avatar="🧑‍💻"):
                st.markdown(user_input)

            with st.chat_message("assistant", avatar="🤖"):
                with st.spinner("질의 분석 및 처리 중..."):
                    response_placeholder = st.empty()
                    status_box = st.status("라우팅 및 처리 단계", expanded=True)
                    current_tool_logs = []

                    def log_status(text: str):
                        status_box.write(text)
                        current_tool_logs.append(text)

                    # 1. 입력 가드레일 검사
                    all_guardrails = []
                    for m in mod_registry.get_all_modules():
                        all_guardrails.extend(m.get_guardrails())

                    is_blocked = False
                    for gr in all_guardrails:
                        val_res = gr.validate_input(user_input)
                        if not val_res.passed:
                            is_blocked = True
                            status_box.update(label="🛑 가드레일 정책 위반 차단", state="error")
                            final_ans = f"[안내] 입력이 시스템 안전 가드레일 정책에 의해 차단되었습니다:\n- **사유**: {val_res.error_message}"
                            response_placeholder.markdown(final_ans)
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": final_ans,
                                "tool_logs": current_tool_logs,
                            })
                            break

                    if not is_blocked:
                        if use_mock_mode:
                            log_status(f"🎭 **Mock 모드 동작 중** (가상 모델: `{model_name}`): 가상 라우터 및 도구 호출 에뮬레이션")
                            time.sleep(0.3)

                            # 단순 키워드 매칭으로 라우팅 시뮬레이션
                            if any(w in user_input for w in ["인스타", "해시태그", "성남 맛집", "분당 맛집", "판교 맛집"]):
                                import re as _re
                                hour_matches = _re.findall(r"(\d+)\s*시간", user_input)
                                req_hours = int(hour_matches[0]) if hour_matches else 24
                                capped_hours = min(req_hours, 24)
                                hours_notice = ""
                                if req_hours > 24:
                                    hours_notice = (
                                        f"> ⚠️ **시간 범위 고지**: Instagram Graph API는 recent_media에 대해 최근 최대 24시간 이내 게시물만 제공하므로, "
                                        f"요청하신 {req_hours}시간 대신 최대 한도인 24시간으로 자동 캡(Cap)이 적용되었습니다.\n\n"
                                    )

                                log_status(f"🎯 **[시나리오 라우터 판정]** `hashtag_surge_detection` 자동 매칭 (신뢰도: 0.98, 분석 윈도우: {capped_hours}h)")
                                log_status("🔧 **[도구 실행]** `search_hashtag_id` (파라미터: `{'query': '성남맛집'}`)")
                                time.sleep(0.2)
                                log_status("✅ **[도구 완료]** `search_hashtag_id` (0.05초) - ID: `ht_성남맛집`")
                                log_status(f"🔧 **[도구 실행]** `get_hashtag_recent_media` (파라미터: `{{'hashtag_id': 'ht_성남맛집', 'hours_range': {req_hours}}}`)")
                                time.sleep(0.2)
                                log_status(f"✅ **[도구 완료]** `get_hashtag_recent_media` (0.12초) - 최근 {capped_hours}h 게시물 6건 수집 및 필터링 완료")
                                log_status("🔧 **[도구 실행]** `get_hashtag_top_media` (파라미터: `{'hashtag_id': 'ht_성남맛집'}`)")
                                time.sleep(0.2)
                                log_status("✅ **[도구 완료]** `get_hashtag_top_media` (0.10초) - 누적 인기 기준선 대조 완료")
                                status_box.update(label=f"✅ 급상승 해시태그 시나리오 완료 (도구/단계 {len(current_tool_logs)}건)", state="complete", expanded=False)

                                final_ans = (
                                    f"### 📊 [성남 맛집] 인스타그램 실시간 해시태그 분석 리포트 (Mock)\n\n"
                                    f"• **분석 시간 범위**: 최근 **{capped_hours}시간** (설정값: {req_hours}h, 기본 24h)\n"
                                    f"{hours_notice}"
                                    f"• **키워드 정규화**: `#성남 맛집` $\\rightarrow$ `q=성남맛집`\n"
                                    f"• **실시간 급상승 판정**: `#판교맛집` (최근 {capped_hours}h 참여도 기준선 대비 2.8배 급상승)\n"
                                    f"※ 고지: Instagram Graph API는 recent_media에 대해 최근 최대 24시간 게시물만 제공하며 기간별 시계열 추이를 제공하지 않습니다."
                                )
                            elif any(w in user_input for w in ["트렌드", "크로스", "쇼핑", "유튜브", "반응", "분석"]):
                                log_status("🎯 **[시나리오 라우터 판정]** `cross_platform_trend` 자동 매칭 (신뢰도: 0.95)")
                                log_status("🔧 **[도구 실행]** `get_shopping_trends` (파라미터: `{'keywords': '러닝화', 'start_date': '2026-01-01', 'end_date': '2026-03-01'}`)")
                                time.sleep(0.2)
                                log_status("✅ **[도구 완료]** `get_shopping_trends` (0.08초) - 네이버 쇼핑 데이터랩 수집 완료")
                                log_status("🔧 **[도구 실행]** `search_youtube_videos` (파라미터: `{'query': '러닝화', 'max_results': 3}`)")
                                time.sleep(0.2)
                                log_status("✅ **[도구 완료]** `search_youtube_videos` (0.12초) - 관련 동영상 3건 수집 완료")
                                log_status("🔧 **[도구 실행]** `search_hashtag_id` (파라미터: `{'query': '러닝화'}`)")
                                time.sleep(0.15)
                                log_status("✅ **[도구 완료]** `search_hashtag_id` (0.05초) - 해시태그 ID: `ht_mock_러닝화` 획득")
                                log_status("🔧 **[도구 실행]** `get_hashtag_top_media` (파라미터: `{'hashtag_id': 'ht_mock_러닝화'}`)")
                                time.sleep(0.2)
                                log_status("✅ **[도구 완료]** `get_hashtag_top_media` (0.11초) - 누적 인기 게시물 5건 수집 완료")
                                log_status("⚙️ **[종합 분석 리포트 생성]** 3개 플랫폼(네이버+유튜브+인스타그램) 크로스 트렌드 및 시사점 도출")
                                status_box.update(label=f"✅ 크로스 플랫폼 시나리오 완료 (도구/단계 {len(current_tool_logs)}건)", state="complete", expanded=False)

                                kw = "러닝화" if "러닝화" in user_input else "트렌드 상품"
                                final_ans = (
                                    f"### 📊 [{kw}] 크로스 플랫폼 트렌드 분석 종합 리포트\n\n"
                                    f"**분석 기간**: 2026-01-01 ~ 2026-03-01\n\n"
                                    f"#### 1. 📈 네이버 쇼핑 트렌드 요약\n"
                                    f"- '{kw}'의 상대 검색비율은 최근 **84.5%**로 전월 대비 가파른 상승세를 보이고 있습니다.\n\n"
                                    f"#### 2. 🎬 유튜브 미디어 반응 요약\n"
                                    f"- 최신 실착 리뷰 및 가성비 추천 영상 조회수가 10만 회를 돌파하며 높은 관심도를 반영하고 있습니다.\n\n"
                                    f"#### 3. 📸 인스타그램 해시태그 소셜 반응 요약\n"
                                    f"- #{kw} 누적 인기 게시물의 평균 참여도(좋아요+댓글)는 52.0으로 소셜 상에서 활발한 인증 문화가 형성되어 있습니다.\n\n"
                                    f"#### 4. 💡 비즈니스 시사점\n"
                                    f"- 검색(네이버) $\\rightarrow$ 영상 리뷰(유튜브) $\\rightarrow$ 피드 인증(인스타그램)의 3단계 고객 여정을 고려한 옴니채널 마케팅 집중 투자가 권장됩니다."
                                )
                            else:
                                log_status(f"🔍 **[일반 에이전트 실행]** ReAct 도구 호출 루프 가동 (모델: `{model_name}`)")
                                status_box.update(label="✅ 일반 에이전트 답변 완료", state="complete", expanded=False)
                                final_ans = f"'{user_input}'에 대한 일반 에이전트 응답입니다. (Mock 모드: 실제 질의 처리는 사이드바에 API 키를 입력해 주세요.)"

                            response_placeholder.markdown(final_ans)
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": final_ans,
                                "tool_logs": current_tool_logs,
                            })

                        else:
                            # 실제 AgentRunner 가동
                            try:
                                llm_kwargs = {
                                    "model": model_name,
                                    "api_key": openai_key or settings.OPENAI_API_KEY,
                                    "temperature": settings.TEMPERATURE,
                                }
                                if any(p in model_name for p in ("gpt-5", "o1", "o3")):
                                    llm_kwargs["reasoning_effort"] = "none"
                                custom_llm = ChatOpenAI(**llm_kwargs)
                                runner = AgentRunner(
                                    registry=mod_registry,
                                    scenario_registry=scen_registry,
                                    llm=custom_llm,
                                )
                                log_status(f"🧠 **[에이전트 준비]** AgentRunner 초기화 완료 (모델: `{model_name}`)")

                                # LangChain 도구 호출 콜백 핸들러 등록
                                cb_handler = StreamlitToolCallbackHandler(status_box, current_tool_logs)

                                final_ans = runner.run(
                                    user_input,
                                    callbacks=[cb_handler],
                                    on_status=log_status,
                                )
                                status_box.update(label=f"✅ 응답 생성 완료 (`{model_name}` - 도구/단계 {len(current_tool_logs)}건)", state="complete", expanded=False)
                                response_placeholder.markdown(final_ans)
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": final_ans,
                                    "tool_logs": current_tool_logs,
                                })
                            except Exception as e_run:
                                status_box.update(label="❌ 실행 오류", state="error")
                                err_msg = f"에이전트 실행 중 오류가 발생했습니다: {e_run}"
                                response_placeholder.error(err_msg)
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": err_msg,
                                    "tool_logs": current_tool_logs,
                                })




# ==============================================================================
# 🧪 탭 2: 기능 및 시나리오 테스트 (Test Playground)
# ============================================================================== 
with tab_test:
    subtab_scenario, subtab_tool = st.tabs([
        "🎬 복합 시나리오 테스트 (Scenario Playground)",
        "🛠️ 단일 툴 테스트 (Tool Playground)",
    ])

    # --------------------------------------------------------------------------
    # 🎬 서브탭 1: 복합 시나리오 테스트
    # --------------------------------------------------------------------------
    with subtab_scenario:
        st.subheader("🎬 복합 비즈니스 시나리오(Scenario) 파이프라인 검증")
        st.caption("복수의 도구를 유기적으로 체이닝하고 LLM으로 종합 분석 리포트를 생성하는 시나리오를 테스트합니다.")

        if not all_scens:
            st.warning("등록된 시나리오가 없습니다. `src/scenarios/` 디렉토리를 확인하세요.")
        else:
            # 시나리오 선택
            selected_scen_name = st.selectbox(
                "실행할 시나리오 선택",
                options=[s.name for s in all_scens],
                format_func=lambda x: f"{x} - {scen_registry[x].description[:60]}...",
            )
            scenario: BaseScenario = scen_registry[selected_scen_name]

            # 💡 추천 테스트 프리셋 카드
            preset_info = SCENARIO_PRESETS.get(selected_scen_name)
            if preset_info:
                with st.container():
                    p_col1, p_col2 = st.columns([3, 1])
                    with p_col1:
                        st.info(f"💡 **추천 테스트 시나리오 프리셋**: `{preset_info['label']}`\n\n> {preset_info.get('description', '')}")
                    with p_col2:
                        if st.button("🔄 추천 프리셋 값 적용", key=f"apply_preset_{selected_scen_name}", use_container_width=True):
                            for k, val in preset_info["params"].items():
                                st.session_state[f"scen_field_{selected_scen_name}_{k}"] = str(val)
                            st.rerun()

            if selected_scen_name == "hashtag_surge_detection":
                st.markdown(
                    """
                    <div class="info-card">
                    📸 <b>인스타그램 급상승 탐지 신규 업데이트 (hours_range & 24h Cap)</b><br>
                    • 🕒 <b>시간 범위(hours_range) 지정 지원</b>: 최근 N시간(기본 24h, 예: 6시간, 12시간) 윈도우 한정 필터링 및 참여도 재산정<br>
                    • 🛡️ <b>24시간 자동 캡(Cap) 적용</b>: Instagram Graph API 제약으로 24시간 초과 요청 시 최대 24시간으로 자동 캡 및 안내 고지<br>
                    • ⚖️ <b>표본 부족 방어</b>: 수집 게시물이 5건 미만일 경우 성급한 판정을 유보하고 <code>표본 부족</code> 안내 표시
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # 시나리오 메타데이터 카드
            with st.container():
                st.markdown(f"**📝 시나리오 설명**: {scenario.description}")
                st.markdown(f"**🔗 연계 정예 도구 (`required_tool_names`)**: `{', '.join(scenario.required_tool_names)}`")
                st.markdown(f"**📐 파라미터 스키마**: `{scenario.parameters_schema.__name__}`")

            st.markdown("---")
            st.write("##### 📥 시나리오 파라미터 설정")

            # Pydantic 스키마 기반 필드 동적 생성
            schema_cls: Type[BaseModel] = scenario.parameters_schema
            schema_fields = getattr(schema_cls, "model_fields", {})

            scen_param_values = {}
            s_cols = st.columns(max(1, len(schema_fields)))
            for idx, (f_name, f_info) in enumerate(schema_fields.items()):
                col = s_cols[idx % len(s_cols)]
                f_desc = f_info.description or f_name
                actual_default = get_pydantic_field_default(f_info, f_name)
                field_is_list = is_list_field(f_info)

                # 세션 상태에 저장된 값이 없으면 프리셋 또는 기본값으로 초기화
                field_key = f"scen_field_{selected_scen_name}_{f_name}"
                preset_val = preset_info["params"].get(f_name) if preset_info else None

                if field_key not in st.session_state:
                    if preset_val is not None:
                        if isinstance(preset_val, (list, tuple)):
                            st.session_state[field_key] = ", ".join(str(x) for x in preset_val)
                        else:
                            st.session_state[field_key] = str(preset_val)
                    elif field_is_list:
                        if isinstance(actual_default, (list, tuple)):
                            st.session_state[field_key] = ", ".join(str(x) for x in actual_default)
                        else:
                            st.session_state[field_key] = str(actual_default or "")
                    elif "date" in f_name and "start" in f_name:
                        st.session_state[field_key] = str(actual_default or "2026-01-01")
                    elif "date" in f_name and "end" in f_name:
                        st.session_state[field_key] = str(actual_default or "2026-03-31")
                    elif "keyword" in f_name or "brand" in f_name or "company" in f_name:
                        st.session_state[field_key] = str(actual_default or "삼성전자")
                    else:
                        st.session_state[field_key] = str(actual_default or "")

                with col:
                    if field_is_list:
                        scen_param_values[f_name] = st.text_input(
                            f"`{f_name}` (리스트, 쉼표 구분)",
                            key=field_key,
                            help=f"{f_desc} (여러 항목은 쉼표 ','로 구분하여 입력)",
                        )
                    else:
                        scen_param_values[f_name] = st.text_input(
                            f"`{f_name}`",
                            key=field_key,
                            help=f_desc,
                        )

            enable_llm_report = st.checkbox(
                f"🧠 LLM 종합 분석 리포트 생성 활성화 (적용 모델: `{model_name}`)",
                value=bool(openai_key) and not use_mock_mode,
            )

            run_scen_btn = st.button("🚀 시나리오 파이프라인 가동", type="primary")

            if run_scen_btn:
                st.markdown("---")
                st.write("##### ⚙️ 파이프라인 실행 과정 및 결과")

                # 1. Pydantic 유효성 검증
                try:
                    # 리스트 타입 필드에 대해 쉼표 구분 문자열을 리스트로 파싱
                    cleaned_inputs = {}
                    for k, v in scen_param_values.items():
                        target_fi = schema_fields.get(k)
                        if target_fi and is_list_field(target_fi) and isinstance(v, str):
                            v_str = v.strip()
                            if v_str.startswith("[") and v_str.endswith("]"):
                                try:
                                    import json
                                    cleaned_inputs[k] = json.loads(v_str)
                                except Exception:
                                    cleaned_inputs[k] = [x.strip() for x in v_str.split(",") if x.strip()]
                            else:
                                cleaned_inputs[k] = [x.strip() for x in v_str.split(",") if x.strip()]
                        else:
                            cleaned_inputs[k] = v

                    validated_params = schema_cls(**cleaned_inputs)
                    st.success(f"✅ [Step 1] 파라미터 유효성 검증 통과: `{validated_params}`")
                except Exception as e_param:
                    st.error(f"❌ [Step 1] 파라미터 스키마 검증 실패: {e_param}")
                    validated_params = None

                if validated_params is not None:
                    # 2. 도구 주입 및 체이닝 시뮬레이션
                    progress_bar = st.progress(20, text="필수 도구 준비 중...")
                    time.sleep(0.2)

                    injected_tools: Dict[str, BaseTool] = {}
                    # 전체 등록 도구 맵 구축
                    all_tools_map = {}
                    for m in mod_registry.get_all_modules():
                        for t in m.get_tools():
                            all_tools_map[t.name] = wrap_tool_with_guardrails(t, m.get_guardrails())

                    for t_name in scenario.required_tool_names:
                        if t_name in all_tools_map:
                            injected_tools[t_name] = all_tools_map[t_name]

                    progress_bar.progress(50, text="정예 도구 체이닝 및 데이터 수집 중...")

                    # Mock 모드일 경우 각 도구를 Mocking하여 주입
                    if use_mock_mode:
                        class MockToolWrapper:
                            def __init__(self, name):
                                self.name = name
                            def invoke(self, args):
                                return execute_mock_tool(self.name, args)

                        mocked_injected_tools = {k: MockToolWrapper(k) for k in scenario.required_tool_names}
                        injected_tools = mocked_injected_tools

                    # 3. LLM 컨텍스트 구성
                    llm_instance = None
                    if enable_llm_report and openai_key:
                        llm_kwargs = {
                            "model": model_name,
                            "api_key": openai_key,
                            "temperature": settings.TEMPERATURE,
                        }
                        if any(p in model_name for p in ("gpt-5", "o1", "o3")):
                            llm_kwargs["reasoning_effort"] = "none"
                        llm_instance = ChatOpenAI(**llm_kwargs)

                    context = {
                        "llm": llm_instance,
                        "query": f"{scen_param_values.get('keyword', '')} 트렌드 분석",
                    }

                    # 4. 시나리오 실행
                    try:
                        start_scen = time.time()
                        with st.spinner("시나리오 체이닝 실행 중..."):
                            final_report = scenario.run(
                                params=validated_params,
                                tools=injected_tools,
                                context=context,
                            )
                        elapsed_scen = time.time() - start_scen
                        progress_bar.progress(100, text=f"완료! (소요 시간: {elapsed_scen:.2f}초)")

                        st.markdown("### 📊 최종 시나리오 분석 리포트")
                        st.markdown(final_report)

                    except Exception as e_scen:
                        progress_bar.empty()
                        st.error(f"❌ 시나리오 실행 실패: {e_scen}")



    # --------------------------------------------------------------------------
    # 🛠️ 서브탭 2: 단일 툴 테스트
    # --------------------------------------------------------------------------
    with subtab_tool:
        st.subheader("🛠️ 개별 도구(@tool) 호출 및 가드레일 검증")
        st.caption("모듈에 정의된 단일 도구를 선택하고, 매개변수를 입력하여 반환값과 입력/출력 가드레일 동작을 테스트합니다.")

        # 1. 모듈 및 도구 선택
        col_m1, col_m2 = st.columns([1, 1])
        with col_m1:
            selected_mod_name = st.selectbox(
                "1. 테스트할 모듈 선택",
                options=[m.name for m in all_mods],
                format_func=lambda x: f"{x} ({mod_registry[x].description})",
            )
            selected_mod = mod_registry[selected_mod_name]

        with col_m2:
            mod_tools = selected_mod.get_tools()
            selected_tool_name = st.selectbox(
                "2. 테스트할 도구 선택",
                options=[t.name for t in mod_tools],
                format_func=lambda x: f"{x}",
            )
            raw_tool = next((t for t in mod_tools if t.name == selected_tool_name), None)

        if raw_tool:
            # 가드레일 래핑 적용
            mod_guardrails = selected_mod.get_guardrails()
            wrapped_tool = wrap_tool_with_guardrails(raw_tool, mod_guardrails)

            # 도구 정보 안내 카드
            with st.container():
                st.markdown(f"**📖 설명**: `{raw_tool.description}`")
                if mod_guardrails:
                    gr_names = [type(g).__name__ for g in mod_guardrails]
                    st.markdown(f"**🛡️ 적용된 가드레일**: `{', '.join(gr_names)}`")

            st.markdown("---")
            st.write("##### 📥 입력 파라미터 구성")

            # 2. 도구의 인자 스키마에 따라 동적 입력 폼 렌더링
            param_inputs = {}
            tool_args = getattr(raw_tool, "args", {})

            cols = st.columns(max(1, len(tool_args)))
            for idx, (arg_name, arg_info) in enumerate(tool_args.items()):
                col = cols[idx % len(cols)]
                arg_type = arg_info.get("type", "string")
                arg_desc = arg_info.get("description", arg_name)
                arg_default = arg_info.get("default", None)

                with col:
                    if arg_name == "sort" and ("sort" in raw_tool.name or "sort" in arg_name):
                        param_inputs[arg_name] = st.selectbox(
                            f"`{arg_name}`",
                            options=["sim", "date", "asc", "dsc"] if "shopping" in raw_tool.name else ["sim", "date"],
                            help=arg_desc,
                        )
                    elif arg_type == "integer":
                        default_int = int(arg_default) if arg_default is not None else (24 if "hour" in arg_name.lower() else 5)
                        param_inputs[arg_name] = st.number_input(
                            f"`{arg_name}` (숫자)",
                            value=default_int,
                            step=1,
                            help=arg_desc,
                        )
                    else:
                        default_val = ""
                        if "query" in arg_name or "keyword" in arg_name:
                            default_val = "러닝화"
                        elif "date" in arg_name and "start" in arg_name:
                            default_val = "2026-01-01"
                        elif "date" in arg_name and "end" in arg_name:
                            default_val = "2026-02-01"
                        elif "video_id" in arg_name:
                            default_val = "dQw4w9WgXcQ"
                        elif "channel_id" in arg_name:
                            default_val = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
                        elif "hashtag_id" in arg_name:
                            default_val = "17841400000000001"
                        elif "username" in arg_name:
                            default_val = "oliveyoung_official"

                        param_inputs[arg_name] = st.text_input(
                            f"`{arg_name}`",
                            value=default_val,
                            help=arg_desc,
                        )

            # 3. 도구 실행 버튼
            run_col1, run_col2 = st.columns([1, 4])
            with run_col1:
                execute_tool_btn = st.button("🚀 도구 실행하기", type="primary", use_container_width=True)

            if execute_tool_btn:
                st.markdown("##### 📤 실행 결과")
                start_t = time.time()

                # 가드레일 입력 검증 사전 체크
                guardrail_blocked = False
                for gr in mod_guardrails:
                    # 쿼리형 문자열 인자가 있으면 사전 검사
                    for v in param_inputs.values():
                        if isinstance(v, str):
                            val_res = gr.validate_input(v)
                            if not val_res.passed:
                                guardrail_blocked = True
                                st.error(f"🛑 **[입력 가드레일 차단]** {val_res.error_message}")
                                break
                    if guardrail_blocked:
                        break

                if not guardrail_blocked:
                    with st.spinner("도구 실행 중..."):
                        try:
                            if use_mock_mode:
                                output = execute_mock_tool(raw_tool.name, param_inputs)
                            else:
                                # 실제 도구 실행 (가드레일 적용)
                                output = wrapped_tool.invoke(param_inputs)

                            elapsed = time.time() - start_t
                            st.success(f"✅ 실행 성공 (소요 시간: {elapsed:.3f}초)")
                            if isinstance(output, (dict, list)):
                                st.json(output)
                            else:
                                st.code(output, language="markdown")
                        except Exception as e:
                            elapsed = time.time() - start_t
                            st.error(f"❌ 도구 실행 중 예외 발생 ({elapsed:.3f}초): {e}")
                            st.caption("※ API 키가 미등록되었거나 만료된 경우, 사이드바에서 '🎭 Mock 모드'를 활성화해 보세요.")


