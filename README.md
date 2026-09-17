# Llama Dispatcher

An asynchronous orchestrator and OpenAI-compatible proxy for `llama.cpp`. It compiles configured profiles and ensembles, runs llama.cpp, and exposes centrally managed client aliases through the Dispatcher proxy.

> **Important:** Clients connect to the Dispatcher proxy, not directly to llama.cpp. Exact defaults and the canonical proxy/port rules are maintained in [Project Context](CONTEXT.md).

---

## Table of Contents

1. [Core Idea and Separation of Concerns](#1-core-idea-and-separation-of-concerns)
2. [Directory Structure](#2-directory-structure)
3. [Instance Concept and Git Separation](#3-instance-concept-and-git-separation)
4. [Configuration Cascade](#4-configuration-cascade)
5. [Profile Structure](#5-profile-structure)
6. [Engine Templates and Instance Engines](#6-engine-templates-and-instance-engines)
7. [Ensemble Structure](#7-ensemble-structure)
8. [The Proxy – Model Aliases and Parameter Injection](#8-the-proxy--model-aliases-and-parameter-injection)
9. [⚠️ Port Overview – Do Not Mix Up These Two Ports!](#9-️-port-overview--do-not-mix-up-these-two-ports)
10. [Debug Endpoints](#10-debug-endpoints)
11. [Serve Modes](#11-serve-modes)
12. [Bench and Eval](#12-bench-and-eval)
13. [Database](#13-database)
14. [CLI Reference](#14-cli-reference)
15. [Parameter Naming System](#15-parameter-naming-system)
16. [Starting – Quick Reference](#16-starting--quick-reference)

---

## 1. Core Idea and Separation of Concerns

The project separates shared model defaults, machine-specific instance configuration, Dispatcher code, and local instance data. Change the layer that owns the concern; the canonical ownership rules are maintained in [Project Context](CONTEXT.md).
---

## 2. Directory Structure

```
Llama_Dispatcher/
├── src/
│   └── dispatcher.py          # Orchestrator + Proxy + API
├── defaults/
│   ├── gemma.yaml             # Gemma Sampling Defaults (serve section)
│   ├── llama.yaml             # Llama Sampling Defaults
│   ├── qwen.yaml              # Qwen Sampling Defaults
│   └── engine-templates/      # Templates to copy to instances/<name>/engines/
│       ├── cuda.yaml
│       ├── vulkan.yaml
│       └── sycl.yaml
├── instances/                 # NOT in the main repo (separate private Git)
│   ├── Laptop/
│   │   ├── instance.yaml      # machine_guid, nickname
│   │   ├── engines/
│   │   │   └── vulkan.yaml    # bin_dir + GPU flags for this machine
│   │   ├── ensembles/
│   │   │   └── thinkpad.yaml
│   │   ├── profiles/
│   │   │   └── Thinkpad_vulkan_gemma_26B_A4B.yaml
│   │   └── data/
│   │       └── metrics.db     # SQLite (not versioned)
│   └── Speedy/
│       ├── instance.yaml
│       ├── engines/
│       │   └── cuda.yaml
│       ├── ensembles/
│       │   └── 3090.yaml
│       ├── profiles/
│       └── data/
└── pyproject.toml
```

---

## 3. Instance Concept and Git Separation

Each machine has a private instance under `instances/<name>/`; machine-specific paths and operational data do not belong in the public Dispatcher repository. The canonical repository boundary is maintained in [Project Context](CONTEXT.md).
| Repo | Visibility | Content |
|---|---|---|
| `SomeSunlight/Llama_Dispatcher` | Public | Code, Defaults, Documentation |
| `SomeSunlight/Llama_Dispatcher_Laptop` | Private | Laptop profiles, Engines, Ensembles |
| `SomeSunlight/Llama_Dispatcher_Speedy` | Private | Speedy profiles, Engines, Ensembles |

### Fresh Install on a New Machine

The trick when cloning: `git clone <url> <target_directory>` allows a custom folder name –
so the instance lands directly in the correct subdirectory without the GitHub repo name interfering.

```powershell
# Step 1: Clone main repo
git clone https://github.com/SomeSunlight/Llama_Dispatcher.git
cd Llama_Dispatcher

# Step 2: Clone instance repos into the EXACT correct subdirectories
git clone https://github.com/SomeSunlight/Llama_Dispatcher_Laptop.git instances/Laptop
git clone https://github.com/SomeSunlight/Llama_Dispatcher_Speedy.git instances/Speedy

# Step 3: Python environment
uv sync
```

For one instance that is shared between Windows and WSL, keep machine-local paths out of the profile files. Use `${LLAMA_MODEL_ROOT}` for the common model directory and pass the concrete runtime paths when starting Dispatcher:

```yaml
common:
  m: "${LLAMA_MODEL_ROOT}/gemma-4-26B.gguf"
```

```powershell
# Windows example
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop `
  --bin-dir 'C:\llama.cpp\server\server_07_SYCL' `
  --model-root 'C:\AI_Models\LLM\GGUF_Raw'
```

```bash
# WSL/Linux example
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop \
  --bin-dir /home/user/.local/share/ai-workstation/local-inference/llama.cpp/builds/sycl-<commit>/build/bin \
  --model-root /mnt/c/AI_Models/LLM/GGUF_Raw
```

`--bin-dir` and `--model-root` are explicit process-local overrides; they do not rewrite the instance repository. `--model-root` has precedence over the optional `LLAMA_MODEL_ROOT` environment fallback. If a configuration uses `${LLAMA_MODEL_ROOT}` and neither source is available, Dispatcher stops with a clear error instead of launching with an unresolved path. The environment variable is therefore a convenience for manual workflows, not a required hidden prerequisite.

`instance.yaml` instance.yaml carries the machine identity used by metrics. If a requested instance does not exist, the Dispatcher currently creates the instance and assigns a new machine_guid automatically. Canonical identity and current creation behavior are maintained in [Project Context](CONTEXT.md). (To clarify, if in case of a unknown instance it would be better to stop, or to assist creating a new identity explicitly.)

### Daily Workflow after Configuration Changes

```bash
# Backup Laptop instance
cd instances/Laptop
git add .
git commit -m "thinkpad: new agent alias configured"
git push

# Backup Speedy instance
cd instances/Speedy
git add .
git commit -m "3090: context increased"
git push
```

### What `--instance` does

When using the instance layout, pass `--instance`; omitting it selects the legacy root-level lookup mode. A missing requested instance is currently created automatically. Canonical behavior and current state are maintained in [Project Context](CONTEXT.md).

---

## 4. Configuration Cascade

Configuration is layered from model defaults through the instance engine and profile to the ensemble entry; later layers override earlier ones. Profiles explicitly reference their model and engine defaults, and ad-hoc CLI overrides sit above the cascade. Machine-local launch paths supplied by `--bin-dir` and `--model-root` are process-level runtime inputs and do not become persisted profile configuration. The canonical ownership and precedence rules are maintained in [Project Context](CONTEXT.md).
---

## 5. Profile Structure

Profiles describe a model on specific hardware. They have three operational mode sections (`serve`, `bench`, `eval`) and one common section (`common`). Portable profiles may use `${LLAMA_MODEL_ROOT}` rather than embedding an operating-system-specific absolute model directory.

```yaml
# instances/Laptop/profiles/Thinkpad_vulkan_gemma_26B_A4B.yaml
name: "Thinkpad_vulkan_gemma_26B_A4B"
description: "Gemma 4 26B QAT, Vulkan build, reduced context"

defaults:
  model: "gemma"    # → defaults/gemma.yaml  (Sampling Defaults)
  engine: "vulkan"  # → instances/Laptop/engines/vulkan.yaml  (bin_dir, GPU flags)

common:
  m: "${LLAMA_MODEL_ROOT}/gemma-4-26B.gguf"
  c: 16384
  threads: 1
  cache-type-k: "q4_0"
  cache-type-v: "q4_0"

serve:
  ubatch-size: 2048
  batch-size: 2048
  parallel: 1
  cont-batching: true
  jinja: true       # Required for Gemma 4
  port: 8081        # Fallback if not defined in Ensemble
  host: "0.0.0.0"
  ctx-checkpoints: 0
  # no-kv-offload and cache-ram come from engines/vulkan.yaml

bench:
  r: 1
  pg:
    - [512, 128]
    - [16384, 128]
    - ["MAX_CONTEXT", 128]

eval:
  c: 8192
  b: 512
  ot: null   # removes the override-tensor flag for Perplexity
```

**Shorthands** are canonized: `m` → `model`, `c` → `ctx-size`, `ngl` → `n-gpu-layers`, `ctk` → `cache-type-k`, `ot` → `override-tensor`.

---

## 6. Engine Templates and Instance Engines

Engine files separate what is binary/hardware-specific from the model. They are embedded into the `common:` and `serve:` sections of the profile via **deep merge**. A standalone instance may keep a `bin_dir` fallback in its engine file, but launchers that manage llama.cpp builds should pass `--bin-dir` explicitly so the same instance can run unchanged on multiple operating systems.

**Template** (Template under `defaults/engine-templates/`):
```yaml
# defaults/engine-templates/vulkan.yaml  – ONLY a template, not used directly
bin_dir: "c:\\llama-cpp\\server\\server_vulkan"
```

**Instance-specific Engine** (Adjust after copying the template):
```yaml
# instances/Laptop/engines/vulkan.yaml
bin_dir: "c:\\llama.cpp\\server\\server_06_vulcan"

common:
  n-gpu-layers: 99   # all layers on GPU
  split-mode: none   # no Multi-GPU
  main-gpu: 0
  flash-attn: on

serve:
  no-kv-offload: true  # Vulkan does not support KV-offloading
  cache-ram: 0         # prevents Vulkan-specific crashes
```

Search order: `instances/<name>/engines/` → `defaults/engine-templates/` (fallback). An explicit `--bin-dir` overrides the resulting binary directory only for the current process.

---

## 7. Ensemble Structure

Ensembles define which models are offered together in the llama.cpp router, and which model aliases the **Proxy** makes visible to the outside.

```yaml
# instances/Laptop/ensembles/thinkpad.yaml

defaults:
  engine: "vulkan"   # → instances/Laptop/engines/vulkan.yaml  (for bin_dir)

dispatcher:
  port: 8001         # Dispatcher-Proxy port (clients point here)

engine:
  port: 8081         # llama.cpp-server port (internal, Dispatcher forwards there)
  host: "0.0.0.0"
  models_max: 1

models:
  # Real llama.cpp model (occupies VRAM)
  - profile: "Thinkpad_vulkan_gemma_26B_A4B"
    alias: "Sparringpartner"
    load-on-startup: true
    chat_template_kwargs:
      enable_thinking: true

  # Proxy-only Alias: no VRAM, forwards to "Sparringpartner"
  - profile: "Thinkpad_vulkan_gemma_26B_A4B"
    alias: "agent"
    target: "Sparringpartner"
    chat_template_kwargs:
      enable_thinking: false
    sampling:
      temperature: 0.3
      top_k: 20
      top_p: 0.9
      min_p: 0.1
      repeat_penalty: 1.1
```

**Key Concepts:**

| Field | Meaning |
|---|---|
| `defaults.engine` | Reads `bin_dir` from the instance engine file unless `--bin-dir` overrides it for this process |
| `dispatcher.port` | Port of the Dispatcher-Proxy (clients) |
| `engine.port` | Port of llama.cpp (internal) |
| `target: "alias"` | Proxy-only: no INI entry, rewritten to target alias |
| `chat_template_kwargs` | Injected by the Proxy into every request (e.g., `enable_thinking`) |
| `sampling:` | Sampling parameters that the Proxy injects and overrides |

---

## 8. The Proxy – Model Aliases, Parameter Resolution, and Logging

The Dispatcher is the client-facing OpenAI-compatible proxy. It resolves each public alias to its backing profile and optional target model, enforces configured policy, and forwards unmanaged request fields unchanged. It distinguishes client parameters, compiled Dispatcher policy parameters, and the effective parameters sent to llama.cpp.

The canonical request-state vocabulary, precedence rules, and current provenance limitation are maintained in [Project Context](CONTEXT.md). The flow below remains the operational illustration.

### Configuration and request flow

```text
                         CONFIGURATION SOURCES

  defaults/<model>.yaml     instance engine      profile YAML      ensemble entry
  (model defaults)          (engine defaults)    (model/mode)      (alias overrides)
          \                      |                    |                  /
           \_____________________|____________________|_________________/
                                  |
                                  v
                    Dispatcher compiles alias policy
                    - public alias -> resolved profile
                    - public alias -> sampling policy
                    - optional public alias -> target alias
                                  |
                                  |
CLIENTS                           |                         llama.cpp
Open WebUI / Goose / curl         |                         internal server
                                  |
POST /v1/chat/completions         |
{                                 |
  "model": "agent",             |
  "temperature": 0.9,            |
  "max_tokens": 4096             |
} ------------------------------> Dispatcher
                                  | 1. preserve client snapshot
                                  | 2. resolve profile for "agent"
                                  | 3. overwrite configured values
                                  |    temperature: 0.9 -> 0.3
                                  | 4. pass through unmanaged values
                                  |    max_tokens: 4096
                                  | 5. remap model when target is set
                                  |    agent -> Sparringpartner
                                  | 6. preserve effective snapshot + diff
                                  v
                         POST /v1/chat/completions
                         {
                           "model": "Sparringpartner",
                           "temperature": 0.3,
                           "max_tokens": 4096
                         } ---------------------------> llama.cpp
```

### Resolution rules

Request handling preserves client intent, resolves the alias/profile, applies configured policy, passes unmanaged fields through, performs optional target remapping, forwards the effective request, and logs the transformation. `chat_template_kwargs` is enforced as one whole policy object rather than recursively merged. Canonical semantics are maintained in [Project Context](CONTEXT.md).
### What clients see

```text
GET http://localhost:8001/v1/models
-> ["Sparringpartner", "agent"]   # both visible, one model in VRAM
```

### Proxy request logging

`metrics_proxy_requests` keeps compatibility with the older schema while adding an
explicit v7 model. Historical `req_*` fields were already populated **after**
Dispatcher transformation; despite their names, they contain effective values. They
remain available for existing queries. New code also writes clearly named fields:

| Field group | Purpose |
|---|---|
| `client_model`, `resolved_profile`, `target_model`, `alias_remapped` | Request routing at a glance |
| `effective_*` | Frequently queried values that actually reached llama.cpp |
| `client_params_json` | Complete client control parameters before transformation |
| `effective_params_json` | Complete control parameters forwarded to llama.cpp |
| `parameter_changes_json` | Changed values with `client`, `effective`, and `source` |

The JSON snapshots exclude `messages`, `prompt`, and `input`. They record request
control parameters without duplicating conversation or prompt content in telemetry.
Unknown or future parameters remain visible in JSON without requiring a schema change.

Example transformation record:

```json
{
  "model": {
    "client": "agent",
    "effective": "Sparringpartner",
    "source": "alias_target"
  },
  "temperature": {
    "client": 0.9,
    "effective": 0.3,
    "source": "dispatcher_policy",
    "configured_for": "agent",
    "resolved_profile": "3090_gemma_fast_top_quality_workhorse_2x131k_q8"
  }
}
```

For the normal operational overview:

```sql
SELECT *
FROM v_proxy_request_summary
ORDER BY timestamp DESC;
```

Existing databases are upgraded additively. Historical effective values are copied
from the legacy fields where their meaning is certain. Historical client aliases,
client snapshots, and exact parameter provenance remain `NULL` because they were not
recorded and must not be invented.

### Why this design makes sense

- **Consistency**: all clients use the same centrally managed policy.
- **VRAM efficiency**: multiple public aliases can share one loaded target model.
- **Transparent telemetry**: SQL shows what the client selected and what actually ran.
- **Forward compatibility**: arbitrary parameters remain available in JSON snapshots.

---

## 9. ⚠️ Port Overview – Do Not Mix Up These Two Ports!

| Endpoint | Use |
|---|---|
| Dispatcher proxy | Client-facing API; aliases and Dispatcher policy are active |
| llama.cpp server | Internal inference endpoint used by the Dispatcher |

Point clients at the configured Dispatcher proxy endpoint. Direct llama.cpp access can appear to work while silently bypassing Dispatcher features. The proxy itself has no browser UI.

For a first check, query `/v1/models` on the configured proxy endpoint: it should show all configured aliases. Use a simple API client such as curl or a minimal Python script before debugging through a full UI; Open WebUI is better treated as a later integration check. Connect directly to llama.cpp only when bypassing Dispatcher features is intentional. Exact default ports and current runtime limitations are maintained in [Project Context](CONTEXT.md).

---

## 10. Debug Endpoints

While the Dispatcher is running, two debug endpoints are available:

### `GET /debug/config`

Shows the current proxy configuration:

```bash
curl http://localhost:8001/debug/config
```

Response:
```json
{
  "status": "running",
  "llama_port": 8081,
  "aliases": [
    {
      "alias": "Sparringpartner",
      "type": "real",
      "target": null,
      "injected_params": {"temperature": 1.0, "chat_template_kwargs": {"enable_thinking": true}}
    },
    {
      "alias": "agent",
      "type": "proxy-only",
      "target": "Sparringpartner",
      "injected_params": {"temperature": 0.3, "chat_template_kwargs": {"enable_thinking": false}}
    }
  ]
}
```

### `POST /debug/preview`

Simulates the proxy transformation **without forwarding** – ideal for testing before an actual start:

```bash
curl http://localhost:8001/debug/preview \
  -H "Content-Type: application/json" \
  -d '{"model":"agent","messages":[{"role":"user","content":"Hello"}],"temperature":0.9}'
```

Response shows:
- `original_model` vs. `forwarded_model`
- `injected_params`: what was injected and what the client sent
- `overridden_by_client`: what the client wanted but was overwritten
- `forwarded_body`: the full body that would go to llama.cpp

### Compile-only (without starting the server)

```bash
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop --compile-only
```

Shows the generated INI and the llama.cpp start command, but starts nothing.

---

## 11. Serve Modes

### Ensemble Mode (Standard for operation)

```bash
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop
```

Workflow:
1. Reads `instances/Laptop/ensembles/thinkpad.yaml`
2. Loads profiles, merges Engine Defaults and Model Defaults (Cascade)
3. Writes `instances/Laptop/data/thinkpad_models.ini`
4. Starts llama.cpp: `llama-server --models-preset thinkpad_models.ini ...`
5. Starts Dispatcher-Proxy on Port 8001

The Dispatcher port is read from `ensemble.dispatcher.port`; `--api-port` on the CLI overrides it.

### Single Profile Mode (for testing and fine-tuning)

```bash
uv run src/dispatcher.py serve --profile Thinkpad_vulkan_gemma_26B_A4B --instance Laptop
```

Starts llama.cpp directly from the profile, without the router-INI. No proxy aliasing.

---

## 12. Bench and Eval

```bash
uv run src/dispatcher.py bench --profile Thinkpad_vulkan_gemma_26B_A4B --instance Laptop
uv run src/dispatcher.py eval  --profile Thinkpad_vulkan_gemma_26B_A4B --instance Laptop \
    --dataset data/wikitext-2-raw.txt
```

`MAX_CONTEXT` in `bench.pg` is calculated at runtime as `ctx-size - tg`.

---

## 13. Database

Per instance: `instances/<name>/data/metrics.db` (not versioned).

### Tables

| Table | Content |
|---|---|
| `execution_runs` | One entry per server start (Ensemble/Profile, Version, CLI, INI-Hash) |
| `serve_model_instances` | One instance per loaded model (declared + effective parameters) |
| `metrics_serve` | One entry per completed request (Tokens, Speed, TTFT, Sampling-Params) |
| `metrics_lifecycle` | Load/Evict/Unload events |
| `metrics_bench` | Benchmark results with error bars |
| `metrics_eval` | Perplexity results |
| `proxy_requests` | Proxy log: Endpoint, model, injected params, tokens, latency, TTFT |

### Timestamps

All timestamps are timezone-aware: `YYYY-MM-DD HH:MM:SS+HH:MM` (local time with UTC offset). Sortable, directly readable in DB viewers.

### Views

- `v_serve_telemetry` – Request timings with runtime context
- `v_serve_model_instances` – Loaded model instances with effective args
- `v_router_performance` – Aggregated lifecycle events
- `v_bench_results` / `v_eval_results` – Measurement results

---

## 14. CLI Reference

### Usage Syntax

```bash
uv run src/dispatcher.py <mode> [options] [llama.cpp-overrides...]
```

### Modes (Required argument)

| Mode | Description |
|---|---|
| `serve` | Starts llama.cpp + Dispatcher-Proxy. Requires `--ensemble` **or** `--profile` |
| `bench` | Benchmark (pp/tg speed). Requires `--profile` |
| `eval` | Perplexity measurement. Requires `--profile` and `--dataset` |

### Options

| Option | Default | Description |
|---|---|---|
| `--ensemble NAME` | – | Name of the ensemble YAML (without `.yaml`). For `serve` in router mode with proxy |
| `--profile NAME` | – | Name of the profile YAML (without `.yaml`). For `serve` single model, `bench`, `eval` |
| `--instance NAME` | – | Instance name (folder under `instances/`). **Without this parameter, the Dispatcher runs in Legacy Mode** and searches for profiles/ensembles in the project root. No prompt. |
| `--api-port PORT` | from Ensemble or `8001` | Port of the Dispatcher-Proxy. Overrides `dispatcher.port` in the ensemble YAML |
| `--dataset PATH` | `data/wikitext-2-raw.txt` | Text file for `eval` (Perplexity) |
| `--compile-only` | – | Compiles INI and shows the llama.cpp start command, but starts nothing |
| `--bin-dir PATH` | Engine/profile `bin_dir` | Process-local llama.cpp binary directory. Explicit CLI value overrides persisted engine/profile paths |
| `--model-root PATH` | `LLAMA_MODEL_ROOT` environment fallback | Expands `${LLAMA_MODEL_ROOT}` in portable YAML paths. CLI takes precedence over the optional environment fallback |

### Ad-hoc llama.cpp Overrides

**All** llama.cpp parameters can be passed directly via the CLI – they overwrite the profile/ensemble with the highest priority. The Dispatcher automatically recognizes and canonizes all spellings (short, long, dash or underscore):

```bash
# Limit context to 8192 (for quick tests)
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop --ctx-size 8192

# Overwrite parallelism and threads
uv run src/dispatcher.py bench --profile Thinkpad_vulkan_gemma_26B_A4B --instance Laptop \
    --parallel 2 --threads 8

# Overwrite sampling for this start
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop \
    --temperature 0.5 --top-k 40
```

Boolean flags are accepted as `true`/`false` or as a bare flag:
```bash
--flash-attn true   # explicit
--flash-attn        # equivalent (flag without value = true)
--no-kv-offload     # negating prefix for switches
```

---

## 15. Parameter Naming System

### The Problem

YAML does not forbid underscores in keys, but llama.cpp uses dashes (`--ctx-size`, `--cache-type-k`). On top of that, there are short and long forms (`-c` vs. `--ctx-size`). The ensemble/profile can come from three sources (Defaults, Engine, Profile), each of which might use different conventions. Without clear rules, typos are silent and ineffective.

### The Solution: Canonicalization

The Dispatcher normalizes parameter keys to one canonical form before use. Use dashed llama.cpp-style keys in YAML; alternate spellings remain accepted and normalized. Canonical naming rules are maintained in [Project Context](CONTEXT.md).

```yaml
# ✅ Preferred
cache-type-k: "q8_0"
flash-attn: true

# ✅ Works (will be canonized to the above)
cache_type_k: "q8_0"
flash_attn: true

# ✅ Shorthand in common:/serve: works
ngl: 99    # → n-gpu-layers
c: 65536   # → ctx-size
```

### Group Keys (YAML only, not to llama.cpp)

These keys do not exist in llama.cpp – they are YAML comfort wrappers. Their content is flattened before canonicalization:

```yaml
# The content is packed directly into the parameter list
sampling:
  temperature: 1.0
  top-k: 64
  top-p: 0.95

# Equivalent to:
temperature: 1.0
top-k: 64
top-p: 0.95
```

Valid group keys: `sampling`, `sampler`, `generation`, `defaults`

### Full Shorthand Table (PARAM_MAPPING)

| Shorthand / Alias | Canonical Long Form |
|---|---|
| `c`, `ctx`, `context` | `ctx-size` |
| `b` | `batch-size` |
| `ub` | `ubatch-size` |
| `t` | `threads` |
| `ngl` | `n-gpu-layers` |
| `fa` | `flash-attn` |
| `ctk` | `cache-type-k` |
| `ctv` | `cache-type-v` |
| `ot`, `override_tensor`, `override-tensors` | `override-tensor` |
| `m` | `model` |
| `temp` | `temperature` |
| `top_k` | `top-k` |
| `top_p` | `top-p` |
| `min_p` | `min-p` |
| `repeat_penalty` | `repeat-penalty` |
| `repeat_last_n` | `repeat-last-n` |
| `presence_penalty` | `presence-penalty` |
| `frequency_penalty` | `frequency-penalty` |
| `typical_p`, `typ_p` | `typical-p` |
| `dynatemp_range` | `dynatemp-range` |
| `dynatemp_exp`, `dynatemp_exponent` | `dynatemp-exp` |
| `mirostat_lr` | `mirostat-lr` |
| `mirostat_ent` | `mirostat-ent` |
| `dry_multiplier` | `dry-multiplier` |
| `dry_base` | `dry-base` |
| `dry_allowed_length` | `dry-allowed-length` |
| `dry_penalty_last_n` | `dry-penalty-last-n` |
| `dry_sequence_breaker` | `dry-sequence-breaker` |
| `sampler_seq` | `sampler-seq` |
| `sampling_seq` | `sampling-seq` |
| `hf_repo` | `hf-repo` |
| `hf_file` | `hf-file` |
| `model_url` | `model-url` |
| `model_draft` | `model-draft` |
| `chat_template` | `chat-template` |
| `load_on_startup` | `load-on-startup` |
| `api_key` | `api-key` |

> All other keys: `_` → `-` is sufficient. `cache_type_k` → `cache-type-k` automatically.

### What happens to incoming request parameters (Proxy)

If a client sends `temperature: 0.9` and the ensemble has `temperature: 0.3` configured,
**the Proxy always overwrites the client value**. This is intended.

The sampling parameters managed (and potentially overwritten) by the Proxy are:

`temperature`, `top-p`, `top-k`, `min-p`, `repeat-penalty`, `presence-penalty`,
`frequency-penalty`, `typical-p`, `dynatemp-range`, `dynatemp-exp`, `mirostat-lr`,
`mirostat-ent`, `dry-multiplier`, `dry-base`, `dry-allowed-length`, `dry-penalty-last-n`,
`sampler-seq`, `repeat-last-n`

**In the database**, they are stored in canonical form (dashes).
**In the JSON body** sent to llama.cpp, they are written with underscores (`top_k`, `temperature`) – this is what the OpenAI-compatible llama.cpp API expects.

`chat_template_kwargs` is a special case: it is injected as a Proxy parameter,
but does not appear in the llama.cpp-INI.

---

## 16. Starting – Quick Reference

```bash
# Start Ensemble (Proxy + llama.cpp)
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop
uv run src/dispatcher.py serve --ensemble 3090    --instance Speedy

# Portable Windows/WSL start when runtime paths differ
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop \
  --bin-dir /path/to/llama.cpp/build/bin \
  --model-root /path/to/shared/models

# Compile only, do not start
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop --compile-only

# Check proxy configuration (during operation)
curl http://localhost:8001/debug/config

# Simulate request transformation (during operation)
curl http://localhost:8001/debug/preview \
  -H "Content-Type: application/json" \
  -d '{"model":"agent","messages":[{"role":"user","content":"test"}], "temperature":0.9}'

# See models (like Open WebUI)
curl http://localhost:8001/v1/models

# Backup instance (Laptop)
cd instances/Laptop && git add . && git commit -m "Update" && git push

# Fresh Install on a new machine (all 3 repos in one go)
git clone https://github.com/SomeSunlight/Llama_Dispatcher.git
cd Llama_Dispatcher
git clone https://github.com/SomeSunlight/Llama_Dispatcher_Laptop.git instances/Laptop
git clone https://github.com/SomeSunlight/Llama_Dispatcher_Speedy.git instances/Speedy
uv sync
```