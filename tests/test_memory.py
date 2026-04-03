from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


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


memory_module = load_module("zai_deep_research_memory", "memory.py")


@unittest.skipUnless(memory_module.is_available(), "SQLite FTS5 is unavailable")
class MemoryModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "memory.sqlite"
        memory_module.configure(self.db_path)
        memory_module.init_memory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_init_memory_creates_required_tables(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            connection.close()

        self.assertIn("iterations", tables)
        self.assertIn("reports", tables)
        self.assertIn("artifacts", tables)
        self.assertIn("iterations_fts", tables)

    def test_search_hits_query_summary_and_title(self) -> None:
        memory_module.save_iteration(
            session_id="session-a",
            iteration=1,
            query="alpha research question",
            summary_md="This summary mentions beta evidence.",
            findings=[],
        )
        memory_module.save_report(
            session_id="session-a",
            title="Gamma Report",
            report_path=str(Path(self.tempdir.name) / "report.md"),
            report_md="# Gamma Report",
        )

        query_hits = memory_module.search_iterations("alpha", limit=5)
        summary_hits = memory_module.search_iterations("beta", limit=5)
        title_hits = memory_module.search_iterations("Gamma", limit=5)

        self.assertEqual(query_hits[0]["session_id"], "session-a")
        self.assertEqual(summary_hits[0]["session_id"], "session-a")
        self.assertEqual(title_hits[0]["title"], "Gamma Report")

    def test_save_report_backfills_titles_and_updates_fts(self) -> None:
        memory_module.save_iteration(
            session_id="session-a",
            iteration=1,
            query="common topic",
            summary_md="Summary text",
            findings=[],
        )
        memory_module.save_iteration(
            session_id="session-a",
            iteration=2,
            query="common topic follow-up",
            summary_md="More summary text",
            findings=[],
        )

        memory_module.save_report(
            session_id="session-a",
            title="Backfilled Title",
            report_path=str(Path(self.tempdir.name) / "report.md"),
            report_md="# Backfilled Title",
        )

        connection = sqlite3.connect(self.db_path)
        try:
            titles = connection.execute(
                "SELECT DISTINCT title FROM iterations WHERE session_id = ?",
                ("session-a",),
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(titles, [("Backfilled Title",)])
        results = memory_module.search_iterations("Backfilled", limit=5)
        self.assertEqual(results[0]["title"], "Backfilled Title")

    def test_search_respects_limit_and_excluded_session(self) -> None:
        memory_module.save_iteration(
            session_id="session-a",
            iteration=1,
            query="shared phrase",
            summary_md="first",
            findings=[],
        )
        memory_module.save_iteration(
            session_id="session-b",
            iteration=1,
            query="shared phrase",
            summary_md="second",
            findings=[],
        )
        memory_module.save_iteration(
            session_id="session-c",
            iteration=1,
            query="shared phrase",
            summary_md="third",
            findings=[],
        )

        results = memory_module.search_iterations(
            "shared",
            limit=1,
            exclude_session_id="session-b",
        )

        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0]["session_id"], "session-b")


if __name__ == "__main__":
    unittest.main()
