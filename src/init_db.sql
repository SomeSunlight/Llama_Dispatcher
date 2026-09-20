-- Llama Dispatcher metrics schema v8
-- New column machine_id in execution_runs for multi-instance support.
-- Existing v4 databases are migrated via _upgrade_schema() in database_manager.py.
PRAGMA foreign_keys = ON;
PRAGMA user_version = 8;

CREATE TABLE IF NOT EXISTS execution_runs (
    run_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL DEFAULT 'unknown',  -- UUID of the dispatcher instance (from instance.yaml)
    timestamp DATETIME,
    tool_mode TEXT NOT NULL,             -- 'serve', 'bench', 'eval'
    ensemble_name TEXT NOT NULL,         -- ensemble (serve) or profile name (bench/eval)
    llama_version TEXT,
    llama_binary TEXT,                   -- effective binary path actually executed
    cli_command TEXT NOT NULL,           -- main process invocation, reconstructed as-is
    startup_params TEXT NOT NULL,        -- canonicalized startup parameters of the main process
    preset_path TEXT,                    -- router preset, if --models-preset was used
    preset_content TEXT,                 -- exact INI content at runtime
    preset_sha256 TEXT                   -- hash for quick comparison / reproducibility
);

CREATE TABLE IF NOT EXISTS serve_model_instances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    loaded_at DATETIME,
    unloaded_at DATETIME,
    model_alias TEXT NOT NULL,
    child_port INTEGER,
    declared_params TEXT NOT NULL DEFAULT '{}',       -- model section compiled from profile/ensemble
    effective_args TEXT NOT NULL DEFAULT '{}',        -- child server args logged by llama.cpp
    effective_cli_command TEXT,                       -- child invocation reconstructed from log
    meta_json TEXT NOT NULL DEFAULT '{}',             -- cmd_child_to_router:info JSON, if present
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

-- Proxy request log: what clients actually request (parameters, tokens, latency).
-- Populated when clients connect via the dispatcher port (not directly to llama.cpp).
CREATE TABLE IF NOT EXISTS metrics_proxy_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id TEXT NOT NULL DEFAULT 'unknown',
    run_id TEXT,                          -- active execution_runs.run_id, nullable
    timestamp DATETIME,
    endpoint TEXT NOT NULL,               -- e.g. 'chat/completions', 'completions'

    -- Compatibility fields from schema v6. They contain effective values, despite req_* names.
    model_requested TEXT,                 -- effective model sent to llama.cpp (legacy name)
    stream INTEGER NOT NULL DEFAULT 0,    -- 0/1
    req_temperature REAL,
    req_top_p REAL,
    req_top_k INTEGER,
    req_min_p REAL,
    req_max_tokens INTEGER,
    req_enable_thinking INTEGER,

    -- Explicit request-resolution model (schema v7).
    client_model TEXT,                    -- exact public alias sent by the client
    resolved_profile TEXT,                -- Dispatcher profile backing client_model
    target_model TEXT,                    -- effective model alias sent to llama.cpp
    alias_remapped INTEGER,               -- 1 when client_model != target_model

    -- Frequently queried effective values sent to llama.cpp.
    effective_temperature REAL,
    effective_top_p REAL,
    effective_top_k INTEGER,
    effective_min_p REAL,
    effective_repeat_penalty REAL,
    effective_max_tokens INTEGER,
    effective_enable_thinking INTEGER,

    -- Complete prompt-free control-parameter snapshots and transformation details.
    client_params_json TEXT,              -- JSON before Dispatcher transformation
    effective_params_json TEXT,           -- JSON forwarded to llama.cpp
    parameter_changes_json TEXT,          -- JSON diff with source classification

    -- Response statistics extracted from llama.cpp responses.
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    finish_reason TEXT,                   -- stop, length, tool_calls, ...
    duration REAL,                        -- request to last chunk, seconds
    ttft REAL,                            -- time to first token, seconds
    status_code INTEGER,
    injected_params TEXT,                 -- legacy compact JSON of changed policy values
    FOREIGN KEY(run_id) REFERENCES execution_runs(run_id) ON DELETE SET NULL
);


DROP VIEW IF EXISTS v_proxy_request_summary;
CREATE VIEW v_proxy_request_summary AS
SELECT
    id,
    machine_id,
    run_id,
    timestamp,
    endpoint,
    client_model,
    resolved_profile,
    target_model,
    alias_remapped,
    stream,
    effective_enable_thinking AS thinking,
    effective_temperature AS temperature,
    effective_top_p AS top_p,
    effective_top_k AS top_k,
    effective_min_p AS min_p,
    effective_repeat_penalty AS repeat_penalty,
    effective_max_tokens AS max_tokens,
    prompt_tokens,
    completion_tokens,
    finish_reason,
    ttft,
    duration,
    status_code,
    CASE
        WHEN parameter_changes_json IS NULL OR parameter_changes_json = '' THEN 0
        ELSE (SELECT COUNT(*) FROM json_each(parameter_changes_json))
    END AS changed_parameter_count
FROM metrics_proxy_requests;

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
    r.llama_version,
    r.llama_binary,
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
    r.llama_version,
    r.llama_binary,
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
    r.llama_version,
    r.llama_binary,
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
    r.llama_version,
    r.llama_binary,
    json_extract(r.startup_params, '$."ctx-size"') AS ctx_size,
    json_extract(r.startup_params, '$."cache-type-k"') AS quant_k,
    e.dataset,
    e.perplexity,
    e.perplexity_error,
    e.duration
FROM metrics_eval e
JOIN execution_runs r ON e.run_id = r.run_id
ORDER BY r.timestamp DESC;
