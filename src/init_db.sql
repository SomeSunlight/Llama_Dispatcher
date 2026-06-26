-- Llama Dispatcher metrics schema v5
-- Neue Spalte machine_id in execution_runs für multi-Instanz-Unterstützung.
-- Bestehende v4-Datenbanken werden via _upgrade_schema() in database_manager.py migriert.
PRAGMA foreign_keys = ON;
PRAGMA user_version = 5;

CREATE TABLE IF NOT EXISTS execution_runs (
    run_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL DEFAULT 'unknown',  -- UUID der Dispatcher-Instanz (aus instance.yaml)
    timestamp DATETIME,
    tool_mode TEXT NOT NULL,             -- 'serve', 'bench', 'eval'
    ensemble_name TEXT NOT NULL,         -- Ensemble (serve) oder Profil-Name (bench/eval)
    llama_version TEXT,
    cli_command TEXT NOT NULL,           -- Hauptprozess-Aufruf, as-is rekonstruiert
    startup_params TEXT NOT NULL,        -- Kanonisierte Startparameter des Hauptprozesses
    preset_path TEXT,                    -- Router-Preset, falls --models-preset verwendet wurde
    preset_content TEXT,                 -- exakter INI-Inhalt zum Laufzeitpunkt
    preset_sha256 TEXT                   -- Hash für schnellen Vergleich / Reproduzierbarkeit
);

CREATE TABLE IF NOT EXISTS serve_model_instances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    loaded_at DATETIME,
    unloaded_at DATETIME,
    model_alias TEXT NOT NULL,
    child_port INTEGER,
    declared_params TEXT NOT NULL DEFAULT '{}',       -- aus Profil/Ensemble kompilierte Modellsektion
    effective_args TEXT NOT NULL DEFAULT '{}',        -- von llama.cpp geloggte Child-Server-Args
    effective_cli_command TEXT,                       -- Child-Aufruf, aus Log rekonstruiert
    meta_json TEXT NOT NULL DEFAULT '{}',             -- cmd_child_to_router:info JSON, falls vorhanden
    status TEXT NOT NULL DEFAULT 'loaded',            -- loaded, unloaded, evicted, crashed
    FOREIGN KEY(run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_serve_model_instances_run ON serve_model_instances(run_id);
CREATE INDEX IF NOT EXISTS idx_serve_model_instances_alias ON serve_model_instances(run_id, model_alias);
CREATE INDEX IF NOT EXISTS idx_serve_model_instances_port ON serve_model_instances(run_id, child_port);

CREATE TABLE IF NOT EXISTS metrics_bench (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    test_type TEXT NOT NULL,
    ctx_size INTEGER NOT NULL,
    speed REAL NOT NULL,
    speed_error REAL NOT NULL DEFAULT 0.0,
    FOREIGN KEY(run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metrics_eval (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    dataset TEXT NOT NULL,
    perplexity REAL NOT NULL,
    perplexity_error REAL NOT NULL DEFAULT 0.0,
    duration REAL NOT NULL,
    FOREIGN KEY(run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metrics_serve (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    runtime_instance_id INTEGER,
    timestamp DATETIME,
    model_alias TEXT NOT NULL,
    child_port INTEGER,
    slot_id INTEGER,
    task_id INTEGER,
    p_tokens INTEGER NOT NULL,
    g_tokens INTEGER NOT NULL,
    i_speed REAL NOT NULL,
    g_speed REAL NOT NULL,
    duration REAL NOT NULL,
    FOREIGN KEY(run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(runtime_instance_id) REFERENCES serve_model_instances(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_serve_run ON metrics_serve(run_id);
CREATE INDEX IF NOT EXISTS idx_metrics_serve_instance ON metrics_serve(runtime_instance_id);
CREATE INDEX IF NOT EXISTS idx_metrics_serve_task ON metrics_serve(run_id, child_port, task_id);

CREATE TABLE IF NOT EXISTS metrics_lifecycle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    runtime_instance_id INTEGER,
    timestamp DATETIME,
    model_alias TEXT NOT NULL,
    event_type TEXT NOT NULL,            -- load, ready, evict, unload, crash
    duration_ms REAL NOT NULL DEFAULT 0.0,
    FOREIGN KEY(run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(runtime_instance_id) REFERENCES serve_model_instances(id) ON DELETE SET NULL
);

-- Proxy-Request-Log: was Clients tatsächlich anfragen (Parameter, Tokens, Latenz).
-- Wird befüllt wenn Clients über den Dispatcher-Port (nicht direkt an llama.cpp) verbinden.
CREATE TABLE IF NOT EXISTS metrics_proxy_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id TEXT NOT NULL DEFAULT 'unknown',
    run_id TEXT,                          -- aktiver execution_runs.run_id, nullable
    timestamp DATETIME,
    endpoint TEXT NOT NULL,               -- z.B. 'chat/completions', 'completions'
    model_requested TEXT,                 -- was der Client im Feld 'model' schickte
    stream INTEGER NOT NULL DEFAULT 0,    -- 0/1
    -- Vom Client explizit gesendete Sampling-Parameter (NULL = Client hat es nicht gesetzt)
    req_temperature REAL,
    req_top_p REAL,
    req_top_k INTEGER,
    req_min_p REAL,
    req_max_tokens INTEGER,
    req_enable_thinking INTEGER,          -- aus chat_template_kwargs.enable_thinking (0/1)
    -- Antwort-Statistiken (aus Response-Body extrahiert)
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    finish_reason TEXT,                   -- stop, length, tool_calls, …
    duration REAL,                        -- Gesamtdauer Request→letzter Chunk (Sekunden)
    ttft REAL,                            -- Time-to-first-token (Sekunden)
    status_code INTEGER,
    injected_params TEXT,                 -- JSON: Parameter die vom Profil überschrieben wurden
    FOREIGN KEY(run_id) REFERENCES execution_runs(run_id) ON DELETE SET NULL
);

DROP VIEW IF EXISTS v_serve_telemetry;
CREATE VIEW v_serve_telemetry AS
SELECT
    r.machine_id,
    m.timestamp,
    r.ensemble_name,
    m.model_alias,
    CASE
        WHEN json_extract(i.effective_args, '$."model"') IS NULL
            OR json_extract(i.effective_args, '$."model"') = ''
        THEN json_extract(i.effective_args, '$."model"')
        ELSE LTRIM(
            REPLACE(json_extract(i.effective_args, '$."model"'), CHAR(92), CHAR(47)),
            RTRIM(
                REPLACE(json_extract(i.effective_args, '$."model"'), CHAR(92), CHAR(47)),
                REPLACE(
                    REPLACE(json_extract(i.effective_args, '$."model"'), CHAR(92), CHAR(47)),
                    CHAR(47), ''
                )
            )
        )
    END AS model_name,
    json_extract(i.effective_args, '$."n-gpu-layers"') AS n_gpu_layers,
    json_extract(i.effective_args, '$."cache-type-k"') AS cache_type_k,
    json_extract(i.effective_args, '$."cache-type-v"') AS cache_type_v,
    r.startup_params AS startup_params,
    json_extract(i.effective_args, '$."ctx-size"') AS runtime_ctx_size,
    m.p_tokens AS prompt_tokens,
    m.i_speed AS ingest_speed,
    m.g_tokens AS gen_tokens,
    m.g_speed AS gen_speed,
    m.duration,
    json_extract(i.effective_args, '$."parallel"') AS parallel,
    json_extract(i.effective_args, '$."ubatch-size"') AS ubatch_size,
    json_extract(i.effective_args, '$."temperature"') AS runtime_temperature,
    json_extract(i.effective_args, '$."top-p"') AS runtime_top_p,
    json_extract(i.effective_args, '$."top-k"') AS runtime_top_k,
    json_extract(i.effective_args, '$."min-p"') AS runtime_min_p,
    json_extract(i.effective_args, '$."repeat-penalty"') AS runtime_repeat_penalty,
    m.child_port,
    m.slot_id,
    m.task_id,
    i.id AS runtime_instance_id
FROM metrics_serve m
JOIN execution_runs r ON m.run_id = r.run_id
LEFT JOIN serve_model_instances i ON m.runtime_instance_id = i.id
ORDER BY m.timestamp DESC;

DROP VIEW IF EXISTS v_serve_model_instances;
CREATE VIEW v_serve_model_instances AS
SELECT
    i.id,
    r.machine_id,
    i.loaded_at,
    i.unloaded_at,
    r.ensemble_name,
    i.model_alias,
    i.child_port,
    i.status,
    json_extract(i.effective_args, '$."model"') AS model_path,
    json_extract(i.effective_args, '$."ctx-size"') AS ctx_size,
    json_extract(i.effective_args, '$."n-gpu-layers"') AS n_gpu_layers,
    json_extract(i.effective_args, '$."cache-type-k"') AS cache_type_k,
    json_extract(i.effective_args, '$."cache-type-v"') AS cache_type_v,
    json_extract(i.effective_args, '$."temperature"') AS temperature,
    json_extract(i.effective_args, '$."top-p"') AS top_p,
    json_extract(i.effective_args, '$."top-k"') AS top_k,
    json_extract(i.effective_args, '$."min-p"') AS min_p,
    json_extract(i.effective_args, '$."repeat-penalty"') AS repeat_penalty,
    i.declared_params,
    i.effective_args,
    i.meta_json
FROM serve_model_instances i
JOIN execution_runs r ON i.run_id = r.run_id
ORDER BY i.loaded_at DESC;

DROP VIEW IF EXISTS v_router_performance;
CREATE VIEW v_router_performance AS
SELECT
    r.machine_id,
    r.ensemble_name,
    l.model_alias,
    l.event_type,
    COUNT(l.id) AS event_count,
    ROUND(AVG(l.duration_ms)/1000.0, 2) AS avg_duration_sec,
    ROUND(SUM(l.duration_ms)/1000.0, 2) AS total_duration_sec
FROM metrics_lifecycle l
JOIN execution_runs r ON l.run_id = r.run_id
GROUP BY r.machine_id, r.ensemble_name, l.model_alias, l.event_type;

DROP VIEW IF EXISTS v_bench_results;
CREATE VIEW v_bench_results AS
SELECT
    r.machine_id,
    r.timestamp,
    r.ensemble_name AS profile,
    b.test_type,
    b.ctx_size AS test_ctx,
    json_extract(r.startup_params, '$.threads') AS threads,
    json_extract(r.startup_params, '$."cache-type-k"') AS quant_k,
    b.speed,
    b.speed_error,
    r.cli_command
FROM metrics_bench b
JOIN execution_runs r ON b.run_id = r.run_id
ORDER BY r.timestamp DESC, b.ctx_size ASC;

DROP VIEW IF EXISTS v_eval_results;
CREATE VIEW v_eval_results AS
SELECT
    r.machine_id,
    r.timestamp,
    r.ensemble_name AS profile,
    json_extract(r.startup_params, '$."ctx-size"') AS ctx_size,
    json_extract(r.startup_params, '$."cache-type-k"') AS quant_k,
    e.dataset,
    e.perplexity,
    e.perplexity_error,
    e.duration
FROM metrics_eval e
JOIN execution_runs r ON e.run_id = r.run_id
ORDER BY r.timestamp DESC;
