"""동적 모듈 탐색 및 플러그인 레지스트리 (Dynamic Module Registry).

[🏛️ 아키텍처 설계 & 코드 참고사항]
- 런타임 리플렉션(Reflection) 기반 자동 탐색:
  `pkgutil.iter_modules`와 `importlib`을 활용하여 `src/modules/` 하위의 모든 패키지를 스캔하고,
  `BaseAgentModule`을 구현한 클래스를 찾아 자동으로 인스턴스화 및 등록합니다.
- 제로 코드 수정 확장성 (OCP):
  신규 기능/도메인 모듈을 추가할 때 코어 레지스트리 코드를 단 한 줄도 수정할 필요가 없으며,
  `is_enabled()`를 통해 필요한 API 키가 없는 모듈은 자동으로 비활성화(Graceful Degradation)됩니다.
"""

import importlib
import inspect
import logging
import pkgutil
from typing import Dict, List, Optional
from .base import BaseAgentModule

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """도메인 에이전트 모듈을 동적으로 탐색, 등록, 관리하는 중앙 레지스트리."""

    def __init__(self) -> None:
        self._modules: Dict[str, BaseAgentModule] = {}

    def register(self, module: BaseAgentModule) -> None:
        """단일 모듈 인스턴스를 레지스트리에 등록합니다.

        Args:
            module: BaseAgentModule을 구현한 인스턴스.

        Raises:
            TypeError: 인자가 BaseAgentModule 인스턴스가 아닐 경우 발생.
        """
        if not isinstance(module, BaseAgentModule):
            raise TypeError(
                f"Expected an instance of BaseAgentModule, got {type(module).__name__}"
            )
        self._modules[module.name] = module
        logger.debug("모듈 등록 완료: %s (활성화: %s)", module.name, module.is_enabled())

    def get_enabled_modules(self) -> List[BaseAgentModule]:
        """활성화(is_enabled() == True) 상태인 모듈 인스턴스 목록을 반환합니다."""
        return [m for m in self._modules.values() if m.is_enabled()]

    def get_module(self, name: str) -> Optional[BaseAgentModule]:
        """고유 이름을 기준으로 등록된 모듈 인스턴스를 조회합니다."""
        return self._modules.get(name)

    def get_all_modules(self) -> List[BaseAgentModule]:
        """등록된 모든 모듈 인스턴스(활성 및 비활성 포함) 목록을 반환합니다."""
        return list(self._modules.values())

    def clear(self) -> None:
        """등록된 모든 모듈을 레지스트리에서 초기화(제거)합니다."""
        self._modules.clear()

    def __contains__(self, name: str) -> bool:
        return name in self._modules

    def __len__(self) -> int:
        return len(self._modules)

    def __getitem__(self, name: str) -> BaseAgentModule:
        return self._modules[name]

    def discover_modules(self, package_path: str = "src.modules") -> None:
        """지정된 패키지 경로를 리플렉션으로 동적 탐색하여 BaseAgentModule 구현체를 인스턴스화하고 자동 등록합니다.

        Args:
            package_path: 점(.)으로 구분된 파이썬 패키지 경로 (기본값: 'src.modules').
        """
        try:
            pkg = importlib.import_module(package_path)
        except Exception as e:
            logger.warning("Failed to import root package %s: %s", package_path, e)
            return

        if not hasattr(pkg, "__path__"):
            return

        for _, mod_name, is_pkg in pkgutil.iter_modules(pkg.__path__):
            sub_mod = None
            if is_pkg:
                # 아키텍처 규칙: 각 워커는 <pkg>.<name>.module 경로에 BaseAgentModule을 구현합니다.
                primary_target = f"{package_path}.{mod_name}.module"
                try:
                    sub_mod = importlib.import_module(primary_target)
                except Exception as e_primary:
                    fallback_target = f"{package_path}.{mod_name}"
                    try:
                        sub_mod = importlib.import_module(fallback_target)
                    except Exception as e_fallback:
                        logger.warning(
                            "Failed to import module package %s (tried %s: %s, %s: %s)",
                            mod_name,
                            primary_target,
                            e_primary,
                            fallback_target,
                            e_fallback,
                        )
                        continue
            else:
                target = f"{package_path}.{mod_name}"
                try:
                    sub_mod = importlib.import_module(target)
                except Exception as e:
                    logger.warning("Failed to import module %s: %s", target, e)
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
                        and issubclass(attr, BaseAgentModule)
                        and attr is not BaseAgentModule
                        and not inspect.isabstract(attr)
                        and getattr(attr, "__module__", None) == sub_mod.__name__
                    ):
                        try:
                            instance = attr()
                            self.register(instance)
                        except Exception as e_inst:
                            logger.warning(
                                "Failed to instantiate module class %s in %s: %s",
                                attr_name,
                                sub_mod.__name__,
                                e_inst,
                            )
                            continue
            except Exception as e_scan:
                logger.warning(
                    "Failed to scan attributes of module %s: %s",
                    sub_mod.__name__,
                    e_scan,
                )
                continue

        logger.info("모듈 자동 탐색 완료: 총 %d개 등록됨", len(self._modules))

