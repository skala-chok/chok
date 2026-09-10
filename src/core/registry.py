import importlib
import inspect
import logging
import pkgutil
from typing import Dict, List, Optional
from .base import BaseAgentModule

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """Discovers, registers, and provides access to domain agent modules."""

    def __init__(self) -> None:
        self._modules: Dict[str, BaseAgentModule] = {}

    def register(self, module: BaseAgentModule) -> None:
        """Register a single module instance.

        Args:
            module: An instance of BaseAgentModule.

        Raises:
            TypeError: If module is not an instance of BaseAgentModule.
        """
        if not isinstance(module, BaseAgentModule):
            raise TypeError(
                f"Expected an instance of BaseAgentModule, got {type(module).__name__}"
            )
        self._modules[module.name] = module

    def get_enabled_modules(self) -> List[BaseAgentModule]:
        """Return only registered modules whose is_enabled() returns True."""
        return [m for m in self._modules.values() if m.is_enabled()]

    def get_module(self, name: str) -> Optional[BaseAgentModule]:
        """Retrieve a registered module by its unique name."""
        return self._modules.get(name)

    def get_all_modules(self) -> List[BaseAgentModule]:
        """Return all registered module instances (both enabled and disabled)."""
        return list(self._modules.values())

    def clear(self) -> None:
        """Clear all registered modules."""
        self._modules.clear()

    def __contains__(self, name: str) -> bool:
        return name in self._modules

    def __len__(self) -> int:
        return len(self._modules)

    def __getitem__(self, name: str) -> BaseAgentModule:
        return self._modules[name]

    def discover_modules(self, package_path: str = "src.modules") -> None:
        """Dynamically scan packages inside modules directory and instantiate BaseAgentModule implementations.

        Args:
            package_path: Dot-separated python package path (default: 'src.modules').
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
                # Per project architecture, workers implement BaseAgentModule in <pkg>.<name>.module
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

