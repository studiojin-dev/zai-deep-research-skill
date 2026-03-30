from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILL_NAME = "zai-deep-research"
DEFAULT_MCP_SERVERS = {
    "search": "web-search-zai",
    "reader": "web-reader-zai",
    "vision": "vision-zai",
    "repository": "zread",
}
SUPPORTED_CLIENTS = ("auto", "codex", "claude", "opencode", "gemini")


def _default_data_dir() -> Path:
    return Path.cwd().resolve() / f".{DEFAULT_SKILL_NAME}"


def _expand_path(value: str | None, base_dir: Path | None = None) -> Path | None:
    if value is None:
        return None
    path = Path(os.path.expanduser(value))
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve()


@dataclass(frozen=True)
class StorageConfig:
    data_dir: Path
    memory_db_path: Path
    vector_index_path: Path
    vector_metadata_path: Path


@dataclass(frozen=True)
class McpConfig:
    search: str
    reader: str
    vision: str
    repository: str


@dataclass(frozen=True)
class RuntimeConfig:
    client: str


@dataclass(frozen=True)
class SkillConfig:
    skill_name: str
    storage: StorageConfig
    mcp_servers: McpConfig
    runtime: RuntimeConfig
    config_path: Path | None


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merged[key] = _merge_dict(base[key], value)
        else:
            merged[key] = value
    return merged


def _build_default_payload() -> dict[str, Any]:
    data_dir = _default_data_dir()
    return {
        "skill_name": DEFAULT_SKILL_NAME,
        "runtime": {
            "client": "auto",
        },
        "storage": {
            "data_dir": str(data_dir),
            "memory_db_path": str(data_dir / "memory.sqlite"),
            "vector_index_path": str(data_dir / "vector.index"),
            "vector_metadata_path": str(data_dir / "vector.jsonl"),
        },
        "mcp_servers": dict(DEFAULT_MCP_SERVERS),
    }


def load_config(config_path: str | None = None) -> SkillConfig:
    runtime_cwd = Path.cwd().resolve()
    resolved_config_path = _expand_path(config_path, runtime_cwd) if config_path else None
    if resolved_config_path is None:
        cwd_config_path = runtime_cwd / "config.json"
        if cwd_config_path.exists():
            resolved_config_path = cwd_config_path.resolve()
        else:
            default_path = SKILL_ROOT / "config.json"
            resolved_config_path = default_path.resolve() if default_path.exists() else None

    payload = _build_default_payload()
    if resolved_config_path is not None:
        override = json.loads(resolved_config_path.read_text(encoding="utf-8"))
        payload = _merge_dict(payload, override)

    skill_name = str(payload["skill_name"]).strip()
    if skill_name != DEFAULT_SKILL_NAME:
        raise ValueError(
            f"skill_name must be '{DEFAULT_SKILL_NAME}' to match the directory and spec"
        )

    runtime_data = payload.get("runtime", {})
    client = str(runtime_data.get("client", "auto")).strip() or "auto"
    if client not in SUPPORTED_CLIENTS:
        raise ValueError(
            f"runtime.client must be one of {', '.join(SUPPORTED_CLIENTS)}, got '{client}'"
        )

    storage_data = payload["storage"]
    data_dir = _expand_path(storage_data.get("data_dir"), runtime_cwd)
    if data_dir is None:
        raise ValueError("storage.data_dir is required")

    storage = StorageConfig(
        data_dir=data_dir,
        memory_db_path=_expand_path(storage_data.get("memory_db_path"), data_dir)
        or data_dir / "memory.sqlite",
        vector_index_path=_expand_path(storage_data.get("vector_index_path"), data_dir)
        or data_dir / "vector.index",
        vector_metadata_path=_expand_path(storage_data.get("vector_metadata_path"), data_dir)
        or data_dir / "vector.jsonl",
    )

    mcp_data = payload["mcp_servers"]
    mcp_servers = McpConfig(
        search=str(mcp_data["search"]).strip(),
        reader=str(mcp_data["reader"]).strip(),
        vision=str(mcp_data["vision"]).strip(),
        repository=str(mcp_data["repository"]).strip(),
    )

    return SkillConfig(
        skill_name=skill_name,
        storage=storage,
        mcp_servers=mcp_servers,
        runtime=RuntimeConfig(client=client),
        config_path=resolved_config_path,
    )
