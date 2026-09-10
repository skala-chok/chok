import importlib
import inspect
import logging
import pkgutil
from typing import Dict, List, Optional
from .scenario import BaseScenario

logger = logging.getLogger(__name__)


class ScenarioRegistry:
    """N개의 복합 비즈니스 시나리오를 자동 탐색, 등록 및 제공하는 레지스트리."""

    def __init__(self) -> None:
        self._scenarios: Dict[str, BaseScenario] = {}

    def register(self, scenario: BaseScenario) -> None:
        """단일 시나리오 인스턴스를 등록합니다.

        Args:
            scenario: BaseScenario를 구현한 인스턴스.

        Raises:
            TypeError: BaseScenario 인스턴스가 아닐 경우.
        """
        if not isinstance(scenario, BaseScenario):
            raise TypeError(
                f"Expected an instance of BaseScenario, got {type(scenario).__name__}"
            )
        self._scenarios[scenario.name] = scenario
        logger.debug("시나리오 등록 완료: %s", scenario.name)

    def get_scenario(self, name: str) -> Optional[BaseScenario]:
        """시나리오 고유 식별자로 등록된 시나리오 인스턴스를 조회합니다."""
        return self._scenarios.get(name)

    def get_all_scenarios(self) -> List[BaseScenario]:
        """등록된 모든 시나리오 인스턴스 목록을 반환합니다."""
        return list(self._scenarios.values())

    def clear(self) -> None:
        """등록된 모든 시나리오를 제거합니다."""
        self._scenarios.clear()

    def __contains__(self, name: str) -> bool:
        return name in self._scenarios

    def __len__(self) -> int:
        return len(self._scenarios)

    def __getitem__(self, name: str) -> BaseScenario:
        return self._scenarios[name]

    def discover_scenarios(self, package_path: str = "src.scenarios") -> None:
        """scenarios 패키지 하위를 동적으로 탐색하여 BaseScenario 구현체를 자동 인스턴스화하고 등록합니다.

        Args:
            package_path: 탐색 대상 루트 패키지 경로 (기본값: 'src.scenarios')
        """
        try:
            pkg = importlib.import_module(package_path)
        except Exception as e:
            logger.info("시나리오 패키지 로드 생략 또는 실패 (%s): %s", package_path, e)
            return

        if not hasattr(pkg, "__path__"):
            return

        for _, mod_name, is_pkg in pkgutil.iter_modules(pkg.__path__):
            sub_mod = None
            if is_pkg:
                primary_target = f"{package_path}.{mod_name}.scenario"
                try:
                    sub_mod = importlib.import_module(primary_target)
                except Exception:
                    fallback_target = f"{package_path}.{mod_name}"
                    try:
                        sub_mod = importlib.import_module(fallback_target)
                    except Exception as e_fallback:
                        logger.warning(
                            "시나리오 패키지 임포트 실패 (%s): %s",
                            mod_name,
                            e_fallback,
                        )
                        continue
            else:
                target = f"{package_path}.{mod_name}"
                try:
                    sub_mod = importlib.import_module(target)
                except Exception as e:
                    logger.warning("시나리오 모듈 임포트 실패 (%s): %s", target, e)
                    continue

            if sub_mod is None:
                continue

            try:
                for attr_name in dir(sub_mod):
                    try:
                        attr = getattr(sub_mod, attr_name)
                    except Exception:
                        continue

                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, BaseScenario)
                        and attr is not BaseScenario
                        and not inspect.isabstract(attr)
                        and getattr(attr, "__module__", None) == sub_mod.__name__
                    ):
                        try:
                            instance = attr()
                            self.register(instance)
                        except Exception as e_inst:
                            logger.warning(
                                "시나리오 클래스 인스턴스화 실패 (%s in %s): %s",
                                attr_name,
                                sub_mod.__name__,
                                e_inst,
                            )
                            continue
            except Exception as e_scan:
                logger.warning(
                    "시나리오 속성 스캔 실패 (%s): %s",
                    sub_mod.__name__,
                    e_scan,
                )
                continue
