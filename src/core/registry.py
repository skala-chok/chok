import importlib
import inspect
import pkgutil
from typing import Dict, List, Optional
from .base import BaseAgentModule


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
        except ImportError:
            return

        if not hasattr(pkg, "__path__"):
            return

        for _, mod_name, is_pkg in pkgutil.iter_modules(pkg.__path__):
            sub_mod = None
            if is_pkg:
                # Per project architecture, workers implement BaseAgentModule in <pkg>.<name>.module
                try:
                    sub_mod = importlib.import_module(
                        f"{package_path}.{mod_name}.module"
                    )
                except ImportError:
                    try:
                        sub_mod = importlib.import_module(
                            f"{package_path}.{mod_name}"
                        )
                    except ImportError:
                        continue
            else:
                try:
                    sub_mod = importlib.import_module(
                        f"{package_path}.{mod_name}"
                    )
                except ImportError:
                    continue

            if sub_mod is None:
                continue

            for attr_name in dir(sub_mod):
                attr = getattr(sub_mod, attr_name)
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, BaseAgentModule)
                    and attr is not BaseAgentModule
                    and not inspect.isabstract(attr)
                ):
                    try:
                        instance = attr()
                        self.register(instance)
                    except Exception:
                        continue
