import pytest
from unittest.mock import MagicMock, patch
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool, tool
from langchain_core.messages import AIMessage

from src.core.scenario import BaseScenario, ScenarioExecutionPlan, ScenarioResult
from src.core.scenario_registry import ScenarioRegistry
from src.core.router import ScenarioRouter, ScenarioRoutingDecision
from src.core.agent import AgentRunner
from src.core.registry import ModuleRegistry
from src.scenarios.cross_platform_trend.scenario import (
    CrossPlatformTrendScenario,
    CrossPlatformTrendParams,
)


# 테스트용 Mock 시나리오 및 파라미터
class DummyParams(BaseModel):
    query_text: str = Field(description="더미 텍스트")


class DummyScenario(BaseScenario):
    @property
    def name(self) -> str:
        return "dummy_scenario"

    @property
    def description(self) -> str:
        return "더미 테스트용 시나리오입니다."

    @property
    def parameters_schema(self):
        return DummyParams

    @property
    def required_tool_names(self):
        return ["dummy_tool"]

    def execute(self, params, tools, context=None) -> str:
        tool_res = ""
        if "dummy_tool" in tools:
            tool_res = tools["dummy_tool"].invoke({"text": params.query_text})
        return f"DummyScenario 실행 완료: {params.query_text} (도구결과: {tool_res})"


@tool
def dummy_tool(text: str) -> str:
    """더미 테스트 도구"""
    return f"Processed: {text}"


class TestScenarioAbstraction:
    def test_base_scenario_subclass_success(self):
        scenario = DummyScenario()
        assert scenario.name == "dummy_scenario"
        assert scenario.description == "더미 테스트용 시나리오입니다."
        assert scenario.required_tool_names == ["dummy_tool"]
        assert scenario.parameters_schema == DummyParams

    def test_scenario_execution_plan_model(self):
        plan = ScenarioExecutionPlan(
            scenario_name="dummy_scenario",
            confidence=0.95,
            parameters={"query_text": "테스트"},
            reasoning="테스트 목적",
        )
        assert plan.scenario_name == "dummy_scenario"
        assert plan.confidence == 0.95
        assert plan.parameters["query_text"] == "테스트"

    def test_base_scenario_run_template_success(self):
        scenario = DummyScenario()
        params = DummyParams(query_text="성공테스트")
        tools = {"dummy_tool": dummy_tool}

        with patch("src.core.scenario.logger.info") as mock_info:
            output = scenario.run(params, tools)
            assert "DummyScenario 실행 완료: 성공테스트" in output
            # 시작 로그 및 완료 로그가 남았는지 확인
            assert mock_info.call_count >= 2

    def test_base_scenario_run_template_failure(self):
        class FailingScenario(BaseScenario):
            @property
            def name(self): return "fail_scen"
            @property
            def description(self): return "실패 시나리오"
            @property
            def parameters_schema(self): return DummyParams
            def execute(self, params, tools, context=None):
                raise RuntimeError("의도된 실행 에러")

        scenario = FailingScenario()
        params = DummyParams(query_text="에러")
        with patch("src.core.scenario.logger.error") as mock_err:
            with pytest.raises(RuntimeError) as exc_info:
                scenario.run(params, {})
            assert "의도된 실행 에러" in str(exc_info.value)
            mock_err.assert_called_once()


class TestScenarioRegistry:
    def test_register_and_get(self):
        registry = ScenarioRegistry()
        scenario = DummyScenario()
        registry.register(scenario)

        assert len(registry) == 1
        assert "dummy_scenario" in registry
        assert registry.get_scenario("dummy_scenario") is scenario
        assert registry["dummy_scenario"] is scenario
        assert len(registry.get_all_scenarios()) == 1

    def test_register_type_error(self):
        registry = ScenarioRegistry()
        with pytest.raises(TypeError):
            registry.register("not_a_scenario")  # type: ignore

    def test_clear(self):
        registry = ScenarioRegistry()
        registry.register(DummyScenario())
        registry.clear()
        assert len(registry) == 0

    def test_discover_scenarios_built_in(self):
        registry = ScenarioRegistry()
        registry.discover_scenarios("src.scenarios")
        # src/scenarios/cross_platform_trend 가 자동 등록되어야 함
        assert "cross_platform_trend" in registry
        scenario = registry["cross_platform_trend"]
        assert isinstance(scenario, CrossPlatformTrendScenario)


class TestScenarioRouter:
    def test_route_with_no_scenarios(self):
        registry = ScenarioRegistry()
        router = ScenarioRouter(registry=registry)
        assert router.route("아무 질문") is None

    def test_route_successful_matching(self):
        registry = ScenarioRegistry()
        registry.register(DummyScenario())

        mock_llm = MagicMock()
        mock_decision = ScenarioRoutingDecision(
            scenario_name="dummy_scenario",
            confidence=0.9,
            parameters={"query_text": "신제품 반응"},
            reasoning="더미 시나리오와 일치함",
        )
        
        # with_structured_output 체인 모킹
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_decision
        mock_llm.with_structured_output.return_value = MagicMock(
            __or__=MagicMock(return_value=mock_structured)
        )

        router = ScenarioRouter(registry=registry, llm=mock_llm, confidence_threshold=0.6)
        
        with patch.object(router, "_build_scenario_catalog", return_value="catalog"):
            with patch("src.core.router.ChatPromptTemplate.from_messages") as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt.__or__.return_value = mock_structured
                mock_prompt_cls.return_value = mock_prompt

                plan = router.route("신제품 반응 분석해줘")
                assert plan is not None
                assert plan.scenario_name == "dummy_scenario"
                assert plan.confidence == 0.9
                assert plan.parameters == {"query_text": "신제품 반응"}

    def test_route_low_confidence_fallback(self):
        registry = ScenarioRegistry()
        registry.register(DummyScenario())

        mock_llm = MagicMock()
        mock_decision = ScenarioRoutingDecision(
            scenario_name="dummy_scenario",
            confidence=0.4,  # 기준(0.6) 미만
            parameters={"query_text": "불확실"},
        )
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_decision

        router = ScenarioRouter(registry=registry, llm=mock_llm, confidence_threshold=0.6)
        with patch("src.core.router.ChatPromptTemplate.from_messages") as mock_prompt_cls:
            mock_prompt = MagicMock()
            mock_prompt.__or__.return_value = mock_structured
            mock_prompt_cls.return_value = mock_prompt

            plan = router.route("애매한 질문")
            assert plan is None


class TestAgentRunnerWithScenario:
    def test_agent_runner_executes_scenario_when_routed(self):
        mod_registry = ModuleRegistry()
        scenario_registry = ScenarioRegistry()
        scenario = DummyScenario()
        scenario_registry.register(scenario)

        # Mock Router that returns a valid plan
        mock_router = MagicMock()
        mock_router.route.return_value = ScenarioExecutionPlan(
            scenario_name="dummy_scenario",
            confidence=0.9,
            parameters={"query_text": "나이키"},
        )

        mock_llm = MagicMock()
        runner = AgentRunner(
            registry=mod_registry,
            llm=mock_llm,
            scenario_registry=scenario_registry,
            router=mock_router,
        )

        output = runner.run("나이키 트렌드 알려줘")
        assert "DummyScenario 실행 완료: 나이키" in output

    def test_agent_runner_fallback_when_router_returns_none(self):
        mod_registry = ModuleRegistry()
        scenario_registry = ScenarioRegistry()
        scenario_registry.register(DummyScenario())

        mock_router = MagicMock()
        mock_router.route.return_value = None  # 매칭 실패 -> 일반 에이전트 폴백

        mock_llm = MagicMock()
        with patch("src.core.agent.AgentExecutor.invoke", return_value={"output": "일반 답변입니다"}):
            runner = AgentRunner(
                registry=mod_registry,
                llm=mock_llm,
                scenario_registry=scenario_registry,
                router=mock_router,
            )
            output = runner.run("단순 인사")
            assert output == "일반 답변입니다"


class TestCrossPlatformTrendScenario:
    def test_cross_platform_trend_execution_flow(self):
        scenario = CrossPlatformTrendScenario()
        assert "search_hashtag_id" in scenario.required_tool_names
        assert "get_hashtag_top_media" in scenario.required_tool_names

        params = CrossPlatformTrendParams(
            keyword="#러닝화",
            start_date="2026-01-01",
            end_date="2026-02-01",
        )

        mock_trend_tool = MagicMock()
        mock_trend_tool.invoke.return_value = "쇼핑트렌드: 러닝화 지수 80"

        mock_yt_tool = MagicMock()
        mock_yt_tool.invoke.return_value = "유튜브영상: 러닝화 추천 Top 3"

        mock_ig_search = MagicMock()
        mock_ig_search.invoke.return_value = "• 해시태그 ID: 17841400000000001"

        mock_ig_top = MagicMock()
        mock_ig_top.invoke.return_value = "인스타그램 인기 게시물: #러닝화 참여도 150.0"

        tools = {
            "get_shopping_trends": mock_trend_tool,
            "search_youtube_videos": mock_yt_tool,
            "search_hashtag_id": mock_ig_search,
            "get_hashtag_top_media": mock_ig_top,
        }

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="종합 크로스 분석 리포트 내용")

        with patch("src.scenarios.cross_platform_trend.scenario.ChatPromptTemplate.from_messages") as mock_p:
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = AIMessage(content="종합 크로스 분석 리포트 내용")
            mock_p.return_value.__or__.return_value = mock_chain

            result = scenario.execute(params, tools, context={"llm": mock_llm})
            assert result == "종합 크로스 분석 리포트 내용"
            mock_trend_tool.invoke.assert_called_once()
            mock_yt_tool.invoke.assert_called_once()
            mock_ig_search.invoke.assert_called_once_with({"query": "러닝화"})
            mock_ig_top.invoke.assert_called_once_with({"hashtag_id": "17841400000000001"})

    def test_cross_platform_trend_fallback_formatting(self):
        scenario = CrossPlatformTrendScenario()
        params = CrossPlatformTrendParams(
            keyword="러닝화",
            start_date="2026-01-01",
            end_date="2026-02-01",
        )

        mock_trend_tool = MagicMock()
        mock_trend_tool.invoke.return_value = "쇼핑트렌드 데이터"

        mock_yt_tool = MagicMock()
        mock_yt_tool.invoke.return_value = "유튜브 데이터"

        mock_ig_search = MagicMock()
        mock_ig_search.invoke.return_value = "• 해시태그 ID: 17841400000000001"

        mock_ig_top = MagicMock()
        mock_ig_top.invoke.return_value = "인스타그램 인기 게시물 데이터"

        tools = {
            "get_shopping_trends": mock_trend_tool,
            "search_youtube_videos": mock_yt_tool,
            "search_hashtag_id": mock_ig_search,
            "get_hashtag_top_media": mock_ig_top,
        }

        result = scenario.execute(params, tools, context={})
        assert "#### 1. 네이버 쇼핑 트렌드" in result
        assert "#### 2. 유튜브 관련 영상" in result
        assert "#### 3. 인스타그램 해시태그 반응" in result
        assert "인스타그램 인기 게시물 데이터" in result

    def test_cross_platform_trend_korean_fallback_id(self):
        """한글 키워드 기반 Fallback Mock ID(예: fallback_ht_러닝화)가 온전히 추출되는지 검증."""
        scenario = CrossPlatformTrendScenario()
        params = CrossPlatformTrendParams(keyword="러닝화")

        mock_ig_search = MagicMock()
        mock_ig_search.invoke.return_value = "[Fallback Mock] 해시태그 ID: fallback_ht_러닝화"

        mock_ig_top = MagicMock()
        mock_ig_top.invoke.return_value = "[Fallback Mock] 누적 인기 게시물: #러닝화"

        tools = {
            "search_hashtag_id": mock_ig_search,
            "get_hashtag_top_media": mock_ig_top,
        }

        result = scenario.execute(params, tools, context={})
        mock_ig_top.invoke.assert_called_once_with({"hashtag_id": "fallback_ht_러닝화"})
        assert "fallback_ht_러닝화" not in result or "[Fallback Mock]" in result

    def test_cross_platform_trend_missing_instagram_tools(self):
        """인스타그램 도구가 미등록 상태일 때 크래시 없이 기본 안내 메시지로 폴백되는지 검증."""
        scenario = CrossPlatformTrendScenario()
        params = CrossPlatformTrendParams(keyword="러닝화")

        tools = {
            "get_shopping_trends": MagicMock(invoke=MagicMock(return_value="쇼핑")),
            "search_youtube_videos": MagicMock(invoke=MagicMock(return_value="유튜브")),
        }

        result = scenario.execute(params, tools, context={})
        assert "인스타그램 도구를 사용할 수 없습니다." in result

    def test_cross_platform_trend_instagram_search_failure(self):
        """해시태그 ID 조회 실패 시 인기 게시물 도구를 허위 ID로 호출하지 않고 안내 메시지를 보존하는지 검증."""
        scenario = CrossPlatformTrendScenario()
        params = CrossPlatformTrendParams(keyword="존재하지않는태그")

        mock_ig_search = MagicMock()
        mock_ig_search.invoke.return_value = "해시태그 '존재하지않는태그'에 대한 ID를 찾을 수 없습니다."

        mock_ig_top = MagicMock()

        tools = {
            "search_hashtag_id": mock_ig_search,
            "get_hashtag_top_media": mock_ig_top,
        }

        result = scenario.execute(params, tools, context={})
        mock_ig_top.invoke.assert_not_called()
        assert "해시태그 '존재하지않는태그'에 대한 ID를 찾을 수 없습니다." in result


