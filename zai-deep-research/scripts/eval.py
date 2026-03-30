from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parent
DEFAULT_WORKSPACE = REPO_ROOT / ".zai-deep-research-evals"
EVALS_PATH = SKILL_ROOT / "evals" / "evals.json"
DEFAULT_CLIENT = "codex"

DATE_PATTERNS = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December) "
        r"\d{1,2}, \d{4}\b"
    ),
)
LINK_PATTERN = re.compile(r"\[[^\]]+\]\((https?://[^)]+)\)|https?://\S+")


class EvalError(RuntimeError):
    """Raised when the local eval harness cannot continue."""


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9가-힣\s_-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value)
    return value[:80] or "eval"


def load_evals() -> dict[str, Any]:
    if not EVALS_PATH.exists():
        raise EvalError(f"missing eval definition file: {EVALS_PATH}")
    return json.loads(EVALS_PATH.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def next_iteration_dir(workspace: Path) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    existing_numbers: list[int] = []
    for path in workspace.iterdir():
        if not path.is_dir():
            continue
        match = re.fullmatch(r"iteration-(\d+)", path.name)
        if match:
            existing_numbers.append(int(match.group(1)))
    return workspace / f"iteration-{(max(existing_numbers) + 1) if existing_numbers else 1}"


def snapshot_skill(destination: Path) -> None:
    if destination.exists():
        raise EvalError(f"snapshot destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        SKILL_ROOT,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "config.json"),
    )


def find_report_path(outputs_dir: Path, payload: dict[str, Any]) -> Path | None:
    report_path = payload.get("report_path")
    if isinstance(report_path, str) and report_path.strip():
        candidate = Path(report_path).expanduser()
        if candidate.exists():
            return candidate.resolve()

    markdown_files = sorted(outputs_dir.glob("*.md"))
    return markdown_files[0].resolve() if markdown_files else None


def run_skill(
    *,
    skill_path: Path,
    prompt: str,
    client: str,
    outputs_dir: Path,
    working_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(skill_path / "scripts" / "run.py"),
        prompt,
        "--client",
        client,
        "--json",
        "--output-dir",
        str(outputs_dir),
    ]
    start_time = time.monotonic()
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        cwd=str(working_dir),
        check=False,
    )
    duration_ms = int((time.monotonic() - start_time) * 1000)

    payload: dict[str, Any]
    stdout = result.stdout.strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {
            "status": "error",
            "client": client,
            "issues": ["launcher did not emit valid JSON"],
            "raw_stdout": stdout,
        }

    if result.returncode != 0 and payload.get("status") == "success":
        payload["status"] = "error"
        payload.setdefault("issues", []).append(
            f"launcher exited with unexpected code {result.returncode}"
        )

    token_usage = payload.get("token_usage")
    total_tokens = None
    if isinstance(token_usage, dict):
        candidate = token_usage.get("total_tokens")
        if isinstance(candidate, int):
            total_tokens = candidate

    write_json(
        outputs_dir.parent / "result.json",
        {
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": result.stderr.strip(),
            "payload": payload,
        },
    )
    timing_payload = {
        "duration_ms": duration_ms,
        "total_tokens": total_tokens,
    }
    write_json(outputs_dir.parent / "timing.json", timing_payload)
    return payload, timing_payload


def extract_section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*$\n?(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def count_absolute_dates(text: str) -> int:
    matches: set[str] = set()
    for pattern in DATE_PATTERNS:
        matches.update(pattern.findall(text))
    return len(matches)


def count_links(text: str) -> int:
    return len(LINK_PATTERN.findall(text))


def run_check(check: dict[str, Any], payload: dict[str, Any], report_text: str) -> tuple[bool, str]:
    check_type = check["type"]
    assertion = check["assertion"]

    if check_type == "status_equals":
        expected = check["value"]
        actual = payload.get("status")
        return actual == expected, f"expected status={expected}, actual={actual}"

    if check_type == "markdown_h1":
        first_non_empty = next((line.strip() for line in report_text.splitlines() if line.strip()), "")
        passed = first_non_empty.startswith("# ")
        return passed, f"first non-empty line: {first_non_empty or '(empty)'}"

    if check_type == "has_section":
        section = str(check["value"])
        marker = f"## {section}"
        passed = marker in report_text
        return passed, f"section marker {'found' if passed else 'missing'}: {marker}"

    if check_type == "contains_regex":
        pattern = re.compile(str(check["value"]), re.IGNORECASE | re.MULTILINE)
        match = pattern.search(report_text)
        return match is not None, f"pattern={pattern.pattern}"

    if check_type == "min_source_links":
        section_name = str(check.get("section", "Sources"))
        section_text = extract_section(report_text, section_name) or report_text
        found = count_links(section_text)
        minimum = int(check["value"])
        return found >= minimum, f"found {found} links in {section_name}"

    if check_type == "min_absolute_dates":
        found = count_absolute_dates(report_text)
        minimum = int(check["value"])
        return found >= minimum, f"found {found} absolute dates"

    raise EvalError(f"unsupported check type: {check_type} ({assertion})")


def grade_eval_case(run_dir: Path, eval_case: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    outputs_dir = run_dir / "outputs"
    report_path = find_report_path(outputs_dir, payload)
    report_text = report_path.read_text(encoding="utf-8") if report_path else ""
    results: list[dict[str, Any]] = []

    for check in eval_case.get("checks", []):
        passed, evidence = run_check(check, payload, report_text)
        results.append(
            {
                "text": check["assertion"],
                "passed": passed,
                "evidence": evidence,
            }
        )

    passed_count = sum(1 for item in results if item["passed"])
    failed_count = len(results) - passed_count
    grading = {
        "assertion_results": results,
        "summary": {
            "passed": passed_count,
            "failed": failed_count,
            "total": len(results),
            "pass_rate": (passed_count / len(results)) if results else 0.0,
        },
    }
    write_json(run_dir / "grading.json", grading)
    return grading


def stats_for(values: list[float | None]) -> dict[str, float | None]:
    numeric = [value for value in values if value is not None]
    if not numeric:
        return {"mean": None, "stddev": None}
    if len(numeric) == 1:
        return {"mean": numeric[0], "stddev": 0.0}
    return {
        "mean": statistics.mean(numeric),
        "stddev": statistics.pstdev(numeric),
    }


def benchmark_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_label: dict[str, list[dict[str, Any]]] = {"with_skill": [], "old_skill": []}
    for record in records:
        by_label[record["label"]].append(record)

    payload: dict[str, Any] = {"run_summary": {}}
    for label, label_records in by_label.items():
        payload["run_summary"][label] = {
            "pass_rate": stats_for([item["pass_rate"] for item in label_records]),
            "time_seconds": stats_for([item["duration_ms"] / 1000.0 for item in label_records]),
            "tokens": stats_for([item["total_tokens"] for item in label_records]),
        }

    with_skill = payload["run_summary"]["with_skill"]
    old_skill = payload["run_summary"]["old_skill"]
    payload["run_summary"]["delta"] = {
        "pass_rate": None
        if with_skill["pass_rate"]["mean"] is None or old_skill["pass_rate"]["mean"] is None
        else with_skill["pass_rate"]["mean"] - old_skill["pass_rate"]["mean"],
        "time_seconds": None
        if with_skill["time_seconds"]["mean"] is None or old_skill["time_seconds"]["mean"] is None
        else with_skill["time_seconds"]["mean"] - old_skill["time_seconds"]["mean"],
        "tokens": None
        if with_skill["tokens"]["mean"] is None or old_skill["tokens"]["mean"] is None
        else with_skill["tokens"]["mean"] - old_skill["tokens"]["mean"],
    }
    return payload


def run_evals(*, client: str, baseline_skill: Path, workspace: Path) -> Path:
    if not baseline_skill.exists():
        raise EvalError(f"baseline skill path does not exist: {baseline_skill}")
    if not (baseline_skill / "SKILL.md").exists():
        raise EvalError(f"baseline path does not look like a skill: {baseline_skill}")

    eval_definition = load_evals()
    iteration_dir = next_iteration_dir(workspace)
    records: list[dict[str, Any]] = []
    feedback_payload: dict[str, str] = {}

    for eval_case in eval_definition.get("evals", []):
        eval_id = str(eval_case["id"])
        eval_slug = slugify(eval_id)
        eval_root = iteration_dir / eval_slug

        for label, skill_path in (("with_skill", SKILL_ROOT), ("old_skill", baseline_skill)):
            run_root = eval_root / label
            outputs_dir = run_root / "outputs"
            payload, timing = run_skill(
                skill_path=skill_path,
                prompt=str(eval_case["prompt"]),
                client=client,
                outputs_dir=outputs_dir,
                working_dir=REPO_ROOT,
            )
            grading = grade_eval_case(run_root, eval_case, payload)
            records.append(
                {
                    "label": label,
                    "eval_id": eval_id,
                    "pass_rate": grading["summary"]["pass_rate"],
                    "duration_ms": timing["duration_ms"],
                    "total_tokens": timing["total_tokens"],
                }
            )

        feedback_payload[eval_slug] = ""

    write_json(iteration_dir / "benchmark.json", benchmark_summary(records))
    write_json(iteration_dir / "feedback.json", feedback_payload)
    return iteration_dir


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local evals for zai-deep-research",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/eval.py snapshot --dest ./.zai-deep-research-evals/skill-snapshot\n"
            "  python scripts/eval.py run --client codex --baseline-skill ./.zai-deep-research-evals/skill-snapshot\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Create an old_skill snapshot")
    snapshot_parser.add_argument("--dest", required=True, help="Snapshot destination path")

    run_parser = subparsers.add_parser("run", help="Run, grade, and benchmark all eval cases")
    run_parser.add_argument(
        "--client",
        default=DEFAULT_CLIENT,
        help=f"Primary backend used for eval execution (default: {DEFAULT_CLIENT})",
    )
    run_parser.add_argument(
        "--baseline-skill",
        required=True,
        help="Path to the old_skill snapshot used as the comparison baseline",
    )
    run_parser.add_argument(
        "--workspace",
        default=str(DEFAULT_WORKSPACE),
        help=f"Workspace root for eval artifacts (default: {DEFAULT_WORKSPACE})",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.command == "snapshot":
        destination = Path(args.dest).expanduser().resolve()
        snapshot_skill(destination)
        print(f"Snapshot created at {destination}")
        return 0

    if args.command == "run":
        iteration_dir = run_evals(
            client=args.client,
            baseline_skill=Path(args.baseline_skill).expanduser().resolve(),
            workspace=Path(args.workspace).expanduser().resolve(),
        )
        print(f"Eval artifacts written to {iteration_dir}")
        return 0

    raise EvalError(f"unsupported command: {args.command}")


def cli(argv: list[str]) -> int:
    try:
        return main(argv)
    except EvalError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
