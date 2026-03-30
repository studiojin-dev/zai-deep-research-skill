from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config import DEFAULT_SKILL_NAME, SkillConfig, load_config
from memory import configure as configure_memory
from memory import init_memory as memory_init_memory
from memory import save_artifact as memory_save_artifact
from memory import save_iteration as memory_save_iteration
from memory import save_report as memory_save_report
from vector_store import add_texts as vector_add_texts
from vector_store import configure as configure_vector_store
from vector_store import is_available as vector_is_available
from vector_store import similarity_search as vector_similarity_search

DEFAULT_MAX_ITERATIONS = 7
AGENT_FILES = ("planner.md", "researcher.md", "summarizer.md", "synthesizer.md")


def safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON output: {exc}\nRaw output:\n{text}") from exc


def unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def build_session_id(query: str) -> str:
    base = slugify(query)[:40] or "zai_deep_research"
    return f"{base}_{os.getpid()}"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9가-힣\s_-]", "", value)
    value = re.sub(r"[\s_-]+", "_", value)
    return value[:80] or "zai_deep_research_report"


def run_codex(prompt: str) -> str:
    result = subprocess.run(
        ["codex", "exec", "--skip-git-repo-check", "-"],
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
        cwd=str(SKILL_ROOT),
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        details = stderr or stdout or "unknown codex exec error"
        raise RuntimeError(f"codex exec failed: {details}")

    return result.stdout.strip()


def list_codex_mcp_names() -> set[str]:
    result = subprocess.run(
        ["codex", "mcp", "list"],
        text=True,
        capture_output=True,
        check=False,
        cwd=str(SKILL_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(
            "codex mcp list failed: "
            + (result.stderr.strip() or result.stdout.strip() or "unknown error")
        )

    names: set[str] = set()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Name") or set(stripped) == {"-"}:
            continue
        parts = stripped.split()
        if parts:
            names.add(parts[0])
    return names


def extract_json_block(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    return safe_json_loads(text)


def resolve_output_dir(output_dir: str | None) -> Path:
    if output_dir:
        path = Path(os.path.expanduser(output_dir)).resolve()
    else:
        path = (Path.cwd().resolve() / "research").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_runtime(config: SkillConfig) -> None:
    config.storage.data_dir.mkdir(parents=True, exist_ok=True)
    configure_memory(config.storage.memory_db_path)
    configure_vector_store(
        index_path=config.storage.vector_index_path,
        metadata_path=config.storage.vector_metadata_path,
    )


def render_agent_template(config: SkillConfig, agent_filename: str) -> str:
    template_path = SKILL_ROOT / "agents" / agent_filename
    if not template_path.exists():
        raise FileNotFoundError(f"Missing agent template: {template_path}")

    rendered = template_path.read_text(encoding="utf-8")
    replacements = {
        "__SKILL_NAME__": config.skill_name,
        "__MCP_SEARCH_NAME__": config.mcp_servers.search,
        "__MCP_READER_NAME__": config.mcp_servers.reader,
        "__MCP_VISION_NAME__": config.mcp_servers.vision,
        "__MCP_REPOSITORY_NAME__": config.mcp_servers.repository,
    }
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


def build_memory_context(query: str, limit: int = 3) -> str:
    if not vector_is_available():
        return "(vector memory unavailable)"

    similar = vector_similarity_search(query, k=limit)
    if not similar:
        return "(no similar prior memory found)"

    lines: list[str] = []
    for item in similar:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        session_id = item.get("session_id", "unknown")
        iteration = item.get("iteration", "unknown")
        distance = item.get("distance", "n/a")
        lines.append(
            f"- session={session_id}, iteration={iteration}, distance={distance}\n{text}"
        )

    return "\n\n".join(lines) if lines else "(no similar prior memory found)"


def maybe_index_iteration_summary(
    session_id: str,
    iteration: int,
    query: str,
    summary_md: str,
) -> None:
    if not vector_is_available():
        return

    vector_add_texts(
        [summary_md],
        [
            {
                "session_id": session_id,
                "iteration": iteration,
                "query": query,
                "artifact_type": "iteration_summary",
            }
        ],
    )


def build_planner_prompt(config: SkillConfig, user_query: str) -> str:
    template = render_agent_template(config, "planner.md")
    return f"{template}\n\nUser request:\n{user_query}".strip()


def build_researcher_prompt(
    config: SkillConfig,
    quality_goal: str,
    iteration: int,
    query: str,
    prior_summaries: list[str],
    recommended_mcps: list[str],
    memory_context: str,
) -> str:
    template = render_agent_template(config, "researcher.md")
    prior_context = "\n\n".join(
        f"Iteration {idx + 1} summary:\n{summary}"
        for idx, summary in enumerate(prior_summaries)
    )
    recommended_text = ", ".join(recommended_mcps) if recommended_mcps else "(not specified)"
    return (
        f"{template}\n\n"
        f"Quality goal: {quality_goal}\n"
        f"Current iteration: {iteration}\n"
        f"Current query: {query}\n"
        f"Recommended MCPs from planning: {recommended_text}\n\n"
        f"Prior iteration context:\n{prior_context or '(none)'}\n\n"
        f"Relevant prior memory:\n{memory_context}"
    ).strip()


def build_summarizer_prompt(
    config: SkillConfig,
    iteration: int,
    query: str,
    researcher_payload: dict[str, Any],
) -> str:
    template = render_agent_template(config, "summarizer.md")
    serialized = json.dumps(researcher_payload, ensure_ascii=False, indent=2)
    return (
        f"{template}\n\n"
        f"Current iteration: {iteration}\n"
        f"Current query: {query}\n\n"
        f"Researcher output:\n{serialized}"
    ).strip()


def build_final_synthesis_prompt(
    config: SkillConfig,
    clarified_query: str,
    quality_goal: str,
    iteration_payloads: list[dict[str, Any]],
) -> str:
    template = render_agent_template(config, "synthesizer.md")
    serialized = json.dumps(iteration_payloads, ensure_ascii=False, indent=2)
    return (
        f"{template}\n\n"
        f"Original clarified query:\n{clarified_query}\n\n"
        f"Quality goal:\n{quality_goal}\n\n"
        f"Iteration results:\n{serialized}"
    ).strip()


def save_final_report(session_id: str, output_dir: Path, report_md: str) -> Path:
    lines = [line.strip() for line in report_md.splitlines() if line.strip()]
    title = lines[0].lstrip("# ").strip() if lines else "ZAI Deep Research Report"
    filename = f"{slugify(title)}_{session_id}.md"
    path = output_dir / filename
    path.write_text(report_md, encoding="utf-8")

    memory_save_report(
        session_id=session_id,
        title=title,
        report_path=str(path),
        report_md=report_md,
    )
    memory_save_artifact(
        session_id=session_id,
        artifact_type="final_report",
        artifact_path=str(path),
        metadata={"title": title, "output_dir": str(output_dir)},
    )
    return path


def validate_runtime(config: SkillConfig) -> list[str]:
    issues: list[str] = []
    if config.skill_name != DEFAULT_SKILL_NAME:
        issues.append(
            f"skill_name must be '{DEFAULT_SKILL_NAME}', got '{config.skill_name}'"
        )

    for filename in AGENT_FILES:
        path = SKILL_ROOT / "agents" / filename
        if not path.exists():
            issues.append(f"missing agent template: {path}")
            continue

        rendered = render_agent_template(config, filename)
        for unresolved in (
            "__SKILL_NAME__",
            "__MCP_SEARCH_NAME__",
            "__MCP_READER_NAME__",
            "__MCP_VISION_NAME__",
            "__MCP_REPOSITORY_NAME__",
        ):
            if unresolved in rendered:
                issues.append(f"unresolved placeholder {unresolved} in {path}")

        for server_name in (
            config.mcp_servers.search,
            config.mcp_servers.reader,
            config.mcp_servers.vision,
            config.mcp_servers.repository,
        ):
            if server_name not in rendered:
                issues.append(f"{path} does not mention MCP server '{server_name}'")

    configured_mcp_names = list_codex_mcp_names()
    for server_name in (
        config.mcp_servers.search,
        config.mcp_servers.reader,
        config.mcp_servers.vision,
        config.mcp_servers.repository,
    ):
        if server_name not in configured_mcp_names:
            issues.append(f"Codex MCP server '{server_name}' is not configured locally")

    return issues


def run(
    query: str,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    output_dir: str | None = None,
    config_path: str | None = None,
) -> int:
    config = load_config(config_path)
    configure_runtime(config)
    memory_init_memory()

    validation_issues = validate_runtime(config)
    if validation_issues:
        raise RuntimeError("invalid skill configuration:\n- " + "\n- ".join(validation_issues))

    session_id = build_session_id(query)
    resolved_output_dir = resolve_output_dir(output_dir)

    planner_raw = run_codex(build_planner_prompt(config, query))
    plan = extract_json_block(planner_raw)

    if plan.get("need_user_input"):
        print(f"Clarification required before {config.skill_name} research:\n")
        for idx, question in enumerate(plan.get("questions", []), start=1):
            print(f"{idx}. {question}")
        return 2

    clarified_query = plan["clarified_query"]
    quality_goal = plan["quality_goal"]
    recommended_mcps = unique_preserve_order(plan.get("recommended_mcps", []))
    pending_queries = unique_preserve_order(plan.get("sub_questions") or [clarified_query])
    iteration_payloads: list[dict[str, Any]] = []
    prior_summaries: list[str] = []
    seen_queries: set[str] = set()
    iteration = 0

    while pending_queries and iteration < max_iterations:
        current_query = pending_queries.pop(0).strip()
        if not current_query or current_query in seen_queries:
            continue
        seen_queries.add(current_query)
        iteration += 1

        memory_context = build_memory_context(current_query)
        researcher_raw = run_codex(
            build_researcher_prompt(
                config=config,
                quality_goal=quality_goal,
                iteration=iteration,
                query=current_query,
                prior_summaries=prior_summaries,
                recommended_mcps=recommended_mcps,
                memory_context=memory_context,
            )
        )
        researcher_payload = extract_json_block(researcher_raw)

        summarizer_raw = run_codex(
            build_summarizer_prompt(
                config=config,
                iteration=iteration,
                query=current_query,
                researcher_payload=researcher_payload,
            )
        )
        summary_payload = extract_json_block(summarizer_raw)

        summary_md = summary_payload["iteration_summary_md"]
        findings = researcher_payload.get("findings", [])
        next_queries = summary_payload.get("next_queries", [])

        memory_save_iteration(
            session_id=session_id,
            iteration=iteration,
            query=current_query,
            summary_md=summary_md,
            findings=findings,
        )
        maybe_index_iteration_summary(
            session_id=session_id,
            iteration=iteration,
            query=current_query,
            summary_md=summary_md,
        )

        prior_summaries.append(summary_md)
        iteration_payloads.append(
            {
                "iteration": iteration,
                "query": current_query,
                "researcher": researcher_payload,
                "summary": summary_payload,
            }
        )

        for next_query in unique_preserve_order(next_queries):
            if next_query not in seen_queries and next_query not in pending_queries:
                pending_queries.append(next_query)

    final_report = run_codex(
        build_final_synthesis_prompt(
            config=config,
            clarified_query=clarified_query,
            quality_goal=quality_goal,
            iteration_payloads=iteration_payloads,
        )
    )
    report_path = save_final_report(session_id, resolved_output_dir, final_report)

    print(f"Saved: {report_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the zai-deep-research skill")
    parser.add_argument("query", nargs="*", help="Research query")
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help=f"Maximum research refinement attempts (default: {DEFAULT_MAX_ITERATIONS})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save the final markdown report. Defaults to ./research under the current working directory.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Optional JSON config path. Defaults to ./config.json if present.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate config, agent templates, and prompt wiring without running research.",
    )
    args = parser.parse_args(argv)
    if not args.validate and not args.query:
        parser.error("query is required unless --validate is used")
    return args


if __name__ == "__main__":
    arguments = parse_args(sys.argv[1:])
    if arguments.validate:
        runtime_config = load_config(arguments.config)
        configure_runtime(runtime_config)
        issues = validate_runtime(runtime_config)
        if issues:
            print("Validation failed:")
            for issue in issues:
                print(f"- {issue}")
            sys.exit(1)
        print(f"Validation passed for {runtime_config.skill_name}")
        print(f"Memory DB: {runtime_config.storage.memory_db_path}")
        print(f"Vector index: {runtime_config.storage.vector_index_path}")
        print(f"Vector metadata: {runtime_config.storage.vector_metadata_path}")
        print(
            "MCP servers: "
            f"{runtime_config.mcp_servers.search}, "
            f"{runtime_config.mcp_servers.reader}, "
            f"{runtime_config.mcp_servers.vision}, "
            f"{runtime_config.mcp_servers.repository}"
        )
        sys.exit(0)

    sys.exit(
        run(
            " ".join(arguments.query),
            max_iterations=arguments.max_iterations,
            output_dir=arguments.output_dir,
            config_path=arguments.config,
        )
    )
