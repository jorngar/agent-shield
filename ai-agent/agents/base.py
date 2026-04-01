"""AgentAdapter — abstract interface every supported agent must implement."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple


class AgentAdapter(ABC):
    """Interface for agent-specific behaviour that the interceptor delegates to."""

    # ---- identity ----------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in logs, API payloads, and CLI ``--agent``."""

    # ---- launch ------------------------------------------------------------

    @abstractmethod
    def resolve_command(self, user_args: Optional[List[str]]) -> List[str]:
        """Return the full argv (including the executable) to launch the agent.

        ``user_args`` are extra CLI flags the user passes after ``--``.
        """

    # ---- process identity --------------------------------------------------

    @abstractmethod
    def is_own_process(self, cmdline: str) -> bool:
        """Return *True* if *cmdline* belongs to this agent's own runtime."""

    @abstractmethod
    def build_identity_tokens(self, cmd: List[str]) -> Set[str]:
        """Tokens that identify this agent's process tree (for dedup)."""

    @abstractmethod
    def sanitize_cmdline_for_risk(self, cmdline: str) -> str:
        """Strip agent-specific config flags that bias risk analysis."""

    # ---- MCP discovery -----------------------------------------------------

    @abstractmethod
    def discover_mcp_targets(self) -> Tuple[Set[str], Set[int]]:
        """Discover configured MCP targets from this agent's config.

        Returns ``(hosts, ports)``.
        """

    # ---- API / network classification --------------------------------------

    @abstractmethod
    def is_own_api_connection(
        self,
        cmdline: str,
        remote_host: str,
        port: Optional[int],
        process_role: str,
    ) -> Tuple[bool, str]:
        """Detect connections to this agent's own model API.

        Returns ``(is_api, reason)``.
        """

    @property
    def responses_api_hosts(self) -> Set[str]:
        """Hosts this agent uses for model API calls."""
        return set()

    # ---- agent-specific config flags to sanitise ---------------------------

    @property
    def config_flag_patterns(self) -> List[str]:
        """Regex patterns for agent-specific config flags to sanitise."""
        return []
