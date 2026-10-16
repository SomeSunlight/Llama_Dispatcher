"""S00: SQLite schema/provenance and stubbed llama.cpp lifecycle contracts."""
import asyncio
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import dispatcher_core as core  # noqa: E402
from database_manager import MetricsDatabase  # noqa: E402

SCHEMA = ROOT / "src" / "init_db.sql"


class DatabaseCharacterization(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "metrics.db"

    def test_fresh_schema_views_and_forwarded_not_observed_parameters(self):
        db = MetricsDatabase(self.path, SCHEMA, machine_id="synthetic-win")
        db.insert_run(
            "run-1", "serve", "test", "llama.cpp test", "/synthetic/llama-server",
            "/synthetic/llama-server --port 8181",
            {"port": "8181"}, preset_path="/tmp/test.ini",
            preset_content="[base]\nmodel = tiny.gguf",
            preset_sha256="stub-hash",
        )
        runtime_id = db.insert_serve_model_instance(
            "run-1", "base", 8188,
            {"model": "tiny.gguf", "ctx-size": 8192},
            {"model": "tiny.gguf", "ctx-size": "8192"},
            "llama-server --model tiny.gguf",
        )
        db.insert_serve_telemetry(
            "run-1", runtime_id, "base", 8188, 0, 12,
            10, 5, 123.0, 42.0, 0.4,
        )
        db.insert_proxy_request(
            run_id="run-1", endpoint="chat/completions",
            model_requested="base", client_model="agent",
            resolved_profile="work", target_model="base", alias_remapped=1,
            stream=0, req_temperature=0.2, req_top_p=0.95,
            req_top_k=None, req_min_p=None, req_max_tokens=32,
            req_enable_thinking=0, effective_repeat_penalty=None,
            client_params={"model": "agent", "temperature": 0.9},
            effective_params={"model": "base", "temperature": 0.2},
            parameter_changes={"temperature": {"source": "dispatcher_policy"}},
            prompt_tokens=10, completion_tokens=5, finish_reason="stop",
            duration=0.4, ttft=0.1, status_code=200,
        )
        with sqlite3.connect(self.path) as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            run = con.execute(
                "SELECT machine_id,llama_binary,cli_command,startup_params,preset_content "
                "FROM execution_runs WHERE run_id='run-1'").fetchone()
            proxy = con.execute(
                "SELECT client_model,target_model,client_params_json,effective_params_json,"
                "parameter_changes_json FROM metrics_proxy_requests").fetchone()
            overview = con.execute(
                "SELECT machine_id,client_model,target_model,changed_parameter_count "
                "FROM v_proxy_request_summary").fetchone()
            serve = con.execute(
                "SELECT llama_binary,runtime_instance_id,prompt_tokens,gen_tokens "
                "FROM v_serve_telemetry").fetchone()
        self.assertEqual(version, 8)
        self.assertIn("metrics_proxy_requests", tables)
        self.assertNotIn("proxy_requests", tables)
        self.assertEqual(run[:2], ("synthetic-win", "/synthetic/llama-server"))
        self.assertIn("--port 8181", run[2])
        self.assertEqual(json.loads(run[3]), {"port": "8181"})
        self.assertEqual(run[4], "[base]\nmodel = tiny.gguf")
        self.assertEqual(proxy[:2], ("agent", "base"))
        self.assertEqual(json.loads(proxy[2])["temperature"], 0.9)
        self.assertEqual(json.loads(proxy[3])["temperature"], 0.2)
        self.assertEqual(json.loads(proxy[4])["temperature"]["source"], "dispatcher_policy")
        self.assertEqual(overview, ("synthetic-win", "agent", "base", 1))
        self.assertEqual(serve, ("/synthetic/llama-server", runtime_id, 10, 5))

    def test_legacy_request_columns_are_backfilled_only_when_observable(self):
        # A deliberately minimal legacy layout. No real instance DB is modified.
        with sqlite3.connect(self.path) as con:
            con.executescript("""
                CREATE TABLE execution_runs (
                    run_id TEXT PRIMARY KEY, timestamp TEXT, tool_mode TEXT,
                    ensemble_name TEXT, llama_version TEXT,
                    cli_command TEXT NOT NULL, startup_params TEXT NOT NULL
                );
                INSERT INTO execution_runs
                    (run_id,tool_mode,ensemble_name,llama_version,cli_command,startup_params)
                    VALUES ('old-1','serve','old','legacy','llama-server --port 8080','{}');
                CREATE TABLE metrics_proxy_requests (
                    id INTEGER PRIMARY KEY, machine_id TEXT, run_id TEXT,
                    timestamp TEXT, endpoint TEXT NOT NULL, model_requested TEXT,
                    stream INTEGER, req_temperature REAL, req_top_p REAL,
                    req_top_k INTEGER, req_min_p REAL, req_max_tokens INTEGER,
                    req_enable_thinking INTEGER, prompt_tokens INTEGER,
                    completion_tokens INTEGER, finish_reason TEXT, duration REAL,
                    ttft REAL, status_code INTEGER
                );
                INSERT INTO metrics_proxy_requests
                    (id,model_requested,endpoint,stream,req_temperature,req_enable_thinking)
                    VALUES (1,'base','chat/completions',0,0.2,0);
            """)
        MetricsDatabase(self.path, SCHEMA, machine_id="later")
        MetricsDatabase(self.path, SCHEMA, machine_id="later")  # idempotent
        with sqlite3.connect(self.path) as con:
            run = con.execute(
                "SELECT machine_id,llama_binary FROM execution_runs WHERE run_id='old-1'"
            ).fetchone()
            row = con.execute(
                "SELECT target_model,effective_temperature,effective_enable_thinking,"
                "client_model,resolved_profile,client_params_json,"
                "effective_params_json,parameter_changes_json "
                "FROM metrics_proxy_requests WHERE id=1"
            ).fetchone()
            version = con.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 8)
        self.assertEqual(run, ("unknown", None))
        self.assertEqual(row[:3], ("base", 0.2, 0))
        self.assertEqual(row[3:], (None, None, None, None, None))


class LifecycleCharacterization(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.orc = object.__new__(core.LlamaOrchestrator)
        self.orc.db = Mock()
        self.orc.db.insert_serve_model_instance.return_value = 45
        self.orc.ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def test_router_child_spawn_and_log_telemetry(self):
        stream = asyncio.StreamReader()
        stream.feed_data(
            b"spawning server instance with name=base on port 8188\n"
            b"srv load: --model\n"
            b"srv load: /synthetic/tiny.gguf\n"
            b"srv load: --ctx-size\n"
            b"srv load: 8192\n"
            b'[8188] cmd_child_to_router:info:{"id":"base"}\n'
            b'{"message":"model load","model_alias":"base","timings":'
            b'{"prompt_n":10,"predicted_n":5,"prompt_tps":100.0,'
            b'"predicted_tps":50.0,"prompt_ms":100,"predicted_ms":100}}\n'
        )
        stream.feed_eof()
        await self.orc._read_server_json_stream(
            stream, "run-1", {"models": {"base": {"model": "tiny.gguf"}}},
        )
        row = self.orc.db.insert_serve_model_instance.call_args.kwargs
        self.assertEqual(row["model_alias"], "base")
        self.assertEqual(row["child_port"], 8188)
        self.assertEqual(row["effective_args"]["model"], "/synthetic/tiny.gguf")
        self.assertEqual(row["effective_args"]["ctx-size"], "8192")
        self.orc.db.update_serve_model_instance_meta.assert_called_once_with(
            45, {"id": "base"}
        )
        self.assertEqual(self.orc.db.insert_serve_telemetry.call_args.kwargs["runtime_instance_id"], 45)
        self.assertEqual(self.orc.db.insert_serve_telemetry.call_args.kwargs["p_tokens"], 10)

    async def test_log_reader_cancellation_propagates(self):
        stream = asyncio.StreamReader()
        task = asyncio.create_task(self.orc._read_server_json_stream(stream, "run-1"))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_stop_only_terminates_active_child(self):
        process = SimpleNamespace(terminate=Mock(), wait=AsyncMock())
        self.orc.current_process = process
        self.orc.is_running = True
        with patch.object(core, "orchestrator", self.orc):
            result = await core.api_stop()
            self.assertEqual(result["status"], "success")
            self.assertFalse(self.orc.is_running)
            process.terminate.assert_called_once()
            process.wait.assert_awaited_once()
            idle = await core.api_stop()
            self.assertEqual(idle["status"], "idle")
            self.assertEqual(process.terminate.call_count, 1)

    async def test_immediate_profile_crash_has_fatal_exit_boundary(self):
        # Never invoke the real exit; pin the legacy <45s behavior with a stub.
        self.orc.compile_serve_profile = Mock(return_value=(
            "/synthetic/llama-server", {"models": {"work": {"port": 8181}}}, ["--port", "8181"],
        ))
        self.orc.get_llama_version = AsyncMock(return_value="synthetic")
        self.orc._read_server_json_stream = AsyncMock()
        self.orc.api_port = 8001
        process = SimpleNamespace(stdout=None, wait=AsyncMock(), returncode=1)
        with patch.object(core.asyncio, "create_subprocess_exec",
                          new=AsyncMock(return_value=process)), \
             patch.object(core.os, "_exit", side_effect=SystemExit(1)):
            with self.assertRaises(SystemExit) as caught:
                await self.orc.run_profile_server_loop("work", {})
        self.assertEqual(caught.exception.code, 1)
        self.orc.db.close_serve_model_instance.assert_called_once()
        self.assertEqual(self.orc.db.close_serve_model_instance.call_args.kwargs["status"],
                         "crashed")


if __name__ == "__main__":
    unittest.main()
