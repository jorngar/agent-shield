from agents.base import AgentAdapter

_ADAPTER_REGISTRY: dict[str, type[AgentAdapter]] = {}


def register_adapter(name: str):
    """Decorator to register an adapter class under a CLI name."""

    def decorator(cls: type[AgentAdapter]):
        _ADAPTER_REGISTRY[name.lower()] = cls
        return cls

    return decorator


def get_adapter(name: str) -> type[AgentAdapter]:
    """Return the adapter class registered under *name*.

    Raises ``KeyError`` when the name is unknown.
    """
    key = name.lower().replace("-", "_")
    try:
        return _ADAPTER_REGISTRY[key]
    except KeyError:
        available = ", ".join(sorted(_ADAPTER_REGISTRY)) or "(none)"
        raise KeyError(
            f"Unknown agent adapter '{name}'. Available: {available}"
        ) from None


def list_adapters() -> list[str]:
    """Return sorted list of registered adapter names."""
    return sorted(_ADAPTER_REGISTRY)


# Import adapter modules so their @register_adapter decorators execute.
import agents.codex  # noqa: F401, E402
import agents.kilo  # noqa: F401, E402
import agents.claude_code  # noqa: F401, E402
import agents.openclaw  # noqa: F401, E402
import agents.hermes_agent  # noqa: F401, E402
import agents.gemini_cli  # noqa: F401, E402
