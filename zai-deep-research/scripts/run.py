from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config import DEFAULT_SKILL_NAME, RuntimeConfig, SkillConfig, load_config
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
SUPPORTED_CLIENTS = ("auto", "codex", "claude", "opencode", "gemini")
BACKEND_PROBE_ORDER = ("codex", "claude", "opencode", "gemini")
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
RMCP_FATAL_RE = re.compile(r"rmcp::transport::worker: worker quit with fatal: .+")
COMMAND_TIMEOUT_SECONDS = 300
CODEX_MCP_PROBE_TIMEOUT_SECONDS = 30
CODEX_REASONING_EFFORT = "medium"
REMOTE_MCP_TRANSPORTS = {"streamable_http", "http", "sse"}


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class CodexExecOutput:
    assistant_text: str
    usage: dict[str, Any] | None
    rmcp_errors: list[str]


@dataclass(frozen=True)
class ClientBackend:
    name: str
    executable: str
    display_name: str

    def is_available(self) -> bool:
        return shutil.which(self.executable) is not None

    def run_prompt(
        self,
        prompt: str,
        cwd: Path,
        *,
        disabled_mcp_names: list[str] | None = None,
    ) -> str:
        raise NotImplementedError

    def list_mcp_names(self, cwd: Path) -> set[str]:
        raise NotImplementedError


class LauncherError(RuntimeError):
    """Expected launcher/runtime failures that should surface cleanly to users."""


@dataclass(frozen=True)
class ValidationReport:
    client: str
    configured_mcp_names: list[str]
    required_mcp_names: list[str]
    missing_mcp_names: list[str]
    vector_memory_available: bool
    issues: list[str]
    duration_ms: int

    @property
    def is_ok(self) -> bool:
        return not self.issues

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.is_ok else "error",
            "client": self.client,
            "configured_mcp_names": self.configured_mcp_names,
            "required_mcp_names": self.required_mcp_names,
            "missing_mcp_names": self.missing_mcp_names,
            "vector_memory_available": self.vector_memory_available,
            "issues": self.issues,
            "duration_ms": self.duration_ms,
        }


def coerce_text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


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


def extract_rmcp_fatal_lines(text: str) -> list[str]:
    if not text:
        return []
    return unique_preserve_order(
        [match.group(0).strip() for match in RMCP_FATAL_RE.finditer(strip_ansi(text))]
    )


def parse_codex_exec_json(raw_output: str) -> tuple[str, dict[str, Any] | None]:
    assistant_messages: list[str] = []
    usage: dict[str, Any] | None = None

    for line in strip_ansi(raw_output).splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                text = str(item.get("text", "")).strip()
                if text:
                    assistant_messages.append(text)
        elif event.get("type") == "turn.completed":
            event_usage = event.get("usage")
            if isinstance(event_usage, dict):
                usage = event_usage

    if not assistant_messages:
        raise LauncherError("codex returned no assistant message")
    return assistant_messages[-1], usage


def parse_mcp_transport(raw_output: str) -> str | None:
    for line in strip_ansi(raw_output).splitlines():
        stripped = line.strip()
        if stripped.startswith("transport:"):
            return stripped.split(":", 1)[1].strip()
    return None


def format_unavailable_mcp_note(disabled_mcp_names: list[str] | None) -> str:
    if not disabled_mcp_names:
        return ""
    joined = ", ".join(disabled_mcp_names)
    return (
        "\n\n"
        f"Temporarily unavailable MCP servers this run: {joined}\n"
        "Do not attempt to use those MCP servers. Continue with the remaining configured MCPs."
    )


def codex_mcp_enabled_override(name: str, enabled: bool) -> str:
    value = "true" if enabled else "false"
    return f"mcp_servers.{name}.enabled={value}"


def build_session_id(query: str) -> str:
    base = slugify(query)[:40] or "zai_deep_research"
    return f"{base}_{os.getpid()}"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9가-힣\s_-]", "", value)
    value = re.sub(r"[\s_-]+", "_", value)
    return value[:80] or "zai_deep_research_report"


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def run_command(
    command: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    env_updates: dict[str, str] | None = None,
    timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
) -> CommandResult:
    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    env.setdefault("TERM", "dumb")
    env.setdefault(
        "ZAI_DEEP_RESEARCH_COMMAND_TIMEOUT_SECONDS",
        str(COMMAND_TIMEOUT_SECONDS),
    )
    if env_updates:
        env.update(env_updates)
    timeout_seconds = int(env.get("ZAI_DEEP_RESEARCH_COMMAND_TIMEOUT_SECONDS", timeout_seconds))

    try:
        result = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd),
            env=env,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = strip_ansi(coerce_text_output(exc.stdout)).strip()
        stderr = strip_ansi(coerce_text_output(exc.stderr)).strip()
        details = stderr or stdout
        message = f"command timed out after {timeout_seconds} seconds: {format_command(command)}"
        if details:
            message = f"{message}\n{details}"
        raise LauncherError(message) from exc
    except OSError as exc:
        raise LauncherError(
            f"command could not be executed: {format_command(command)} ({exc})"
        ) from exc
    return CommandResult(
        stdout=strip_ansi(result.stdout).strip(),
        stderr=strip_ansi(result.stderr).strip(),
        returncode=result.returncode,
    )


def normalize_assistant_text(raw_output: str) -> str:
    text = strip_ansi(raw_output).strip()
    if not text:
        return text

    candidate = text
    if candidate.startswith("```"):
        match = re.search(r"```(?:json|markdown|md|text)?\s*(.*?)```", candidate, re.DOTALL)
        if match:
            candidate = match.group(1).strip()

    if candidate.startswith("{") or candidate.startswith("["):
        try:
            payload = safe_json_loads(candidate)
        except ValueError:
            return text
        extracted = extract_text_from_payload(payload)
        return extracted if extracted is not None else text

    return text


def load_structured_payload(raw_output: str, *, backend_name: str) -> Any:
    text = strip_ansi(raw_output).strip()
    if not text:
        raise LauncherError(f"{backend_name} returned empty structured output")

    candidate = text
    if candidate.startswith("```"):
        match = re.search(r"```(?:json|markdown|md|text)?\s*(.*?)```", candidate, re.DOTALL)
        if match:
            candidate = match.group(1).strip()

    if candidate.startswith("["):
        try:
            return safe_json_loads(candidate)
        except ValueError as exc:
            raise LauncherError(f"{backend_name} returned malformed structured output: {exc}") from exc

    if candidate.startswith("{") and "\n" not in candidate:
        try:
            return safe_json_loads(candidate)
        except ValueError as exc:
            raise LauncherError(f"{backend_name} returned malformed structured output: {exc}") from exc

    payloads: list[Any] = []
    for line_no, line in enumerate(candidate.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payloads.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise LauncherError(
                f"{backend_name} returned malformed structured output on line {line_no}: {exc}"
            ) from exc

    if not payloads:
        raise LauncherError(f"{backend_name} returned empty structured output")
    return payloads


def extract_structured_assistant_text(raw_output: str, *, backend_name: str) -> str:
    payload = load_structured_payload(raw_output, backend_name=backend_name)
    extracted = extract_text_from_payload(payload)
    if not extracted:
        raise LauncherError(f"{backend_name} returned structured output without assistant text")
    return extracted


def extract_text_from_payload(payload: Any) -> str | None:
    if isinstance(payload, str):
        return payload.strip()

    if isinstance(payload, dict):
        payload_type = str(payload.get("type", "")).lower()
        if payload_type in {"text", "output_text", "assistant_text"}:
            value = payload.get("text") or payload.get("value")
            extracted = extract_text_from_payload(value)
            if extracted:
                return extracted

        for key in (
            "response",
            "text",
            "content",
            "message",
            "result",
            "output",
            "delta",
            "value",
            "events",
            "parts",
        ):
            value = payload.get(key)
            extracted = extract_text_from_payload(value)
            if extracted:
                return extracted

        messages = payload.get("messages")
        if isinstance(messages, list):
            extracted = extract_text_from_payload(messages)
            if extracted:
                return extracted

    if isinstance(payload, list):
        for item in reversed(payload):
            extracted = extract_text_from_payload(item)
            if extracted:
                return extracted

    return None


def parse_generic_mcp_list(raw_output: str) -> set[str]:
    names: set[str] = set()
    for line in strip_ansi(raw_output).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(
            ("WARNING:", "Checking MCP server health", "Health check", "Name", "Configured MCP servers", "MCP servers")
        ):
            continue
        normalized = stripped.lstrip("+-*").lstrip("✓✗•").strip()
        if not normalized or set(normalized) == {"-"}:
            continue
        if re.match(r"(?i)^name\s{2,}", normalized):
            continue

        column_parts = re.split(r"\s{2,}", normalized, maxsplit=1)
        if column_parts and column_parts[0]:
            name = column_parts[0].strip()
        elif "://" not in normalized and ":" in normalized:
            name = normalized.split(":", 1)[0].strip()
        else:
            name = normalized.split()[0]

        if name.lower() in {"name", "server", "status"}:
            continue
        if name:
            names.add(name)
    return names


def extract_json_block(text: str) -> Any:
    normalized = normalize_assistant_text(text)
    if normalized.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)```", normalized, re.DOTALL)
        if match:
            normalized = match.group(1).strip()
    try:
        return safe_json_loads(normalized)
    except ValueError as exc:
        raise LauncherError(str(exc)) from exc


def resolve_output_dir(output_dir: str | None) -> Path:
    if output_dir:
        path = Path(os.path.expanduser(output_dir)).resolve()
    else:
        path = (Path.cwd().resolve() / "research").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def elapsed_ms(start_time: float) -> int:
    return int((time.monotonic() - start_time) * 1000)


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


def build_planner_prompt(
    config: SkillConfig,
    user_query: str,
    disabled_mcp_names: list[str] | None = None,
) -> str:
    template = render_agent_template(config, "planner.md")
    return f"{template}{format_unavailable_mcp_note(disabled_mcp_names)}\n\nUser request:\n{user_query}".strip()


def build_researcher_prompt(
    config: SkillConfig,
    quality_goal: str,
    iteration: int,
    query: str,
    prior_summaries: list[str],
    recommended_mcps: list[str],
    memory_context: str,
    disabled_mcp_names: list[str] | None = None,
) -> str:
    template = render_agent_template(config, "researcher.md")
    prior_context = "\n\n".join(
        f"Iteration {idx + 1} summary:\n{summary}"
        for idx, summary in enumerate(prior_summaries)
    )
    recommended_text = ", ".join(recommended_mcps) if recommended_mcps else "(not specified)"
    return (
        f"{template}{format_unavailable_mcp_note(disabled_mcp_names)}\n\n"
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


class CodexBackend(ClientBackend):
    def build_exec_command(self, disabled_mcp_names: list[str] | None = None) -> list[str]:
        command = [
            self.executable,
            "exec",
            "--skip-git-repo-check",
            "--json",
            "-c",
            f'reasoning_effort="{CODEX_REASONING_EFFORT}"',
        ]
        for name in disabled_mcp_names or []:
            command.extend(["-c", codex_mcp_enabled_override(name, False)])
        command.append("-")
        return command

    def run_exec_prompt(
        self,
        prompt: str,
        cwd: Path,
        *,
        disabled_mcp_names: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> CodexExecOutput:
        env_updates: dict[str, str] | None = None
        if timeout_seconds is not None:
            env_updates = {
                "ZAI_DEEP_RESEARCH_COMMAND_TIMEOUT_SECONDS": str(timeout_seconds)
            }

        try:
            result = run_command(
                self.build_exec_command(disabled_mcp_names),
                cwd=cwd,
                input_text=prompt,
                env_updates=env_updates,
            )
        except LauncherError as exc:
            rmcp_errors = extract_rmcp_fatal_lines(str(exc))
            if rmcp_errors:
                raise LauncherError(
                    "codex encountered MCP transport failures while starting this run:\n"
                    + "\n".join(rmcp_errors)
                ) from exc
            raise

        rmcp_errors = extract_rmcp_fatal_lines(f"{result.stderr}\n{result.stdout}")
        if result.returncode != 0:
            details = result.stderr or result.stdout or "unknown codex exec error"
            if rmcp_errors:
                details = (
                    "MCP transport failures:\n"
                    + "\n".join(rmcp_errors)
                    + "\n\n"
                    + details
                )
            raise LauncherError(f"{self.name} exec failed: {details}")
        assistant_text, usage = parse_codex_exec_json(result.stdout)
        return CodexExecOutput(
            assistant_text=normalize_assistant_text(assistant_text),
            usage=usage,
            rmcp_errors=rmcp_errors,
        )

    def run_prompt(
        self,
        prompt: str,
        cwd: Path,
        *,
        disabled_mcp_names: list[str] | None = None,
    ) -> str:
        return self.run_exec_prompt(
            prompt,
            cwd,
            disabled_mcp_names=disabled_mcp_names,
        ).assistant_text

    def list_mcp_names(self, cwd: Path) -> set[str]:
        result = run_command(
            [self.executable, "mcp", "list"],
            cwd=cwd,
        )
        if result.returncode != 0:
            details = result.stderr or result.stdout or "unknown mcp list error"
            raise LauncherError(f"{self.name} mcp list failed: {details}")
        return parse_generic_mcp_list(result.stdout)

    def get_mcp_transport(self, name: str, cwd: Path) -> str | None:
        result = run_command(
            [self.executable, "mcp", "get", name],
            cwd=cwd,
        )
        if result.returncode != 0:
            details = result.stderr or result.stdout or "unknown mcp get error"
            raise LauncherError(f"{self.name} mcp get {name} failed: {details}")
        return parse_mcp_transport(result.stdout)


class ClaudeBackend(ClientBackend):
    def run_prompt(
        self,
        prompt: str,
        cwd: Path,
        *,
        disabled_mcp_names: list[str] | None = None,
    ) -> str:
        result = run_command(
            [
                self.executable,
                "-p",
                prompt,
                "--permission-mode",
                "bypassPermissions",
                "--add-dir",
                str(cwd),
            ],
            cwd=cwd,
        )
        if result.returncode != 0:
            details = result.stderr or result.stdout or "unknown claude exec error"
            raise LauncherError(f"{self.name} print mode failed: {details}")
        return normalize_assistant_text(result.stdout)

    def list_mcp_names(self, cwd: Path) -> set[str]:
        result = run_command(
            [self.executable, "mcp", "list"],
            cwd=cwd,
        )
        if result.returncode != 0:
            details = result.stderr or result.stdout or "unknown mcp list error"
            raise LauncherError(f"{self.name} mcp list failed: {details}")
        return parse_generic_mcp_list(result.stdout)


class OpenCodeBackend(ClientBackend):
    def run_prompt(
        self,
        prompt: str,
        cwd: Path,
        *,
        disabled_mcp_names: list[str] | None = None,
    ) -> str:
        result = run_command(
            [self.executable, "run", "--format", "json", "--dir", str(cwd), prompt],
            cwd=cwd,
        )
        if result.returncode != 0:
            details = result.stderr or result.stdout or "unknown opencode run error"
            raise LauncherError(f"{self.name} run failed: {details}")
        return extract_structured_assistant_text(result.stdout, backend_name=self.name)

    def list_mcp_names(self, cwd: Path) -> set[str]:
        result = run_command(
            [self.executable, "mcp", "list"],
            cwd=cwd,
        )
        if result.returncode != 0:
            details = result.stderr or result.stdout or "unknown mcp list error"
            raise LauncherError(f"{self.name} mcp list failed: {details}")
        return parse_generic_mcp_list(result.stdout)


class GeminiBackend(ClientBackend):
    def run_prompt(
        self,
        prompt: str,
        cwd: Path,
        *,
        disabled_mcp_names: list[str] | None = None,
    ) -> str:
        result = run_command(
            [self.executable, "-p", prompt, "--output-format", "json"],
            cwd=cwd,
        )
        if result.returncode != 0:
            details = result.stderr or result.stdout or "unknown gemini headless error"
            raise LauncherError(f"{self.name} prompt failed: {details}")

        try:
            payload = safe_json_loads(result.stdout)
        except ValueError as exc:
            raise LauncherError(f"{self.name} returned malformed structured output: {exc}") from exc
        response = payload.get("response")
        if not isinstance(response, str) or not response.strip():
            details = payload.get("error") or payload
            raise LauncherError(f"{self.name} returned no response text: {details}")
        return normalize_assistant_text(response)

    def list_mcp_names(self, cwd: Path) -> set[str]:
        result = run_command(
            [self.executable, "mcp", "list"],
            cwd=cwd,
        )
        if result.returncode != 0:
            details = result.stderr or result.stdout or "unknown mcp list error"
            raise LauncherError(f"{self.name} mcp list failed: {details}")
        return parse_generic_mcp_list(result.stdout)


BACKENDS: dict[str, ClientBackend] = {
    "codex": CodexBackend("codex", "codex", "Codex CLI"),
    "claude": ClaudeBackend("claude", "claude", "Claude Code"),
    "opencode": OpenCodeBackend("opencode", "opencode", "OpenCode"),
    "gemini": GeminiBackend("gemini", "gemini", "Gemini CLI"),
}


def get_backend(client_name: str) -> ClientBackend:
    try:
        return BACKENDS[client_name]
    except KeyError as exc:
        raise LauncherError(
            f"unsupported client '{client_name}'; choose from {', '.join(SUPPORTED_CLIENTS)}"
        ) from exc


def find_parent_process_client(max_depth: int = 6) -> str | None:
    pid = os.getppid()
    for _ in range(max_depth):
        if pid <= 1:
            return None
        try:
            result = run_command(
                ["ps", "-p", str(pid), "-o", "ppid=", "-o", "comm="],
                cwd=Path.cwd(),
            )
        except LauncherError:
            return None
        if result.returncode != 0 or not result.stdout:
            return None
        line = result.stdout.splitlines()[0].strip()
        if not line:
            return None
        parts = line.split(None, 1)
        if len(parts) != 2:
            return None
        parent_pid, command = parts
        command_name = Path(command).name.lower()
        for client in BACKEND_PROBE_ORDER:
            if client in command_name:
                return client
        try:
            pid = int(parent_pid)
        except ValueError:
            return None
    return None


def probe_installed_clients() -> list[str]:
    detected: list[str] = []
    for client in BACKEND_PROBE_ORDER:
        if BACKENDS[client].is_available():
            detected.append(client)
    return detected


def select_backend(client_override: str | None, runtime: RuntimeConfig) -> ClientBackend:
    requested = (client_override or runtime.client).strip()
    if requested and requested != "auto":
        backend = get_backend(requested)
        if not backend.is_available():
            raise LauncherError(
                f"requested client '{requested}' is not available on PATH; pass a different "
                "--client or update config.runtime.client"
            )
        return backend

    parent_client = find_parent_process_client()
    if parent_client:
        backend = get_backend(parent_client)
        if backend.is_available():
            return backend

    installed_clients = probe_installed_clients()
    if len(installed_clients) == 1:
        return get_backend(installed_clients[0])
    if len(installed_clients) > 1:
        raise LauncherError(
            "auto-detection found multiple installed clients "
            f"({', '.join(installed_clients)}); pass --client explicitly"
        )
    raise LauncherError(
        "could not auto-detect a supported client; install one of "
        f"{', '.join(BACKEND_PROBE_ORDER)} or pass --client explicitly"
    )


def validate_runtime(config: SkillConfig, backend: ClientBackend, cwd: Path) -> ValidationReport:
    start_time = time.monotonic()
    issues: list[str] = []
    configured_mcp_names: list[str] = []
    required_mcp_names = [
        config.mcp_servers.search,
        config.mcp_servers.reader,
        config.mcp_servers.vision,
        config.mcp_servers.repository,
    ]
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

        for server_name in required_mcp_names:
            if server_name not in rendered:
                issues.append(f"{path} does not mention MCP server '{server_name}'")

    if not backend.is_available():
        issues.append(f"selected client '{backend.name}' is not available on PATH")
        return ValidationReport(
            client=backend.name,
            configured_mcp_names=[],
            required_mcp_names=required_mcp_names,
            missing_mcp_names=required_mcp_names,
            vector_memory_available=vector_is_available(),
            issues=issues,
            duration_ms=elapsed_ms(start_time),
        )

    try:
        configured_mcp_names = sorted(backend.list_mcp_names(cwd))
    except LauncherError as exc:
        issues.append(str(exc))
        return ValidationReport(
            client=backend.name,
            configured_mcp_names=[],
            required_mcp_names=required_mcp_names,
            missing_mcp_names=required_mcp_names,
            vector_memory_available=vector_is_available(),
            issues=issues,
            duration_ms=elapsed_ms(start_time),
        )

    missing_mcp_names: list[str] = []
    for server_name in required_mcp_names:
        if server_name not in configured_mcp_names:
            missing_mcp_names.append(server_name)
            issues.append(
                f"{backend.display_name} does not have MCP server '{server_name}' configured"
            )

    return ValidationReport(
        client=backend.name,
        configured_mcp_names=configured_mcp_names,
        required_mcp_names=required_mcp_names,
        missing_mcp_names=missing_mcp_names,
        vector_memory_available=vector_is_available(),
        issues=issues,
        duration_ms=elapsed_ms(start_time),
    )


def detect_unhealthy_codex_mcps(
    backend: CodexBackend,
    cwd: Path,
    configured_mcp_names: list[str],
    candidate_names: list[str],
) -> dict[str, str]:
    unhealthy: dict[str, str] = {}
    probe_prompt = "Reply with exactly OK."

    for name in candidate_names:
        if name not in configured_mcp_names:
            continue

        transport = backend.get_mcp_transport(name, cwd)
        if transport not in REMOTE_MCP_TRANSPORTS:
            continue

        disabled_mcp_names = [
            other
            for other in candidate_names
            if other in configured_mcp_names and other != name
        ]
        try:
            probe_result = backend.run_exec_prompt(
                probe_prompt,
                cwd,
                disabled_mcp_names=disabled_mcp_names,
                timeout_seconds=CODEX_MCP_PROBE_TIMEOUT_SECONDS,
            )
        except LauncherError as exc:
            rmcp_errors = extract_rmcp_fatal_lines(str(exc))
            if rmcp_errors:
                unhealthy[name] = rmcp_errors[0]
                continue
            raise
        if probe_result.rmcp_errors:
            unhealthy[name] = probe_result.rmcp_errors[0]

    return unhealthy


def run(
    query: str,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    output_dir: str | None = None,
    config_path: str | None = None,
    client: str | None = None,
    emit_progress: bool = False,
) -> dict[str, Any]:
    start_time = time.monotonic()
    config = load_config(config_path)
    backend = select_backend(client, config.runtime)
    runtime_cwd = Path.cwd().resolve()
    required_mcp_names = [
        config.mcp_servers.search,
        config.mcp_servers.reader,
        config.mcp_servers.vision,
        config.mcp_servers.repository,
    ]

    validation_report = validate_runtime(config, backend, runtime_cwd)
    if not validation_report.is_ok:
        raise LauncherError("invalid skill configuration:\n- " + "\n- ".join(validation_report.issues))

    disabled_mcp_names: list[str] = []
    if isinstance(backend, CodexBackend):
        unhealthy_mcps = detect_unhealthy_codex_mcps(
            backend,
            runtime_cwd,
            validation_report.configured_mcp_names,
            required_mcp_names,
        )
        disabled_mcp_names = sorted(unhealthy_mcps)
    active_mcp_names = [
        name
        for name in validation_report.configured_mcp_names
        if name not in disabled_mcp_names
    ]

    configure_runtime(config)
    memory_init_memory()

    session_id = build_session_id(query)
    resolved_output_dir = resolve_output_dir(output_dir)

    if emit_progress:
        print(f"Client: {backend.name}", flush=True)
        print(
            "Configured MCPs: "
            + (", ".join(validation_report.configured_mcp_names) if validation_report.configured_mcp_names else "(none)")
        , flush=True)
        print(
            "Active MCPs for this run: "
            + (", ".join(active_mcp_names) if active_mcp_names else "(none)")
        , flush=True)
        print(
            "Disabled MCPs for this run: "
            + (", ".join(disabled_mcp_names) if disabled_mcp_names else "(none)")
        , flush=True)

    planner_raw = backend.run_prompt(
        build_planner_prompt(
            config,
            query,
            disabled_mcp_names=disabled_mcp_names,
        ),
        runtime_cwd,
        disabled_mcp_names=disabled_mcp_names,
    )
    plan = extract_json_block(planner_raw)

    if plan.get("need_user_input"):
        return {
            "status": "clarification_required",
            "client": backend.name,
            "session_id": session_id,
            "report_path": None,
            "iteration_count": 0,
            "clarification_questions": list(plan.get("questions", [])),
            "duration_ms": elapsed_ms(start_time),
            "token_usage": None,
            "configured_mcp_names": validation_report.configured_mcp_names,
            "active_mcp_names": active_mcp_names,
            "disabled_mcp_names": disabled_mcp_names,
        }

    clarified_query = plan["clarified_query"]
    quality_goal = plan["quality_goal"]
    recommended_mcps = [
        name
        for name in unique_preserve_order(plan.get("recommended_mcps", []))
        if name not in disabled_mcp_names
    ]
    if not recommended_mcps:
        recommended_mcps = [
            name for name in required_mcp_names if name not in disabled_mcp_names
        ]
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
        researcher_raw = backend.run_prompt(
            build_researcher_prompt(
                config=config,
                quality_goal=quality_goal,
                iteration=iteration,
                query=current_query,
                prior_summaries=prior_summaries,
                recommended_mcps=recommended_mcps,
                memory_context=memory_context,
                disabled_mcp_names=disabled_mcp_names,
            ),
            runtime_cwd,
            disabled_mcp_names=disabled_mcp_names,
        )
        researcher_payload = extract_json_block(researcher_raw)

        summarizer_raw = backend.run_prompt(
            build_summarizer_prompt(
                config=config,
                iteration=iteration,
                query=current_query,
                researcher_payload=researcher_payload,
            ),
            runtime_cwd,
            disabled_mcp_names=disabled_mcp_names,
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

    final_report = backend.run_prompt(
        build_final_synthesis_prompt(
            config=config,
            clarified_query=clarified_query,
            quality_goal=quality_goal,
            iteration_payloads=iteration_payloads,
        ),
        runtime_cwd,
        disabled_mcp_names=disabled_mcp_names,
    )
    report_path = save_final_report(session_id, resolved_output_dir, final_report)

    return {
        "status": "success",
        "client": backend.name,
        "session_id": session_id,
        "report_path": str(report_path),
        "iteration_count": len(iteration_payloads),
        "clarification_questions": [],
        "duration_ms": elapsed_ms(start_time),
        "token_usage": None,
        "configured_mcp_names": validation_report.configured_mcp_names,
        "active_mcp_names": active_mcp_names,
        "disabled_mcp_names": disabled_mcp_names,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the zai-deep-research skill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/run.py --validate --client codex\n"
            "  python scripts/run.py --validate --client codex --json\n"
            "  python scripts/run.py \"Compare the latest MCP servers\" --client codex\n"
            "  python scripts/run.py \"Compare the latest MCP servers\" --client codex --json\n"
            "  ZAI_DEEP_RESEARCH_COMMAND_TIMEOUT_SECONDS=600 python scripts/run.py "
            "\"Compare the latest MCP servers\" --client codex\n\n"
            "Exit codes:\n"
            "  0  success\n"
            "  1  validation or runtime error\n"
            "  2  clarification required before research can continue\n"
        ),
    )
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
        "--client",
        choices=SUPPORTED_CLIENTS,
        default=None,
        help="Runtime client backend. Defaults to config.runtime.client or auto-detection.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate config, agent templates, backend selection, and MCP wiring without running research.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout. Errors stay on stderr unless a JSON payload can be produced.",
    )
    args = parser.parse_args(argv)
    if not args.validate and not args.query:
        parser.error("query is required unless --validate is used")
    return args


def print_validation_report(report: ValidationReport, runtime_config: SkillConfig) -> None:
    if report.is_ok:
        print(f"Validation passed for {runtime_config.skill_name}")
    else:
        print("Validation failed:")
        for issue in report.issues:
            print(f"- {issue}")
    print(f"Client: {report.client}")
    print(f"Configured MCPs: {', '.join(report.configured_mcp_names) if report.configured_mcp_names else '(none detected)'}")
    if report.missing_mcp_names:
        print(f"Missing MCPs: {', '.join(report.missing_mcp_names)}")
    print(f"Memory DB: {runtime_config.storage.memory_db_path}")
    print(f"Vector index: {runtime_config.storage.vector_index_path}")
    print(f"Vector metadata: {runtime_config.storage.vector_metadata_path}")
    print(
        "Required MCP servers: "
        f"{runtime_config.mcp_servers.search}, "
        f"{runtime_config.mcp_servers.reader}, "
        f"{runtime_config.mcp_servers.vision}, "
        f"{runtime_config.mcp_servers.repository}"
    )
    print(
        "Vector memory: "
        + ("enabled" if report.vector_memory_available else "optional dependency unavailable")
    )


def print_run_result(result: dict[str, Any], skill_name: str) -> int:
    if result["status"] == "clarification_required":
        print(f"Clarification required before {skill_name} research:\n")
        for idx, question in enumerate(result["clarification_questions"], start=1):
            print(f"{idx}. {question}")
        return 2

    print(f"Saved: {result['report_path']}")
    return 0


def main(arguments: argparse.Namespace) -> int:
    runtime_config = load_config(arguments.config)
    backend = select_backend(arguments.client, runtime_config.runtime)

    if arguments.validate:
        report = validate_runtime(runtime_config, backend, Path.cwd().resolve())
        if arguments.json:
            emit_json(report.to_payload())
        else:
            print_validation_report(report, runtime_config)
        return 0 if report.is_ok else 1

    result = run(
        " ".join(arguments.query),
        max_iterations=arguments.max_iterations,
        output_dir=arguments.output_dir,
        config_path=arguments.config,
        client=arguments.client,
        emit_progress=not arguments.json,
    )
    if arguments.json:
        emit_json(result)
        return 2 if result["status"] == "clarification_required" else 0
    return print_run_result(result, runtime_config.skill_name)


def cli(argv: list[str]) -> int:
    arguments = parse_args(argv)
    try:
        return main(arguments)
    except LauncherError as exc:
        if arguments.json:
            emit_json(
                {
                    "status": "error",
                    "client": arguments.client,
                    "issues": [str(exc)],
                }
            )
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception:
        if arguments.json:
            emit_json(
                {
                    "status": "error",
                    "client": arguments.client,
                    "issues": ["unexpected launcher error"],
                }
            )
        else:
            print("INTERNAL CRASH: unexpected launcher error", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
