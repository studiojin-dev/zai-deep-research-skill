from __future__ import annotations

import io
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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
        self.prompts: list[str] = []
        self.prompt_text_by_step: dict[str, str] = {}

    def is_available(self) -> bool:
        return True

    def list_mcp_names(self, cwd: Path) -> set[str]:
        return self._names

    def run_prompt(
        self,
        prompt: str,
        cwd: Path,
        *,
        disabled_mcp_names: list[str] | None = None,
        progress_callback=None,
        step_name: str | None = None,
        iteration: int | None = None,
    ) -> str:
        del cwd, disabled_mcp_names, progress_callback, iteration
        self.prompts.append(step_name or "unknown")
        if step_name is not None:
            self.prompt_text_by_step[step_name] = prompt
        if step_name == "planner":
            return json_dumps(
                {
                    "clarified_query": "q",
                    "quality_goal": "standard",
                    "need_user_input": False,
                    "questions": [],
                    "sub_questions": ["q"],
                    "recommended_mcps": sorted(self._names),
                }
            )
        if step_name == "researcher":
            return json_dumps(
                {
                    "findings": [
                        {
                            "title": "x",
                            "url": "https://example.com",
                            "summary": "s",
                            "why_it_matters": "m",
                            "evidence_type": "web_page",
                        }
                    ],
                    "knowledge_gaps": [],
                    "comparisons_to_check": [],
                    "counterexamples_to_check": [],
                    "similar_cases_to_check": [],
                }
            )
        if step_name == "summarizer":
            return json_dumps(
                {
                    "iteration_summary_md": "summary",
                    "knowledge_gaps": [],
                    "comparisons_to_check": [],
                    "counterexamples_to_check": [],
                    "similar_cases_to_check": [],
                    "next_queries": [],
                }
            )
        if step_name == "synthesizer":
            return "# Title\n## Research Brief\nok"
        raise AssertionError(f"unexpected step {step_name}")


def json_dumps(payload) -> str:
    import json

    return json.dumps(payload)


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
        self.assertIn("lexical_memory_available", payload)
        self.assertIn("vector_memory_available", payload)
        self.assertEqual(
            payload["vector_memory_available"],
            payload["lexical_memory_available"],
        )
        self.assertIn("vector_memory_available", payload["deprecated_fields"])

    def test_load_config_accepts_legacy_vector_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "skill_name": "zai-deep-research",
                        "storage": {
                            "data_dir": "./.zai-deep-research",
                            "memory_db_path": "./.zai-deep-research/memory.sqlite",
                            "vector_index_path": "./.zai-deep-research/vector.index",
                            "vector_metadata_path": "./.zai-deep-research/vector.jsonl",
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = run_module.load_config(str(config_path))

        self.assertEqual(
            config.deprecated_config_keys_detected,
            ("storage.vector_index_path", "storage.vector_metadata_path"),
        )

    def test_validate_runtime_reports_deprecated_config_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "skill_name": "zai-deep-research",
                        "storage": {
                            "data_dir": "./.zai-deep-research",
                            "memory_db_path": "./.zai-deep-research/memory.sqlite",
                            "vector_index_path": "./.zai-deep-research/vector.index",
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = run_module.load_config(str(config_path))

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
        self.assertTrue(report.warnings)
        self.assertIn("storage.vector_index_path", report.warnings[0])
        self.assertEqual(
            report.deprecated_config_keys_detected,
            ["storage.vector_index_path"],
        )

    def test_cli_validate_json_keeps_validation_shape_for_invalid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "skill_name": "zai-deep-research",
                        "runtime": {
                            "client": "bogus",
                        },
                        "storage": {
                            "data_dir": "./.zai-deep-research",
                            "memory_db_path": "./.zai-deep-research/memory.sqlite",
                            "vector_index_path": "./.zai-deep-research/vector.index",
                        },
                        "mcp_servers": {
                            "search": "legacy-search",
                            "reader": "legacy-reader",
                            "vision": "legacy-vision",
                            "repository": "legacy-repository",
                        },
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = run_module.cli(
                    ["--validate", "--json", "--config", str(config_path)]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["client"], "bogus")
        self.assertEqual(
            payload["required_mcp_names"],
            [
                "legacy-search",
                "legacy-reader",
                "legacy-vision",
                "legacy-repository",
            ],
        )
        self.assertEqual(
            payload["missing_mcp_names"],
            payload["required_mcp_names"],
        )
        self.assertIn("vector_memory_available", payload)
        self.assertEqual(
            payload["vector_memory_available"],
            payload["lexical_memory_available"],
        )
        self.assertIn("vector_memory_available", payload["deprecated_fields"])
        self.assertEqual(
            payload["deprecated_config_keys_detected"],
            ["storage.vector_index_path"],
        )
        self.assertTrue(payload["warnings"])
        self.assertIn("storage.vector_index_path", payload["warnings"][0])

    def test_cli_validate_json_keeps_validation_shape_for_backend_selection_failure(self) -> None:
        unavailable_backend = mock.Mock()
        unavailable_backend.is_available.return_value = False

        stdout = io.StringIO()
        with mock.patch.object(run_module, "get_backend", return_value=unavailable_backend):
            with redirect_stdout(stdout):
                exit_code = run_module.cli(
                    ["--validate", "--json", "--client", "gemini"]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["client"], "gemini")
        self.assertEqual(payload["configured_mcp_names"], [])
        self.assertEqual(
            payload["required_mcp_names"],
            [
                "web-search-zai",
                "web-reader-zai",
                "vision-zai",
                "zread",
            ],
        )
        self.assertEqual(
            payload["missing_mcp_names"],
            payload["required_mcp_names"],
        )
        self.assertIn("vector_memory_available", payload)
        self.assertIn("vector_memory_available", payload["deprecated_fields"])

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
            progress_callback=None,
            step_name=None,
            iteration=None,
        ) -> run_module.CodexExecOutput:
            del prompt, cwd, timeout_seconds, progress_callback, step_name, iteration
            disabled = set(disabled_mcp_names or [])
            if "web-search-zai" not in disabled:
                return run_module.CodexExecOutput("OK", None, [], "", "")
            if "web-reader-zai" not in disabled:
                return run_module.CodexExecOutput(
                    "OK",
                    None,
                    [
                        "rmcp::transport::worker: worker quit with fatal: web-reader",
                    ],
                    "",
                    "",
                )
            if "zread" not in disabled:
                return run_module.CodexExecOutput(
                    "OK",
                    None,
                    [
                        "rmcp::transport::worker: worker quit with fatal: zread",
                    ],
                    "",
                    "",
                )
            return run_module.CodexExecOutput("OK", None, [], "", "")

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

    def test_run_tracker_records_transitions(self) -> None:
        tracker = run_module.RunTracker(emit_progress=False)
        tracker.record(step_name="planner", status="running", severity="info", message="start")
        tracker.record(step_name="planner", status="succeeded", severity="info", message="done")
        tracker.record(step_name="researcher", status="skipped", severity="warning", message="skip", iteration=1)
        tracker.record(step_name="finalize", status="aborted", severity="fatal", message="abort")
        self.assertEqual(len(tracker.step_events), 4)
        self.assertEqual(tracker.skipped_steps, 1)
        self.assertEqual(tracker.failed_steps, 1)

    def test_classify_launcher_error_marks_core_step_as_fatal(self) -> None:
        classified = run_module.classify_launcher_error("planner", run_module.LauncherError("command timed out"))
        self.assertEqual(classified.severity, "fatal")
        self.assertEqual(classified.cause, "timeout")

    def test_classify_launcher_error_marks_iteration_step_as_error(self) -> None:
        classified = run_module.classify_launcher_error(
            "researcher",
            run_module.LauncherError("rmcp::transport::worker: worker quit with fatal: boom"),
            iteration=1,
        )
        self.assertEqual(classified.severity, "error")
        self.assertEqual(classified.cause, "mcp_transport")
        self.assertEqual(classified.iteration, 1)

    def test_run_returns_step_events_and_summary(self) -> None:
        config = run_module.load_config(None)
        backend = FakeBackend(
            {
                config.mcp_servers.search,
                config.mcp_servers.reader,
                config.mcp_servers.vision,
                config.mcp_servers.repository,
            }
        )
        validation = run_module.ValidationReport(
            client="codex",
            configured_mcp_names=sorted(backend._names),
            required_mcp_names=sorted(backend._names),
            missing_mcp_names=[],
            lexical_memory_available=True,
            issues=[],
            warnings=[],
            deprecated_fields=["vector_memory_available"],
            deprecated_config_keys_detected=[],
            duration_ms=1,
        )

        with mock.patch.object(run_module, "select_backend", return_value=backend):
            with mock.patch.object(run_module, "validate_runtime", return_value=validation):
                with mock.patch.object(run_module, "configure_runtime", return_value=None):
                    with mock.patch.object(run_module, "memory_init_memory", return_value=None):
                        with mock.patch.object(run_module, "memory_search_iterations", return_value=[]):
                            with mock.patch.object(run_module, "memory_save_iteration", return_value=None):
                                with mock.patch.object(run_module, "save_final_report", return_value=REPO_ROOT / "research.md"):
                                    result = run_module.run("q", client="codex")

        self.assertEqual(result["status"], "success")
        self.assertIn("step_events", result)
        self.assertIn("run_summary", result)
        self.assertEqual(result["final_decision"], "completed")
        self.assertEqual(result["run_summary"]["successful_iteration_count"], 1)
        statuses = [(event["step_name"], event["status"]) for event in result["step_events"]]
        self.assertIn(("planner", "running"), statuses)
        self.assertIn(("planner", "succeeded"), statuses)
        self.assertIn(("researcher", "succeeded"), statuses)

    def test_build_memory_context_uses_lexical_results(self) -> None:
        with mock.patch.object(
            run_module,
            "memory_search_iterations",
            return_value=[
                {
                    "title": "Prior Report",
                    "query": "original question",
                    "summary_md": "A summary that should appear in the prompt context.",
                    "session_id": "session-a",
                    "iteration": 2,
                    "score": -1.25,
                }
            ],
        ):
            context = run_module.build_memory_context("latest question", current_session_id="session-b")

        self.assertIn("title=Prior Report", context)
        self.assertIn("Original query: original question", context)
        self.assertIn("A summary that should appear", context)

    def test_run_includes_prior_memory_in_researcher_prompt(self) -> None:
        config = run_module.load_config(None)
        backend = FakeBackend(
            {
                config.mcp_servers.search,
                config.mcp_servers.reader,
                config.mcp_servers.vision,
                config.mcp_servers.repository,
            }
        )
        validation = run_module.ValidationReport(
            client="codex",
            configured_mcp_names=sorted(backend._names),
            required_mcp_names=sorted(backend._names),
            missing_mcp_names=[],
            lexical_memory_available=True,
            issues=[],
            warnings=[],
            deprecated_fields=["vector_memory_available"],
            deprecated_config_keys_detected=[],
            duration_ms=1,
        )

        with mock.patch.object(run_module, "select_backend", return_value=backend):
            with mock.patch.object(run_module, "validate_runtime", return_value=validation):
                with mock.patch.object(run_module, "configure_runtime", return_value=None):
                    with mock.patch.object(run_module, "memory_init_memory", return_value=None):
                        with mock.patch.object(
                            run_module,
                            "memory_search_iterations",
                            return_value=[
                                {
                                    "title": "Prior Report",
                                    "query": "original question",
                                    "summary_md": "Prior memory summary",
                                    "session_id": "session-a",
                                    "iteration": 2,
                                    "score": -1.0,
                                }
                            ],
                        ):
                            with mock.patch.object(run_module, "memory_save_iteration", return_value=None):
                                with mock.patch.object(run_module, "save_final_report", return_value=REPO_ROOT / "research.md"):
                                    result = run_module.run("q", client="codex")

        self.assertEqual(result["status"], "success")
        researcher_prompt = backend.prompt_text_by_step["researcher"]
        self.assertIn("Relevant prior memory:", researcher_prompt)
        self.assertIn("Prior memory summary", researcher_prompt)


if __name__ == "__main__":
    unittest.main()
