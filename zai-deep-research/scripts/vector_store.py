from __future__ import annotations

import contextlib
import io
import json
import logging
import os
from pathlib import Path
from typing import Any

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
QUIET_LOGGERS = (
    "huggingface_hub",
    "sentence_transformers",
    "transformers",
)

try:
    import faiss  # type: ignore
    import numpy as np  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception as exc:  # pragma: no cover - dependency dependent
    faiss = None
    np = None
    SentenceTransformer = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

_INDEX_PATH: Path | None = None
_METADATA_PATH: Path | None = None
_MODEL_NAME = DEFAULT_MODEL_NAME
_MODEL: Any = None


def _quiet_logging() -> tuple[list[tuple[logging.Logger, int]], dict[str, str | None]]:
    logger_states: list[tuple[logging.Logger, int]] = []
    for name in QUIET_LOGGERS:
        logger = logging.getLogger(name)
        logger_states.append((logger, logger.level))
        logger.setLevel(logging.ERROR)

    env_backup = {
        "HF_HUB_DISABLE_PROGRESS_BARS": os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS"),
        "HF_HUB_DISABLE_TELEMETRY": os.environ.get("HF_HUB_DISABLE_TELEMETRY"),
        "TOKENIZERS_PARALLELISM": os.environ.get("TOKENIZERS_PARALLELISM"),
    }
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    return logger_states, env_backup


def _restore_logging(
    logger_states: list[tuple[logging.Logger, int]],
    env_backup: dict[str, str | None],
) -> None:
    for logger, level in logger_states:
        logger.setLevel(level)
    for key, value in env_backup.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def configure(
    index_path: str | Path,
    metadata_path: str | Path | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
) -> None:
    global _INDEX_PATH, _METADATA_PATH, _MODEL_NAME, _MODEL
    _INDEX_PATH = Path(index_path).expanduser().resolve()
    _METADATA_PATH = (
        Path(metadata_path).expanduser().resolve()
        if metadata_path is not None
        else _INDEX_PATH.with_suffix(".jsonl")
    )
    if model_name != _MODEL_NAME:
        _MODEL = None
    _MODEL_NAME = model_name


def _require_paths() -> tuple[Path, Path]:
    if _INDEX_PATH is None or _METADATA_PATH is None:
        raise RuntimeError("vector store is not configured")
    return _INDEX_PATH, _METADATA_PATH


def is_available() -> bool:
    return (
        _IMPORT_ERROR is None
        and _INDEX_PATH is not None
        and _METADATA_PATH is not None
    )


def _load_model() -> Any:
    global _MODEL
    if not is_available():
        return None
    if _MODEL is None:
        logger_states, env_backup = _quiet_logging()
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                _MODEL = SentenceTransformer(_MODEL_NAME)
        finally:
            _restore_logging(logger_states, env_backup)
    return _MODEL


def _load_index(dimension: int) -> Any:
    index_path, _ = _require_paths()
    if index_path.exists():
        return faiss.read_index(str(index_path))
    return faiss.IndexFlatL2(dimension)


def _save_index(index: Any) -> None:
    index_path, _ = _require_paths()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))


def _load_metadata_rows() -> list[dict[str, Any]]:
    _, metadata_path = _require_paths()
    if not metadata_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with metadata_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _append_metadata_rows(rows: list[dict[str, Any]]) -> None:
    _, metadata_path = _require_paths()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def add_texts(texts: list[str], metadata_items: list[dict[str, Any]]) -> None:
    if not texts or not is_available():
        return
    if len(texts) != len(metadata_items):
        raise ValueError("texts and metadata_items must have the same length")

    try:
        model = _load_model()
        logger_states, env_backup = _quiet_logging()
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                embeddings = np.asarray(model.encode(texts), dtype="float32")
        finally:
            _restore_logging(logger_states, env_backup)
        index = _load_index(embeddings.shape[1])
        index.add(embeddings)
        _save_index(index)

        rows: list[dict[str, Any]] = []
        for text, metadata in zip(texts, metadata_items, strict=True):
            row = dict(metadata)
            row["text"] = text
            rows.append(row)
        _append_metadata_rows(rows)
    except Exception:  # pragma: no cover - optional dependency path
        return


def similarity_search(query: str, k: int = 5) -> list[dict[str, Any]]:
    if not query or not is_available():
        return []

    try:
        model = _load_model()
        metadata_rows = _load_metadata_rows()
        if not metadata_rows:
            return []

        index = _load_index(model.get_sentence_embedding_dimension())
        if index.ntotal == 0:
            return []

        logger_states, env_backup = _quiet_logging()
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                query_vector = np.asarray(model.encode([query]), dtype="float32")
        finally:
            _restore_logging(logger_states, env_backup)
        distances, indices = index.search(query_vector, min(k, index.ntotal))

        results: list[dict[str, Any]] = []
        for distance, index_position in zip(distances[0], indices[0], strict=True):
            if index_position < 0 or index_position >= len(metadata_rows):
                continue
            row = dict(metadata_rows[index_position])
            row["distance"] = float(distance)
            results.append(row)
        return results
    except Exception:  # pragma: no cover - optional dependency path
        return []
