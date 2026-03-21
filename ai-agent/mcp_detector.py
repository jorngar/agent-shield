import re
from typing import List, Dict, Optional, Tuple
from config import MCP_PATTERNS, ALLOWED_COMMANDS


class MCPDetector:
    """Detects MCP server usage attempts in agent commands."""

    def __init__(self):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in MCP_PATTERNS]
        self.detected_mcps: List[Dict] = []

    def scan_command(self, command: str) -> Tuple[bool, List[str]]:
        """Scan a command for MCP patterns. Returns (is_mcp, matched_patterns)."""
        matched = []
        for pattern in self.patterns:
            if pattern.search(command):
                matched.append(pattern.pattern)
        return len(matched) > 0, matched

    def scan_content(self, content: str) -> Tuple[bool, List[str], str]:
        """Scan content for MCP usage. Returns (is_mcp, matched_patterns, mcp_type)."""
        matched = []
        mcp_type = "unknown"

        content_lower = content.lower()

        if "mcp://" in content_lower or "npx mcp" in content_lower:
            matched.append("mcp://")
            mcp_type = "mcp_protocol"

        if "@modelcontextprotocol" in content_lower:
            matched.append("@modelcontextprotocol")
            mcp_type = "npm_mcp_package"

        mcp_servers = [
            ("filesystem", "filesystem"),
            ("brave-search", "brave_search"),
            ("github-tools", "github"),
            ("slack-mcp", "slack"),
            ("sqlite", "sqlite"),
            ("aws-kb", "aws_knowledge"),
            ("azure-openai-mcp", "azure_openai"),
            ("everything", "everything"),
            ("puppeteer", "puppeteer"),
        ]

        for server_name, server_type in mcp_servers:
            if server_name in content_lower:
                matched.append(server_name)
                mcp_type = server_type

        return len(matched) > 0, matched, mcp_type

    def is_allowed_command(self, command: str) -> bool:
        """Check if command is in allowed list."""
        command_parts = command.strip().split()
        if not command_parts:
            return True
        return command_parts[0] in ALLOWED_COMMANDS

    def detect(self, content: str) -> Optional[Dict]:
        """Full detection returning details if MCP detected."""
        is_mcp, matched_patterns, mcp_type = self.scan_content(content)

        if is_mcp:
            detection = {
                "detected": True,
                "type": mcp_type,
                "matched_patterns": matched_patterns,
                "severity": "high",
            }
            self.detected_mcps.append(detection)
            return detection

        return None


def create_mcp_detector() -> MCPDetector:
    return MCPDetector()
