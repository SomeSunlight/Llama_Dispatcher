import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any


def _fmt_offset(ts: datetime.datetime) -> str:
    """Formats a timezone-aware datetime as 'YYYY-MM-DD HH:MM:SS+HH:MM'."""
    s = ts.strftime("%Y-%m-%d %H:%M:%S%z")
    # %z returns '+0200', ISO 8601 requires '+02:00'
    if len(s) > 19 and s[-5] in ("+", "-") and ":" not in s[-5:]:
        s = s[:-2] + ":" + s[-2:]
    return s


def _now_local() -> str:
    """Local time with correct UTC offset as a DB timestamp string.

    Example: '2026-06-15 09:21:00+02:00'

    SQLite stores timestamps as TEXT. The explicit offset makes the time
    timezone-aware, correctly sortable and immediately readable in any viewer –
    without silent UTC shifting. The SQL standard CURRENT_TIMESTAMP always returns
    UTC without a marker, which leads to apparently wrong times on UTC+N systems.
    """
    return _fmt_offset(datetime.datetime.now().astimezone())


class MetricsDatabase:
    def __init__(self, db_path="data/metrics_v4.db", sql_file="src/init_db.sql", machine_id: str = "unknown"):
        self.db_path = Path(db_path)
        self.sql_file = Path(sql_file)
        self.machine_id = machine_id
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._upgrade_schema()

    def _init_db(self):
        if not self.sql_file.exists():
            print(f"[WARNING] SQL init file {self.sql_file} not found. Schema creation skipped.")
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with open(self.sql_file, "r", encoding="utf-8") as f:
                conn.executescript(f.read())

    def _upgrade_schema(self):
        """Apply additive, idempotent schema migrations while preserving measurements."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")

            # v4 → v5: machine_id in execution_runs
            cols = [row[1] for row in conn.execute("PRAGMA table_info(execution_runs)")]
            if "machine_id" not in cols:
                conn.execute(
                    "ALTER TABLE execution_runs ADD COLUMN machine_id TEXT NOT NULL DEFAULT 'unknown'"
                )
                print("[DB] Schema upgrade v4→v5: added execution_runs.machine_id.")

            # v7 → v8: explicit effective llama.cpp binary provenance.
            # Historical rows remain NULL because cli_command may not be safely reversible.
            cols = [row[1] for row in conn.execute("PRAGMA table_info(execution_runs)")]
            if "llama_binary" not in cols:
                conn.execute("ALTER TABLE execution_runs ADD COLUMN llama_binary TEXT")
                print("[DB] Schema upgrade v7→v8: added execution_runs.llama_binary.")

            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "metrics_proxy_requests" not in tables:
                conn.execute("PRAGMA user_version = 8")
                return

            pcols = {row[1] for row in conn.execute("PRAGMA table_info(metrics_proxy_requests)")}
            additions = {
                "injected_params": "TEXT",
                "client_model": "TEXT",
                "resolved_profile": "TEXT",
                "target_model": "TEXT",
                "alias_remapped": "INTEGER",
                "effective_temperature": "REAL",
                "effective_top_p": "REAL",
                "effective_top_k": "INTEGER",
                "effective_min_p": "REAL",
                "effective_repeat_penalty": "REAL",
                "effective_max_tokens": "INTEGER",
                "effective_enable_thinking": "INTEGER",
                "client_params_json": "TEXT",
                "effective_params_json": "TEXT",
                "parameter_changes_json": "TEXT",
            }
            added = []
            for column, sql_type in additions.items():
                if column not in pcols:
                    conn.execute(f"ALTER TABLE metrics_proxy_requests ADD COLUMN {column} {sql_type}")
                    added.append(column)

            # Historical req_* values were logged after Dispatcher transformation. They can
            # therefore be copied safely to effective_* fields. The original client alias and
            # client parameters were never stored and deliberately remain NULL.
            conn.execute(
                """
                UPDATE metrics_proxy_requests
                SET target_model = COALESCE(target_model, model_requested),
                    effective_temperature = COALESCE(effective_temperature, req_temperature),
                    effective_top_p = COALESCE(effective_top_p, req_top_p),
                    effective_top_k = COALESCE(effective_top_k, req_top_k),
                    effective_min_p = COALESCE(effective_min_p, req_min_p),
                    effective_max_tokens = COALESCE(effective_max_tokens, req_max_tokens),
                    effective_enable_thinking = COALESCE(effective_enable_thinking, req_enable_thinking)
                WHERE target_model IS NULL
                   OR effective_temperature IS NULL
                   OR effective_top_p IS NULL
                   OR effective_top_k IS NULL
                   OR effective_min_p IS NULL
                   OR effective_max_tokens IS NULL
                   OR effective_enable_thinking IS NULL
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_proxy_requests_timestamp "
                "ON metrics_proxy_requests(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_proxy_requests_client_model "
                "ON metrics_proxy_requests(client_model)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_proxy_requests_target_model "
                "ON metrics_proxy_requests(target_model)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_proxy_requests_run "
                "ON metrics_proxy_requests(run_id)"
            )
            conn.execute("PRAGMA user_version = 8")
            if added:
                print("[DB] Schema upgrade to v7: added proxy request logging columns: " + ", ".join(added))

    @staticmethod
    def _json(data: Any) -> str:
        return json.dumps(data if data is not None else {}, ensure_ascii=False, sort_keys=True)

    def insert_run(
        self,
        run_id: str,
        mode: str,
        ensemble: str,
        version: str,
        binary: str,
        cmd: str,
        params: dict,
        preset_path: str | None = None,
        preset_content: str | None = None,
        preset_sha256: str | None = None,
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO execution_runs (
                    run_id, machine_id, timestamp, tool_mode, ensemble_name, llama_version, llama_binary,
                    cli_command, startup_params, preset_path, preset_content, preset_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    self.machine_id,
                    _now_local(),
                    mode,
                    ensemble,
                    version,
                    binary,
                    cmd,
                    self._json(params),
                    preset_path,
                    preset_content,
                    preset_sha256,
                ),
            )

    def insert_serve_model_instance(
        self,
        run_id: str,
        model_alias: str,
        child_port: int | None,
        declared_params: dict | None,
        effective_args: dict | None,
        effective_cli_command: str | None = None,
        status: str = "loaded",
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cur = conn.execute(
                """
                INSERT INTO serve_model_instances (
                    run_id, loaded_at, model_alias, child_port, declared_params,
                    effective_args, effective_cli_command, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    _now_local(),
                    model_alias,
                    child_port,
                    self._json(declared_params),
                    self._json(effective_args),
                    effective_cli_command,
                    status,
                ),
            )
            return int(cur.lastrowid)

    def update_serve_model_instance_meta(self, instance_id: int, meta: dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE serve_model_instances
                SET meta_json = ?
                WHERE id = ?
                """,
                (self._json(meta), instance_id),
            )

    def close_serve_model_instance(self, instance_id: int, status: str = "unloaded"):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE serve_model_instances
                SET unloaded_at = ?, status = ?
                WHERE id = ?
                """,
                (_now_local(), status, instance_id),
            )

    def insert_bench(self, run_id: str, test_type: str, ctx: int, speed: float, speed_error: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO metrics_bench (run_id, test_type, ctx_size, speed, speed_error)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, test_type, ctx, speed, speed_error),
            )

    def insert_eval(self, run_id: str, dataset: str, perplexity: float, perplexity_error: float, duration: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO metrics_eval (run_id, dataset, perplexity, perplexity_error, duration)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, dataset, perplexity, perplexity_error, duration),
            )

    def insert_serve_telemetry(
        self,
        run_id: str,
        runtime_instance_id: int | None,
        model_alias: str,
        child_port: int | None,
        slot_id: int | None,
        task_id: int | None,
        p_tokens: int,
        g_tokens: int,
        i_speed: float,
        g_speed: float,
        duration: float,
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO metrics_serve (
                    run_id, runtime_instance_id, timestamp, model_alias, child_port, slot_id, task_id,
                    p_tokens, g_tokens, i_speed, g_speed, duration
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    runtime_instance_id,
                    _now_local(),
                    model_alias,
                    child_port,
                    slot_id,
                    task_id,
                    p_tokens,
                    g_tokens,
                    i_speed,
                    g_speed,
                    duration,
                ),
            )

    def insert_lifecycle(
        self,
        run_id: str,
        model_alias: str,
        event_type: str,
        duration_ms: float,
        runtime_instance_id: int | None = None,
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO metrics_lifecycle (run_id, runtime_instance_id, timestamp, model_alias, event_type, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, runtime_instance_id, _now_local(), model_alias, event_type, duration_ms),
            )

    def insert_proxy_request(
        self,
        run_id: str | None,
        endpoint: str,
        model_requested: str | None,
        client_model: str | None,
        resolved_profile: str | None,
        target_model: str | None,
        alias_remapped: int,
        stream: int,
        req_temperature: float | None,
        req_top_p: float | None,
        req_top_k: int | None,
        req_min_p: float | None,
        req_max_tokens: int | None,
        req_enable_thinking: int | None,
        effective_repeat_penalty: float | None,
        client_params: dict | None,
        effective_params: dict | None,
        parameter_changes: dict | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        finish_reason: str | None,
        duration: float,
        ttft: float | None,
        status_code: int,
        injected_params: str | None = None,
    ):
        """Log client intent, Dispatcher resolution, effective request, and response metrics."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO metrics_proxy_requests (
                    machine_id, run_id, timestamp, endpoint, model_requested,
                    client_model, resolved_profile, target_model, alias_remapped, stream,
                    req_temperature, req_top_p, req_top_k, req_min_p, req_max_tokens,
                    req_enable_thinking,
                    effective_temperature, effective_top_p, effective_top_k, effective_min_p,
                    effective_repeat_penalty, effective_max_tokens, effective_enable_thinking,
                    client_params_json, effective_params_json, parameter_changes_json,
                    prompt_tokens, completion_tokens, finish_reason, duration, ttft,
                    status_code, injected_params
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.machine_id, run_id, _now_local(), endpoint, model_requested,
                    client_model, resolved_profile, target_model, alias_remapped, stream,
                    req_temperature, req_top_p, req_top_k, req_min_p, req_max_tokens,
                    req_enable_thinking,
                    req_temperature, req_top_p, req_top_k, req_min_p,
                    effective_repeat_penalty, req_max_tokens, req_enable_thinking,
                    self._json(client_params), self._json(effective_params),
                    self._json(parameter_changes),
                    prompt_tokens, completion_tokens, finish_reason, duration, ttft,
                    status_code, injected_params,
                ),
            )

