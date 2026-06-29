# Llama Dispatcher

An asynchronous orchestrator and intelligent proxy for `llama.cpp`. The Dispatcher performs two clearly separated tasks:

1. **Manage llama.cpp** – Compiles profiles and ensembles into official llama.cpp parameters, starts the server, and collects metrics.
2. **Act as a Proxy** – Clients see their own model aliases with uniformly set parameters. The Dispatcher receives requests, injects the configured parameters, and forwards them to llama.cpp.

This separation enables: a single model in VRAM, but multiple "personalities" for different clients – centrally configured, not in the client.

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
9. [Debug Endpoints](#9-debug-endpoints)
10. [Serve Modes](#10-serve-modes)
11. [Bench and Eval](#11-bench-and-eval)
12. [Database](#12-database)
13. [CLI Reference](#13-cli-reference)
14. [Parameter Naming System](#14-parameter-naming-system)
15. [Starting – Quick Reference](#15-starting--quick-reference)

---

## 1. Core Idea and Separation of Concerns

The Dispatcher strictly separates what must be together from what must be separate:

| Level | File/Location | Content |
|---|---|---|
| Model Defaults | `defaults/<model>.yaml` | Sampling, hardware-agnostic (e.g., Gemma recommendations) |
| Engine Defaults | `instances/<name>/engines/<engine>.yaml` | Binary path, GPU flags (machine-specific) |
| Profile | `instances/<name>/profiles/<name>.yaml` | Model path, context, quantization, operational parameters |
| Ensemble | `instances/<name>/ensembles/<name>.yaml` | Which models, which aliases, which sampling overrides |
| Dispatcher Code | `src/dispatcher.py` | Compilation, proxy logic, metrics |
| Instance Data | `instances/<name>/data/` | SQLite database (local, not in repo) |

**For operation:** Whoever configures an ensemble only needs to touch the ensemble file. Whoever changes the hardware adjusts the engine file. Whoever changes sampling defaults edits `defaults/<model>.yaml`.

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

Each machine is an **Instance** under `instances/<name>/`. The main Dispatcher code is public on GitHub; instances contain machine paths, model paths, and private data – these do **not** belong in the public repo.

**Solution:** `instances/` is excluded in the main `.gitignore`. Each instance is its **own private Git repo**:

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

After cloning, check `instance.yaml`: the `machine_guid` uniquely identifies the machine
in the metrics database. On a new device, enter a new GUID or use `--instance NewName`
to create a fresh instance (created automatically).

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

```bash
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop
```

With `--instance Laptop`, the Dispatcher points to `instances/Laptop/profiles|ensembles|data/`
and reads the `machine_guid` from `instances/Laptop/instance.yaml`.

**Without `--instance`**, the Dispatcher runs in **Legacy Mode**: it searches for profiles and ensembles
directly under `profiles/` and `ensembles/` in the project root – **no prompt**, no error, just
the wrong path. Anyone using the instance structure must always specify `--instance`.

If the specified instance does not exist yet, the Dispatcher creates it automatically
(empty directories, new `machine_guid` in `instance.yaml`).

---

## 4. Configuration Cascade

When loading a profile, four layers are merged (**deep merge**, later layers overwrite earlier ones):

```
defaults/<model>.yaml               (1. Model Defaults: Sampling, hardware-agnostic)
        ↓ deep-merge
instances/<name>/engines/<engine>.yaml (2. Engine Defaults: bin_dir, GPU flags)
        ↓ deep-merge
instances/<name>/profiles/<name>.yaml  (3. Profile: Model path, context, operational parameters)
        ↓ deep-merge (inline, highest priority)
Ensemble Model Entry                (4. Ensemble: Alias, Sampling overrides, load-on-startup)
```

The profile explicitly references layers 1 and 2:
```yaml
defaults:
  model: "gemma"    # → defaults/gemma.yaml
  engine: "vulkan"  # → instances/Laptop/engines/vulkan.yaml
```

**Consequence:** Sampling defaults exist exactly once in `defaults/gemma.yaml`. Vulkan-specific flags exist exactly once in `engines/vulkan.yaml`. The profile only contains what is truly model-specific.

---

## 5. Profile Structure

Profiles describe a model on specific hardware. They have three operational mode sections (`serve`, `bench`, `eval`) and one common section (`common`).

```yaml
# instances/Laptop/profiles/Thinkpad_vulkan_gemma_26B_A4B.yaml
name: "Thinkpad_vulkan_gemma_26B_A4B"
description: "Gemma 4 26B QAT, Vulkan build, reduced context"

defaults:
  model: "gemma"    # → defaults/gemma.yaml  (Sampling Defaults)
  engine: "vulkan"  # → instances/Laptop/engines/vulkan.yaml  (bin_dir, GPU flags)

common:
  m: "C:\\AI_Models\\gemma-4-26B.gguf"
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

Engine files separate what is binary/hardware-specific from the model. They are embedded into the `common:` and `serve:` sections of the profile via **deep merge**.

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

Search order: `instances/<name>/engines/` → `defaults/engine-templates/` (fallback).

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
| `defaults.engine` | Reads `bin_dir` from the instance engine file |
| `dispatcher.port` | Port of the Dispatcher-Proxy (clients) |
| `engine.port` | Port of llama.cpp (internal) |
| `target: "alias"` | Proxy-only: no INI entry, rewritten to target alias |
| `chat_template_kwargs` | Injected by the Proxy into every request (e.g., `enable_thinking`) |
| `sampling:` | Sampling parameters that the Proxy injects and overrides |

---

## 8. The Proxy – Model Aliases and Parameter Injection

The Dispatcher is a **full OpenAI-compatible Proxy**. Clients point to `http://<host>:8001/v1/` instead of directly to llama.cpp.

### What the Proxy does

For every incoming request:

1. **Alias Lookup**: Finds the configured parameters for the requested model (`model: "agent"`)
2. **Sampling Injection**: Injects `temperature`, `top_p`, `top_k`, `min_p`, `repeat_penalty`, `chat_template_kwargs` – **Proxy values always overwrite client values**
3. **Alias Remapping** (with `target:`): Rewrites `model: "agent"` → `model: "Sparringpartner"`
4. **Forwarding** to llama.cpp (Port 8081)
5. **Logging**: Endpoint, model, tokens, latency, TTFT in SQLite

### What Clients See

```
GET http://localhost:8001/v1/models
→ ["Sparringpartner", "agent"]   ← both visible, one model in VRAM
```

### Data Flow

```
Open WebUI / Goose / curl
  POST /v1/chat/completions  { "model": "agent", "temperature": 0.9, ... }
        ↓
Dispatcher (Port 8001):
  → Load sampling for "agent": temp=0.3, top_k=20, enable_thinking=false
  → temperature: 0.9 → 0.3  (Proxy overwrites)
  → model: "agent" → "Sparringpartner"  (Remapping)
  → Forwarding: { "model": "Sparringpartner", "temperature": 0.3, ... }
        ↓
llama.cpp (Port 8081): knows only [Sparringpartner] – one model, no swaps
```

### Why this makes sense

- **Consistency**: All clients receive the same parameters, regardless of what they send
- **VRAM Efficiency**: Multiple aliases, one model – no constant loading/unloading
- **Centralized Configuration**: Thinking on/off, sampling mode – all in the ensemble file, not in the client

---

## 9. Debug Endpoints

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

## 10. Serve Modes

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

## 11. Bench and Eval

```bash
uv run src/dispatcher.py bench --profile Thinkpad_vulkan_gemma_26B_A4B --instance Laptop
uv run src/dispatcher.py eval  --profile Thinkpad_vulkan_gemma_26B_A4B --instance Laptop \
    --dataset data/wikitext-2-raw.txt
```

`MAX_CONTEXT` in `bench.pg` is calculated at runtime as `ctx-size - tg`.

---

## 12. Database

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

## 13. CLI Reference

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

## 14. Parameter Naming System

### The Problem

YAML does not forbid underscores in keys, but llama.cpp uses dashes (`--ctx-size`, `--cache-type-k`). On top of that, there are short and long forms (`-c` vs. `--ctx-size`). The ensemble/profile can come from three sources (Defaults, Engine, Profile), each of which might use different conventions. Without clear rules, typos are silent and ineffective.

### The Solution: Canonicalization

The Dispatcher normalizes **every** key upon reading to its **canonical form**:
→ Dashes, long form, without leading dashes.

Canonicalization steps (in order):
1. Remove leading `-` or `--`
2. Replace all `_` with `-`
3. Translate short form to long form (via `PARAM_MAPPING`)

**Result:** `top_k`, `top-k`, `-tk` (if defined) – all become `top-k`.

### Recommendation for YAMLs

**Use dashes.** The Dispatcher accepts both, but dashes correspond to the llama.cpp standard and are what you see in `debug/config` and the database.

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

## 15. Starting – Quick Reference

```bash
# Start Ensemble (Proxy + llama.cpp)
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop
uv run src/dispatcher.py serve --ensemble 3090    --instance Speedy

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