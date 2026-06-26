import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any


def _fmt_offset(ts: datetime.datetime) -> str:
    """Formatiert ein timezone-aware datetime als 'YYYY-MM-DD HH:MM:SS+HH:MM'."""
    s = ts.strftime("%Y-%m-%d %H:%M:%S%z")
    # %z liefert '+0200', ISO 8601 braucht '+02:00'
    if len(s) > 19 and s[-5] in ("+", "-") and ":" not in s[-5:]:
        s = s[:-2] + ":" + s[-2:]
    return s


def _now_local() -> str:
    """Lokale Zeit mit korrektem UTC-Offset als DB-Timestamp-String.

    Beispiel: '2026-06-15 09:21:00+02:00'

    SQLite speichert Timestamps als TEXT. Durch den expliziten Offset ist die Zeit
    timezone-aware, korrekt sortierbar und in jedem Viewer sofort lesbar –
    ohne stille UTC-Verschiebung. Der SQL-Standard CURRENT_TIMESTAMP liefert
    immer UTC ohne Markierung, was bei UTC+N-Systemen zu scheinbar falschen Zeiten
    führt.
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
            print(f"[WARNUNG] SQL-Init-Datei {self.sql_file} nicht gefunden. Schema-Erstellung übersprungen.")
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with open(self.sql_file, "r", encoding="utf-8") as f:
                conn.executescript(f.read())

    def _upgrade_schema(self):
        """Fügt fehlende Spalten zu bestehenden Datenbanken hinzu (automatische Schema-Migration)."""
        with sqlite3.connect(self.db_path) as conn:
            # v4 → v5: machine_id in execution_runs
            cols = [row[1] for row in conn.execute("PRAGMA table_info(execution_runs)")]
            if "machine_id" not in cols:
                conn.execute(
                    "ALTER TABLE execution_runs ADD COLUMN machine_id TEXT NOT NULL DEFAULT 'unknown'"
                )
                print("[DB] Schema-Upgrade v4→v5: machine_id-Spalte hinzugefügt.")
            # v5 → v6: injected_params in metrics_proxy_requests (falls Tabelle existiert)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "metrics_proxy_requests" in tables:
                pcols = [row[1] for row in conn.execute("PRAGMA table_info(metrics_proxy_requests)")]
                if "injected_params" not in pcols:
                    conn.execute(
                        "ALTER TABLE metrics_proxy_requests ADD COLUMN injected_params TEXT"
                    )
                    print("[DB] Schema-Upgrade: injected_params-Spalte zu metrics_proxy_requests hinzugefügt.")

    @staticmethod
    def _json(data: Any) -> str:
        return json.dumps(data if data is not None else {}, ensure_ascii=False, sort_keys=True)

    def insert_run(
        self,
        run_id: str,
        mode: str,
        ensemble: str,
        version: str,
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
                    run_id, machine_id, timestamp, tool_mode, ensemble_name, llama_version, cli_command,
                    startup_params, preset_path, preset_content, preset_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    self.machine_id,
                    _now_local(),
                    mode,
                    ensemble,
                    version,
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
        stream: int,
        req_temperature: float | None,
        req_top_p: float | None,
        req_top_k: int | None,
        req_min_p: float | None,
        req_max_tokens: int | None,
        req_enable_thinking: int | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        finish_reason: str | None,
        duration: float,
        ttft: float | None,
        status_code: int,
        injected_params: str | None = None,
    ):
        """Loggt einen proxied Client-Request mit Sampling-Parametern und Response-Stats."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO metrics_proxy_requests (
                    machine_id, run_id, timestamp, endpoint, model_requested, stream,
                    req_temperature, req_top_p, req_top_k, req_min_p, req_max_tokens,
                    req_enable_thinking, prompt_tokens, completion_tokens, finish_reason,
                    duration, ttft, status_code, injected_params
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.machine_id, run_id, _now_local(), endpoint, model_requested, stream,
                    req_temperature, req_top_p, req_top_k, req_min_p, req_max_tokens,
                    req_enable_thinking, prompt_tokens, completion_tokens, finish_reason,
                    duration, ttft, status_code, injected_params,
                ),
            )

