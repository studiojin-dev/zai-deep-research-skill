from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "zai-deep-research"
SCRIPTS_DIR = SKILL_ROOT / "scripts"
INSTALL_SCRIPT = SCRIPTS_DIR / "install.sh"


def load_eval_module():
    spec = importlib.util.spec_from_file_location("zai_deep_research_eval", SCRIPTS_DIR / "eval.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load eval.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["zai_deep_research_eval"] = module
    spec.loader.exec_module(module)
    return module


eval_module = load_eval_module()


def write_fake_skill(skill_path: Path) -> None:
    (skill_path / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_path / "SKILL.md").write_text("# fake\n", encoding="utf-8")
    (skill_path / "scripts" / "run.py").write_text(
        textwrap.dedent(
            '''
            import json
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            output_dir = Path(args[args.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            report = """# Fake Report
            ## Research Brief
            ## Executive Summary
            ## Key Findings
            ## Comparisons
            ## Counterexamples and Caveats
            ## Similar Cases
            ## Open Questions
            ## Sources
            - [Example](https://example.com/a)
            - [Example Two](https://example.com/b)
            - https://example.com/c
            Updated: 2026-03-30
            Published: March 29, 2026
            """
            report_path = output_dir / "report.md"
            report_path.write_text(report, encoding="utf-8")
            payload = {
                "status": "success",
                "client": args[args.index("--client") + 1],
                "session_id": "fake-session",
                "report_path": str(report_path),
                "iteration_count": 1,
                "clarification_questions": [],
                "duration_ms": 1,
                "token_usage": None,
            }
            print(json.dumps(payload))
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )


class InstallAndEvalTests(unittest.TestCase):
    def test_install_dry_run_prints_plan(self) -> None:
        result = subprocess.run(
            [
                "sh",
                str(INSTALL_SCRIPT),
                "--source-dir",
                "./zai-deep-research",
                "--layout",
                "shared",
                "--scope",
                "project",
                "--dry-run",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Action: install", result.stdout)
        self.assertIn("Destination path:", result.stdout)

    def test_install_dry_run_codex_layout_uses_native_path(self) -> None:
        result = subprocess.run(
            [
                "sh",
                str(INSTALL_SCRIPT),
                "--source-dir",
                "./zai-deep-research",
                "--layout",
                "codex",
                "--dry-run",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(Path.home() / ".codex" / "skills" / "zai-deep-research"), result.stdout)

    def test_install_missing_source_dir_reports_clean_error(self) -> None:
        result = subprocess.run(
            ["sh", str(INSTALL_SCRIPT), "--source-dir", "./missing"],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("source directory does not exist", result.stderr)

    def test_eval_run_creates_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp_root = Path(tempdir)
            current_skill = temp_root / "current-skill"
            baseline_skill = temp_root / "baseline-skill"
            workspace = temp_root / "workspace"
            evals_path = current_skill / "evals" / "evals.json"

            write_fake_skill(current_skill)
            write_fake_skill(baseline_skill)
            evals_path.parent.mkdir(parents=True, exist_ok=True)
            evals_path.write_text(
                textwrap.dedent(
                    """
                    {
                      "skill_name": "zai-deep-research",
                      "evals": [
                        {
                          "id": "fake-web-eval",
                          "prompt": "compare the latest public pages",
                          "expected_output": "fake",
                          "assertions": ["The report has sections."],
                          "checks": [
                            {"assertion": "The run completed successfully.", "type": "status_equals", "value": "success"},
                            {"assertion": "The report starts with an H1 title.", "type": "markdown_h1"},
                            {"assertion": "The report includes a Sources section.", "type": "has_section", "value": "Sources"},
                            {"assertion": "The report contains at least three direct source links.", "type": "min_source_links", "value": 3},
                            {"assertion": "The report includes at least two absolute dates.", "type": "min_absolute_dates", "value": 2}
                          ]
                        }
                      ]
                    }
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(eval_module, "SKILL_ROOT", current_skill), mock.patch.object(
                eval_module, "REPO_ROOT", temp_root
            ), mock.patch.object(eval_module, "EVALS_PATH", evals_path):
                iteration_dir = eval_module.run_evals(
                    client="codex",
                    baseline_skill=baseline_skill,
                    workspace=workspace,
                )

            self.assertTrue((iteration_dir / "fake-web-eval" / "with_skill" / "timing.json").exists())
            self.assertTrue((iteration_dir / "fake-web-eval" / "with_skill" / "grading.json").exists())
            self.assertTrue((iteration_dir / "fake-web-eval" / "old_skill" / "timing.json").exists())
            self.assertTrue((iteration_dir / "benchmark.json").exists())
            self.assertTrue((iteration_dir / "feedback.json").exists())


if __name__ == "__main__":
    unittest.main()
