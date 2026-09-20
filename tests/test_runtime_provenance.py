import asyncio
import json
import sqlite3
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from database_manager import MetricsDatabase  # noqa: E402
from dispatcher_core import LlamaOrchestrator  # noqa: E402


class RuntimeProvenanceTests(unittest.TestCase):
    def test_execution_run_records_effective_binary_version_and_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "metrics.db"
            db = MetricsDatabase(
                db_path=db_path,
                sql_file=ROOT / "src" / "init_db.sql",
                machine_id="test-machine",
            )
            db.insert_run(
                run_id="run-1",
                mode="serve",
                ensemble="test",
                version="llama.cpp version 1234 (abcdef)",
                binary="/effective/llama/bin/llama-server",
                cmd="/effective/llama/bin/llama-server --host 0.0.0.0 --port 8081",
                params={"host": "0.0.0.0", "port": "8081"},
            )

            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    """
                    SELECT llama_version, llama_binary, cli_command, startup_params
                    FROM execution_runs
                    WHERE run_id = 'run-1'
                    """
                ).fetchone()
                user_version = conn.execute("PRAGMA user_version").fetchone()[0]

            self.assertEqual(user_version, 8)
            self.assertEqual(row[0], "llama.cpp version 1234 (abcdef)")
            self.assertEqual(row[1], "/effective/llama/bin/llama-server")
            self.assertTrue(row[2].startswith("/effective/llama/bin/llama-server"))
            self.assertEqual(json.loads(row[3]), {"host": "0.0.0.0", "port": "8081"})
            self.assertNotIn("bin_dir", json.loads(row[3]))
            self.assertNotIn("bin-dir", json.loads(row[3]))

    def test_effective_cli_args_do_not_include_engine_fallback(self):
        orchestrator = object.__new__(LlamaOrchestrator)
        params = orchestrator._parse_cli_args(
            [
                "--host",
                "0.0.0.0",
                "--port",
                "8081",
                "--models-preset",
                "/tmp/models.ini",
            ]
        )
        self.assertEqual(params["host"], "0.0.0.0")
        self.assertEqual(params["port"], "8081")
        self.assertEqual(params["models-preset"], "/tmp/models.ini")
        self.assertNotIn("bin-dir", params)
        self.assertNotIn("server-bin", params)
        self.assertNotIn("binary", params)

    def test_version_is_read_from_effective_binary(self):
        if sys.platform == "win32":
            self.skipTest("POSIX executable fixture")

        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "llama-server"
            binary.write_text(
                "#!/bin/sh\n"
                "echo 'llama.cpp version 1234'\n"
                "echo 'commit abcdef123456'\n",
                encoding="utf-8",
            )
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR)

            orchestrator = object.__new__(LlamaOrchestrator)
            version = asyncio.run(orchestrator.get_llama_version(binary))

        self.assertEqual(version, "llama.cpp version 1234 [commit abcdef123456]")


if __name__ == "__main__":
    unittest.main()
