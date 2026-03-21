import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


class ConfigEnvLoadingTests(unittest.TestCase):
    def test_load_env_file_parses_and_preserves_existing_values(self):
        sys.modules.pop("config", None)
        import config

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "# comment",
                        "AGENT_SHIELD_BACKEND_URL=https://example.execute-api.ap-southeast-1.amazonaws.com",
                        "export AGENT_SHIELD_OLLAMA_MODEL='qwen-test'",
                    ]
                ),
                encoding="utf-8",
            )

            original_backend = os.environ.get("AGENT_SHIELD_BACKEND_URL")
            original_model = os.environ.get("AGENT_SHIELD_OLLAMA_MODEL")
            os.environ["AGENT_SHIELD_BACKEND_URL"] = "http://already-set"
            os.environ.pop("AGENT_SHIELD_OLLAMA_MODEL", None)

            try:
                config._load_env_file(env_path)
                self.assertEqual(os.environ["AGENT_SHIELD_BACKEND_URL"], "http://already-set")
                self.assertEqual(os.environ["AGENT_SHIELD_OLLAMA_MODEL"], "qwen-test")
            finally:
                if original_backend is None:
                    os.environ.pop("AGENT_SHIELD_BACKEND_URL", None)
                else:
                    os.environ["AGENT_SHIELD_BACKEND_URL"] = original_backend

                if original_model is None:
                    os.environ.pop("AGENT_SHIELD_OLLAMA_MODEL", None)
                else:
                    os.environ["AGENT_SHIELD_OLLAMA_MODEL"] = original_model

    def test_load_env_file_allows_later_lines_in_same_file_to_override(self):
        sys.modules.pop("config", None)
        import config

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "AGENT_SHIELD_CODEX_ARGS=--dangerously-skip-possible-errors",
                        "AGENT_SHIELD_CODEX_ARGS=-s read-only",
                    ]
                ),
                encoding="utf-8",
            )

            original_value = os.environ.get("AGENT_SHIELD_CODEX_ARGS")
            os.environ.pop("AGENT_SHIELD_CODEX_ARGS", None)

            try:
                config._load_env_file(env_path)
                self.assertEqual(os.environ["AGENT_SHIELD_CODEX_ARGS"], "-s read-only")
            finally:
                if original_value is None:
                    os.environ.pop("AGENT_SHIELD_CODEX_ARGS", None)
                else:
                    os.environ["AGENT_SHIELD_CODEX_ARGS"] = original_value

    def test_normalize_codex_args_remaps_legacy_flag(self):
        sys.modules.pop("config", None)
        import config

        normalized = config._normalize_codex_args(["--dangerously-skip-possible-errors"])
        self.assertEqual(normalized, ["--dangerously-bypass-approvals-and-sandbox"])


if __name__ == "__main__":
    unittest.main()
