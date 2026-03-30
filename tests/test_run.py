from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "zai-deep-research" / "scripts"


def load_module(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


run_module = load_module("zai_deep_research_run", "run.py")


class FakeBackend:
    def __init__(self, names: set[str]) -> None:
        self.name = "codex"
        self.display_name = "Codex CLI"
        self._names = names

    def is_available(self) -> bool:
        return True

    def list_mcp_names(self, cwd: Path) -> set[str]:
        return self._names


class RunModuleTests(unittest.TestCase):
    def test_coerce_text_output_decodes_bytes(self) -> None:
        self.assertEqual(run_module.coerce_text_output(b"hello"), "hello")
        self.assertEqual(run_module.coerce_text_output("hello"), "hello")
        self.assertEqual(run_module.coerce_text_output(None), "")

    def test_extract_rmcp_fatal_lines(self) -> None:
        sample = """
        2026-03-30T09:22:27Z ERROR rmcp::transport::worker: worker quit with fatal: Unexpected content type
        2026-03-30T09:22:28Z ERROR rmcp::transport::worker: worker quit with fatal: Unexpected content type
        """
        extracted = run_module.extract_rmcp_fatal_lines(sample)
        self.assertEqual(
            extracted,
            [
                "rmcp::transport::worker: worker quit with fatal: Unexpected content type",
            ],
        )

    def test_parse_codex_exec_json_extracts_last_agent_message(self) -> None:
        raw_output = "\n".join(
            [
                '{"type":"thread.started","thread_id":"1"}',
                '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"first"}}',
                '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"second"}}',
                '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
            ]
        )
        assistant_text, usage = run_module.parse_codex_exec_json(raw_output)
        self.assertEqual(assistant_text, "second")
        self.assertEqual(usage, {"input_tokens": 10, "output_tokens": 5})

    def test_codex_mcp_enabled_override_quotes_hyphenated_names(self) -> None:
        self.assertEqual(
            run_module.codex_mcp_enabled_override("cloudflare-api", False),
            "mcp_servers.cloudflare-api.enabled=false",
        )

    def test_parse_generic_mcp_list_handles_remote_url_table(self) -> None:
        sample = """WARNING: proceeding, even though we could not update PATH
Name        Command                                                                                    Args                    Env                                  Cwd            Status   Auth
pencil      /Applications/Pencil.app/Contents/Resources/app.asar.unpacked/out/mcp-server-darwin-arm64  --app desktop           -                                    -              enabled  Unsupported
playwright  npx                                                                                        @playwright/mcp@latest  -                                    -              enabled  Unsupported
vision-zai  npx                                                                                        -y @z_ai/mcp_server     Z_AI_API_KEY=*****, Z_AI_MODE=*****  ~/.codex/tmp/  enabled  Unsupported

Name            Url                                            Bearer Token Env Var                                      Status   Auth
astro_docs      https://mcp.docs.astro.build/mcp               -                                                         enabled  Unsupported
web-reader-zai  https://api.z.ai/api/mcp/web_reader/mcp        -                                                         enabled  Bearer token
web-search-zai  https://api.z.ai/api/mcp/web_search_prime/mcp  Bearer token                                               enabled  Bearer token
zread           https://api.z.ai/api/mcp/zread/mcp             -                                                         enabled  Bearer token
"""

        parsed = run_module.parse_generic_mcp_list(sample)

        self.assertIn("vision-zai", parsed)
        self.assertIn("web-reader-zai", parsed)
        self.assertIn("web-search-zai", parsed)
        self.assertIn("zread", parsed)
        self.assertNotIn("web-search-zai  https", parsed)

    def test_validate_runtime_reports_all_required_mcps(self) -> None:
        config = run_module.load_config(None)
        backend = FakeBackend(
            {
                config.mcp_servers.search,
                config.mcp_servers.reader,
                config.mcp_servers.vision,
                config.mcp_servers.repository,
            }
        )

        report = run_module.validate_runtime(config, backend, REPO_ROOT)

        self.assertTrue(report.is_ok)
        self.assertEqual(report.missing_mcp_names, [])
        self.assertEqual(
            sorted(report.configured_mcp_names),
            sorted(
                [
                    config.mcp_servers.search,
                    config.mcp_servers.reader,
                    config.mcp_servers.vision,
                    config.mcp_servers.repository,
                ]
            ),
        )
        payload = report.to_payload()
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["missing_mcp_names"])

    def test_run_command_handles_timeout_bytes_without_crashing(self) -> None:
        timeout = subprocess.TimeoutExpired(
            cmd=["codex", "exec", "--skip-git-repo-check", "-"],
            timeout=5,
            output=b"partial stdout",
            stderr=b"partial stderr",
        )
        with mock.patch.object(run_module.subprocess, "run", side_effect=timeout):
            with self.assertRaises(run_module.LauncherError) as context:
                run_module.run_command(["codex", "exec", "--skip-git-repo-check", "-"], cwd=REPO_ROOT)
        self.assertIn("command timed out after", str(context.exception))
        self.assertIn("partial stderr", str(context.exception))

    def test_detect_unhealthy_codex_mcps_marks_only_broken_remote_servers(self) -> None:
        backend = run_module.CodexBackend("codex", "codex", "Codex CLI")

        def fake_transport(name: str, cwd: Path) -> str | None:
            transports = {
                "web-search-zai": "streamable_http",
                "web-reader-zai": "streamable_http",
                "vision-zai": "stdio",
                "zread": "streamable_http",
            }
            return transports[name]

        def fake_run_exec_prompt(
            prompt: str,
            cwd: Path,
            *,
            disabled_mcp_names: list[str] | None = None,
            timeout_seconds: int | None = None,
        ) -> run_module.CodexExecOutput:
            del prompt, cwd, timeout_seconds
            disabled = set(disabled_mcp_names or [])
            if "web-search-zai" not in disabled:
                return run_module.CodexExecOutput("OK", None, [])
            if "web-reader-zai" not in disabled:
                return run_module.CodexExecOutput(
                    "OK",
                    None,
                    [
                        "rmcp::transport::worker: worker quit with fatal: web-reader",
                    ],
                )
            if "zread" not in disabled:
                return run_module.CodexExecOutput(
                    "OK",
                    None,
                    [
                        "rmcp::transport::worker: worker quit with fatal: zread",
                    ],
                )
            return run_module.CodexExecOutput("OK", None, [])

        with mock.patch.object(backend, "get_mcp_transport", side_effect=fake_transport):
            with mock.patch.object(backend, "run_exec_prompt", side_effect=fake_run_exec_prompt):
                unhealthy = run_module.detect_unhealthy_codex_mcps(
                    backend,
                    REPO_ROOT,
                    ["web-search-zai", "web-reader-zai", "vision-zai", "zread"],
                    ["web-search-zai", "web-reader-zai", "vision-zai", "zread"],
                )

        self.assertEqual(
            unhealthy,
            {
                "web-reader-zai": "rmcp::transport::worker: worker quit with fatal: web-reader",
                "zread": "rmcp::transport::worker: worker quit with fatal: zread",
            },
        )


if __name__ == "__main__":
    unittest.main()
