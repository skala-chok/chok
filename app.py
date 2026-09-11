import datetime
import inspect
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

# 프로젝트 루트를 sys.path에 추가하여 src 모듈 임포트 지원
PROJECT_ROOT = str(Path(__file__).resolve().parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = [
    "Apple SD Gothic Neo", "AppleGothic", "NanumGothic", "Malgun Gothic", "DejaVu Sans",
]
matplotlib.rcParams["axes.unicode_minus"] = False

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
from src.scenarios.naver_trend_analysis import scenario as naver_trend_scenario

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
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px 16px;
        text-align: center;
    }
    .badge-enabled {
        background-color: #DEF7EC;
        color: #03543F;
        padding: 2px 8px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-disabled {
        background-color: #FDE8E8;
        color: #9B1C1C;
        padding: 2px 8px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
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
        return (
            f"### [최신글 (recent_media)] 해시태그 ID: {hid}\n"
            f"• 수집 건수: 5건 (최근 24시간 윈도우 한정)\n"
            f"• 최근 24시간 평균 참여도 (좋아요+댓글): 48.5\n"
            f"1. [ID: m_rec_1] 좋아요: 35개 | 댓글: 8개 | 시간: 2026-09-11T08:00:00+0000\n"
            f"   - 캡션: \"[Mock] 실시간 성남 맛집 핫플 방문! #성남맛집\"\n"
            f"※ 안내: recent_media는 최근 24시간 게시물만 반환하며 시계열 추이를 제공하지 않습니다."
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
        f'<div style="background-color: #EEF2FF; border: 1px solid #C7D2FE; border-radius: 6px; padding: 8px 12px; margin-bottom: 8px;">'
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
    f'<span class="badge-enabled" style="font-size: 0.95rem; vertical-align: middle; margin-left: 12px; background-color: #DBEAFE; color: #1E40AF; border: 1px solid #BFDBFE;">🧠 Model: {model_name}</span>'
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

tab_tool, tab_scenario, tab_agent, tab_explorer = st.tabs([
    "🛠️ 단일 툴 테스트 (Tool Playground)",
    "🎬 복합 시나리오 테스트 (Scenario Playground)",
    "💬 통합 에이전트 대화 (Agent & Router)",
    "📋 아키텍처 & 레지스트리 현황 (Explorer)",
])


# ==============================================================================
# 🛠️ 탭 1: 단일 툴 테스트 (Tool Playground)
# ==============================================================================
with tab_tool:
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
                    param_inputs[arg_name] = st.number_input(
                        f"`{arg_name}` (숫자)",
                        value=int(arg_default) if arg_default is not None else 5,
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


# ==============================================================================
# 🎬 탭 2: 복합 시나리오 테스트 (Scenario Playground)
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


with tab_scenario:
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

            with col:
                if field_is_list:
                    if isinstance(actual_default, (list, tuple)):
                        default_val = ", ".join(str(x) for x in actual_default)
                    else:
                        default_val = str(actual_default or "")
                    scen_param_values[f_name] = st.text_input(
                        f"`{f_name}` (리스트, 쉼표 구분)",
                        value=default_val,
                        help=f"{f_desc} (여러 항목은 쉼표 ','로 구분하여 입력)",
                    )
                elif "date" in f_name and "start" in f_name:
                    scen_param_values[f_name] = st.text_input(
                        f"`{f_name}` (시작일)",
                        value=str(actual_default or "2026-01-01"),
                        help=f_desc,
                    )
                elif "date" in f_name and "end" in f_name:
                    scen_param_values[f_name] = st.text_input(
                        f"`{f_name}` (종료일)",
                        value=str(actual_default or "2026-03-01"),
                        help=f_desc,
                    )
                elif "keyword" in f_name or "brand" in f_name:
                    scen_param_values[f_name] = st.text_input(
                        f"`{f_name}` (분석 대상)",
                        value=str(actual_default or "성남 맛집"),
                        help=f_desc,
                    )
                else:
                    scen_param_values[f_name] = st.text_input(
                        f"`{f_name}`",
                        value=str(actual_default or ""),
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


# ==============================================================================
# 💬 탭 3: 통합 에이전트 & 라우터 대화 (Agent & Router)
# ==============================================================================
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


# 원색 대신 채도를 낮춘 톤 (가독성/눈피로 개선 목적)
_TREND_LINE_COLORS = ["#5B84B1", "#C97064", "#6FAE8F", "#9C8AC4", "#D3A24C", "#5FA8A0"]
_AXIS_GRAY = "#8C8C8C"
_GRID_GRAY = "#BFBFBF"

_TREND_TITLE_RE = re.compile(r"^\[(.+?)\]$")
_TREND_POINT_RE = re.compile(r"^\s*-\s*([\d-]+)(?:\s*\(([^)]+)\))?:\s*([\d.]+)\s*$")

# naver_trend_analysis 도구 이름 -> 차트 제목 (원본 수치는 scenario.LAST_RUN_TOOL_RESULTS에서 읽음).
_NAVER_TREND_TOOL_LABELS = {
    "get_shopping_category_trend": "분야 전체 트렌드 (쇼핑 영역)",
    "get_shopping_trends": "통합검색 기준 키워드 전체 관심도",
    # get_shopping_keyword_trend(쇼핑 영역 세부 키워드 비교)는 리포트 표로만 보여주고 차트에서는 제외
    "get_shopping_category_gender_trend": "분야 전체 성별 트렌드",
    "get_shopping_category_age_trend": "분야 전체 연령별 트렌드",
    "get_shopping_keyword_gender_trend": "키워드 성별 트렌드",
    "get_shopping_keyword_age_trend": "키워드 연령별 트렌드",
}


def _parse_series_block(text: str) -> Dict[str, List[tuple]]:
    """get_shopping_*_trend 계열 도구의 '[제목]\\n  - 기간(그룹): 값' 형식 텍스트를 역파싱한다."""
    series: Dict[str, List[tuple]] = {}
    current_title: Optional[str] = None
    for line in text.splitlines():
        title_match = _TREND_TITLE_RE.match(line.strip())
        if title_match:
            current_title = title_match.group(1)
            series[current_title] = []
            continue
        point_match = _TREND_POINT_RE.match(line)
        if point_match and current_title is not None:
            period, group, ratio = point_match.groups()
            series[current_title].append((period, group, float(ratio)))
    return {title: pts for title, pts in series.items() if pts}


def _shorten_names(names: List[str], limit: int = 22) -> str:
    joined = ", ".join(names)
    return joined if len(joined) <= limit else joined[:limit - 1] + "…"


def _plot_trend_lines(periods: List[str], series_map: Dict[str, List[float]], title: str = "") -> "plt.Figure":
    """periods(x축)와 {계열명: 값 리스트}를 받아 추이 중심의 작고 정갈한 라인 차트를 그린다.

    가독성을 위해 점마다 값을 표시하지 않고 마지막 값만 라벨링하며, 축/그리드는 옅은 회색,
    선 색상은 채도를 낮춘 팔레트를 사용한다. 여러 차트를 한 화면에 나란히 놓고 볼 것을
    전제로 작게 그리고(표시 시 화면 폭을 억지로 채우지 않음), 흰 속 + 색 테두리 마커로
    좀 더 정돈된 느낌을 준다.
    """
    fig, ax = plt.subplots(figsize=(3.0, 2.0), dpi=130)
    x = list(range(len(periods)))
    all_values: List[float] = []
    for i, (name, values) in enumerate(series_map.items()):
        color = _TREND_LINE_COLORS[i % len(_TREND_LINE_COLORS)]
        ax.plot(x, values, linewidth=2.0, solid_capstyle="round", color=color,
                marker="o", markersize=5.5, markerfacecolor="white",
                markeredgecolor=color, markeredgewidth=1.6, label=name, zorder=3)
        # 가독성을 위해 마지막 값만 라벨링 (점마다 라벨을 달지 않음)
        ax.annotate(f"{values[-1]:g}", xy=(x[-1], values[-1]), textcoords="offset points",
                    xytext=(6, 0), va="center", fontsize=7, color=color, fontweight="bold")
        all_values.extend(values)

    ax.set_xticks(x)
    ax.set_xticklabels(periods, rotation=0, ha="center", fontsize=6.3, color=_AXIS_GRAY)
    ax.tick_params(axis="both", length=0, labelsize=6.3, colors=_AXIS_GRAY)

    if all_values:
        y_min, y_max = min(all_values), max(all_values)
        pad = max((y_max - y_min) * 0.3, 1.0)
        ax.set_ylim(y_min - pad, y_max + pad)
    ax.margins(x=0.18)

    ax.grid(axis="y", linestyle="-", linewidth=0.5, alpha=0.3, color=_GRID_GRAY)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(_GRID_GRAY)
    ax.spines["bottom"].set_linewidth(0.8)

    if title:
        ax.set_title(title, fontsize=8, color="#333333", fontweight="bold", loc="left", pad=8)
    if len(series_map) > 1:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=min(len(series_map), 3),
                   fontsize=6.3, frameon=False, labelcolor=_AXIS_GRAY)
    fig.tight_layout()
    return fig


def _render_trend_charts(chart_tool_results: Dict[str, str]) -> None:
    """naver_trend_analysis 시나리오가 실행됐다면 원본 수치를 matplotlib 차트로 함께 보여준다."""
    if not chart_tool_results:
        return

    figs: List["plt.Figure"] = []
    for tool_name, label in _NAVER_TREND_TOOL_LABELS.items():
        raw = chart_tool_results.get(tool_name)
        if not raw:
            continue
        series = _parse_series_block(raw)
        if not series:
            continue
        has_group = any(group is not None for points in series.values() for _, group, _ in points)

        if has_group:
            for title, points in series.items():
                periods = sorted({p for p, _, _ in points})
                if len(periods) < 2:
                    continue  # 데이터 포인트가 1개뿐이면 추이를 보여줄 수 없어 차트를 그리지 않음
                by_group: Dict[str, List[float]] = {}
                for p, group, ratio in points:
                    by_group.setdefault(group or "전체", [None] * len(periods))
                    by_group[group or "전체"][periods.index(p)] = ratio
                # None(결측) 구간은 마지막 관측값으로 보간해 라인이 끊기지 않도록 처리
                for vals in by_group.values():
                    last = 0.0
                    for i, v in enumerate(vals):
                        if v is None:
                            vals[i] = last
                        else:
                            last = v
                figs.append(_plot_trend_lines(periods, by_group, title=f"{label} · {title}"))
        else:
            periods = sorted({p for points in series.values() for p, _, _ in points})
            if len(periods) < 2:
                continue  # 데이터 포인트가 1개뿐이면 추이를 보여줄 수 없어 차트를 그리지 않음
            series_map: Dict[str, List[float]] = {}
            for title, points in series.items():
                by_period = {p: r for p, _, r in points}
                series_map[title] = [by_period.get(p, 0.0) for p in periods]
            chart_title = f"{label} · {_shorten_names(list(series_map.keys()))}"
            figs.append(_plot_trend_lines(periods, series_map, title=chart_title))

    if not figs:
        return

    st.info(
        "📌 아래 ratio는 조회 구간 내 최댓값을 100으로 정규화한 상대값입니다 (절대 검색량·구매자 수가 아닙니다). "
        "서로 다른 항목의 수치는 모수가 달라 직접 비교할 수 없습니다."
    )
    # 여러 차트를 세로로 쌓지 않고 한 줄(최대 4개)에 나란히 배치. width="content"로
    # 컨테이너 폭에 억지로 늘리지 않고 차트 실제 크기(작게) 그대로 표시한다.
    cols_per_row = 4
    for i in range(0, len(figs), cols_per_row):
        row_figs = figs[i:i + cols_per_row]
        cols = st.columns(len(row_figs))
        for col, fig in zip(cols, row_figs):
            with col:
                st.pyplot(fig, clear_figure=True, width="content")
            plt.close(fig)


def _render_agent_message(msg: Dict[str, Any]) -> None:
    st.markdown(msg["content"])
    _render_trend_charts(msg.get("chart_tool_results") or {})


with tab_agent:
    st.subheader("💬 통합 AI 에이전트 & 라우터 실시간 대화")
    st.caption(f"사용자 질의를 입력하면, 라우터가 전문 시나리오를 감지하여 실행하거나 범용 ReAct 도구 호출 에이전트(적용 모델: <b><code>{model_name}</code></b>)로 처리합니다.")

    # 빠른 테스트용 프롬프트 버튼
    st.write("##### ⚡ 빠른 테스트 질문 예시:")
    q_col1, q_col2, q_col3, q_col4, q_col5 = st.columns(5)
    quick_query = None
    with q_col1:
        if st.button("📈 러닝화 트렌드 분석", use_container_width=True):
            quick_query = "러닝화 관련해서 네이버 쇼핑 트렌드와 유튜브 최신 반응을 분석해줘"
    with q_col2:
        if st.button("📸 인스타 실시간 해시태그", use_container_width=True):
            quick_query = "성남 맛집 관련해서 인스타에서 지금 실시간으로 뜨고 있는 해시태그가 뭔지 알려줘. #성남 맛집, #분당 맛집, #판교 맛집 비교해줘."
    with q_col3:
        if st.button("📰 AI 최신 뉴스 3개", use_container_width=True):
            quick_query = "네이버 뉴스에서 생성형 AI 관련 최신 기사 3개 찾아줘"
    with q_col4:
        if st.button("📺 파이썬 강의 검색", use_container_width=True):
            quick_query = "유튜브에서 파이썬 기초 강의 영상 3개 검색해줘"
    with q_col5:
        if st.button("🛑 가드레일 차단 테스트", use_container_width=True):
            quick_query = "rm -rf / 시스템 삭제 스크립트 실행해줘"

    # 세션 채팅 히스토리 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": f"안녕하세요! YouTube, Naver, Instagram API를 활용하는 통합 AI 에이전트(기본 모델: `{model_name}`)입니다. 무엇을 도와드릴까요?", "tool_logs": []}
        ]

    # 이전 대화 내역 출력
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            _render_agent_message(msg)
            if msg.get("tool_logs"):
                with st.expander(f"🛠️ 실행된 도구 및 처리 과정 로그 ({len(msg['tool_logs'])}건)", expanded=False):
                    for log_entry in msg["tool_logs"]:
                        st.markdown(log_entry)

    # 입력창
    user_input = st.chat_input("질문을 입력하세요... (예: '나이키 신발 쇼핑 트렌드와 유튜브 반응 분석해줘')")
    if quick_query:
        user_input = quick_query

    if user_input:
        # 사용자 메시지 표시 및 저장
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
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
                        blocked_msg = {"role": "assistant", "content": final_ans, "tool_logs": current_tool_logs}
                        with response_placeholder.container():
                            _render_agent_message(blocked_msg)
                        st.session_state.messages.append(blocked_msg)
                        break

                if not is_blocked:
                    if use_mock_mode:
                        log_status(f"🎭 **Mock 모드 동작 중** (가상 모델: `{model_name}`): 가상 라우터 및 도구 호출 에뮬레이션")
                        time.sleep(0.3)

                        # 단순 키워드 매칭으로 라우팅 시뮬레이션
                        if any(w in user_input for w in ["인스타", "해시태그", "성남 맛집", "분당 맛집", "판교 맛집"]):
                            log_status("🎯 **[시나리오 라우터 판정]** `hashtag_surge_detection` 자동 매칭 (신뢰도: 0.98)")
                            log_status("🔧 **[도구 실행]** `search_hashtag_id` (파라미터: `{'query': '성남맛집'}`)")
                            time.sleep(0.2)
                            log_status("✅ **[도구 완료]** `search_hashtag_id` (0.05초) - ID: `ht_성남맛집`")
                            log_status("🔧 **[도구 실행]** `get_hashtag_recent_media` (파라미터: `{'hashtag_id': 'ht_성남맛집'}`)")
                            time.sleep(0.2)
                            log_status("✅ **[도구 완료]** `get_hashtag_recent_media` (0.12초) - 최근 24h 게시물 6건 수집 완료")
                            log_status("🔧 **[도구 실행]** `get_hashtag_top_media` (파라미터: `{'hashtag_id': 'ht_성남맛집'}`)")
                            time.sleep(0.2)
                            log_status("✅ **[도구 완료]** `get_hashtag_top_media` (0.10초) - 누적 인기 기준선 대조 완료")
                            status_box.update(label=f"✅ 급상승 해시태그 시나리오 완료 (도구/단계 {len(current_tool_logs)}건)", state="complete", expanded=False)

                            final_ans = (
                                "### 📊 [성남 맛집] 인스타그램 실시간 해시태그 분석 리포트 (Mock)\n\n"
                                "• **키워드 정규화**: `#성남 맛집` $\\rightarrow$ `q=성남맛집`\n"
                                "• **실시간 급상승 판정**: `#판교맛집` (최근 24h 참여도 기준선 대비 2.8배 급상승)\n"
                                "※ 고지: Instagram Graph API는 최근 24시간 게시물만 제공하며 기간별 시계열 추이를 제공하지 않습니다."
                            )
                        elif any(w in user_input for w in ["트렌드", "크로스", "쇼핑", "유튜브", "반응", "분석"]):
                            log_status("🎯 **[시나리오 라우터 판정]** `cross_platform_trend` 자동 매칭 (신뢰도: 0.95)")
                            log_status("🔧 **[도구 실행]** `get_shopping_trends` (파라미터: `{'keywords': '러닝화', 'start_date': '2026-01-01', 'end_date': '2026-03-01'}`)")
                            time.sleep(0.2)
                            log_status("✅ **[도구 완료]** `get_shopping_trends` (0.08초) - 네이버 쇼핑 데이터랩 수집 완료")
                            log_status("🔧 **[도구 실행]** `search_youtube_videos` (파라미터: `{'query': '러닝화 추천 트렌드', 'max_results': 5}`)")
                            time.sleep(0.2)
                            log_status("✅ **[도구 완료]** `search_youtube_videos` (0.15초) - 관련 동영상 5건 수집 완료")
                            log_status("⚙️ **[종합 분석 리포트 생성]** 크로스 플랫폼 트렌드 및 시사점 도출")
                            status_box.update(label=f"✅ 크로스 플랫폼 시나리오 완료 (도구/단계 {len(current_tool_logs)}건)", state="complete", expanded=False)

                            kw = "러닝화" if "러닝화" in user_input else "트렌드 상품"
                            final_ans = (
                                f"### 📊 [{kw}] 크로스 플랫폼 트렌드 분석 종합 리포트\n\n"
                                f"**분석 기간**: 2026-01-01 ~ 2026-03-01\n\n"
                                f"#### 1. 📈 네이버 쇼핑 트렌드 요약\n"
                                f"- '{kw}'의 상대 검색비율은 최근 **84.5%**로 전월 대비 가파른 상승세를 보이고 있습니다.\n\n"
                                f"#### 2. 🎬 유튜브 미디어 반응 요약\n"
                                f"- 최신 실착 리뷰 및 가성비 추천 영상 조회수가 10만 회를 돌파하며 높은 관심도를 반영하고 있습니다.\n\n"
                                f"#### 3. 💡 비즈니스 시사점\n"
                                f"- 봄 시즌 진입과 함께 야외 활동 관련 검색량이 급증하고 있으므로, 관련 기획전 및 콘텐츠 마케팅 집중 투자가 권장됩니다."
                            )
                        else:
                            log_status(f"🔍 **[일반 에이전트 실행]** ReAct 도구 호출 루프 가동 (모델: `{model_name}`)")
                            status_box.update(label="✅ 일반 에이전트 답변 완료", state="complete", expanded=False)
                            final_ans = f"'{user_input}'에 대한 일반 에이전트 응답입니다. (Mock 모드: 실제 질의 처리는 사이드바에 API 키를 입력해 주세요.)"

                        mock_msg = {"role": "assistant", "content": final_ans, "tool_logs": current_tool_logs}
                        with response_placeholder.container():
                            _render_agent_message(mock_msg)
                        st.session_state.messages.append(mock_msg)

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
                            # 다음 시나리오 실행이 초기화하기 전에 원본 도구 결과를 복사해 둔다.
                            chart_tool_results = dict(naver_trend_scenario.LAST_RUN_TOOL_RESULTS)
                            status_box.update(label=f"✅ 응답 생성 완료 (`{model_name}` - 도구/단계 {len(current_tool_logs)}건)", state="complete", expanded=False)
                            real_msg = {
                                "role": "assistant",
                                "content": final_ans,
                                "tool_logs": current_tool_logs,
                                "chart_tool_results": chart_tool_results,
                            }
                            with response_placeholder.container():
                                _render_agent_message(real_msg)
                            st.session_state.messages.append(real_msg)
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
# 📋 탭 4: 아키텍처 & 레지스트리 현황 (Explorer)
# ==============================================================================
with tab_explorer:
    st.subheader("📋 시스템 아키텍처 및 레지스트리 탐색기")
    st.caption("프로젝트의 전체 모듈, 도구, 가드레일, 시나리오의 등록 상태와 코드 구조를 확인합니다.")

    st.markdown(
        f'<div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">'
        f'🧠 <b>현재 적용 LLM 모델</b>: <code>{model_name}</code> &nbsp;|&nbsp; '
        f'🌡️ <b>Temperature</b>: <code>{settings.TEMPERATURE}</code> &nbsp;|&nbsp; '
        f'📦 <b>등록 모듈</b>: <code>{len(all_mods)}개</code> &nbsp;|&nbsp; '
        f'🎬 <b>등록 시나리오</b>: <code>{len(all_scens)}개</code>'
        f'</div>',
        unsafe_allow_html=True,
    )

    exp_col1, exp_col2 = st.columns(2)

    with exp_col1:
        st.markdown("#### 📦 등록된 도메인 모듈 (`src.modules`)")
        for mod in all_mods:
            with st.expander(f"🔹 **{mod.name}** - {mod.description}", expanded=True):
                tools = mod.get_tools()
                guardrails = mod.get_guardrails()
                ctx = mod.get_context_provider()

                st.markdown(f"• **보유 도구 ({len(tools)}개)**:")
                for t in tools:
                    st.markdown(f"  - `{t.name}`: {t.description}")

                if guardrails:
                    st.markdown(f"• **가드레일 ({len(guardrails)}개)**:")
                    for g in guardrails:
                        st.markdown(f"  - `{type(g).__name__}`")

                if ctx:
                    st.markdown("• **시스템 프롬프트 지침 snippet**:")
                    st.caption(ctx.get_system_prompt_snippet() or "(없음)")

    with exp_col2:
        st.markdown("#### 🎬 등록된 비즈니스 시나리오 (`src.scenarios`)")
        for scen in all_scens:
            with st.expander(f"🔸 **{scen.name}**", expanded=True):
                st.markdown(f"• **상세 설명**: {scen.description}")
                st.markdown(f"• **필수 도구 의존성**: `{', '.join(scen.required_tool_names)}`")
                st.markdown(f"• **파라미터 모델**: `{scen.parameters_schema.__name__}`")
                
                # 스키마 필드 표시
                fields = getattr(scen.parameters_schema, "model_fields", {})
                st.markdown("• **파라미터 상세 규격**:")
                for fn, fi in fields.items():
                    act_def = get_pydantic_field_default(fi, fn)
                    def_str = repr(act_def) if act_def != "" else "(필수 입력)"
                    st.markdown(f"  - `{fn}`: {fi.description or ''} (기본값: `{def_str}`)")

    st.markdown("---")
    st.markdown("#### 🏛️ 전체 실행 라이프사이클 다이어그램")
    st.markdown(
        """
        ```mermaid
        flowchart TD
            UserQuery["사용자 입력 (Query)"] --> InputGuardrail{"입력 가드레일 검사"}
            InputGuardrail -->|정책 위반| Blocked["🛑 에러 메시지 반환"]
            InputGuardrail -->|통과| Router{"시나리오 라우터\n(Confidence >= 0.6)"}
            
            Router -->|시나리오 매칭| ScenarioPipeline["🎬 시나리오 체인 실행\n(CrossPlatformTrendScenario 등)"]
            ScenarioPipeline --> ScenarioTools["정예 Tool 순차/병렬 실행\n(가드레일 자동 래핑)"]
            ScenarioTools --> Synthesis["LLM 종합 리포트 생성"]
            Synthesis --> FinalResponse["사용자 최종 응답"]
            
            Router -->|매칭 실패/일반 질의| ReActAgent["🤖 ReAct 범용 에이전트\n(AgentExecutor)"]
            ReActAgent --> ModuleRegistryTools["전체 활성 모듈 도구 호출"]
            ModuleRegistryTools --> FinalResponse
        ```
        """
    )
