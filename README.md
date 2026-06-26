# Llama Dispatcher

Ein asynchroner Orchestrator und intelligenter Proxy für `llama.cpp`. Der Dispatcher übernimmt zwei klar getrennte Aufgaben:

1. **llama.cpp verwalten** – Profile und Ensembles zu offiziellen llama.cpp-Parametern kompilieren, den Server starten, Metriken erfassen.
2. **Als Proxy agieren** – Clients sehen eigene Modell-Aliase mit einheitlich gesetzten Parametern. Der Dispatcher nimmt Anfragen entgegen, injiziert die konfigurierten Parameter und leitet an llama.cpp weiter.

Diese Trennung ermöglicht: ein einziges Modell im VRAM, aber mehrere „Persönlichkeiten" für verschiedene Clients – zentral konfiguriert, nicht im Client.

---

## Inhaltsverzeichnis

1. [Grundidee und Separation of Concerns](#1-grundidee-und-separation-of-concerns)
2. [Verzeichnisstruktur](#2-verzeichnisstruktur)
3. [Instanz-Konzept und Git-Trennung](#3-instanz-konzept-und-git-trennung)
4. [Konfigurations-Kaskade](#4-konfigurations-kaskade)
5. [Profil-Struktur](#5-profil-struktur)
6. [Engine-Templates und Instanz-Engines](#6-engine-templates-und-instanz-engines)
7. [Ensemble-Struktur](#7-ensemble-struktur)
8. [Der Proxy – Modell-Aliase und Parameter-Injektion](#8-der-proxy--modell-aliase-und-parameter-injektion)
9. [Debug-Endpoints](#9-debug-endpoints)
10. [Serve-Modi](#10-serve-modi)
11. [Bench und Eval](#11-bench-und-eval)
12. [Datenbank](#12-datenbank)
13. [Starten – Schnellreferenz](#13-starten--schnellreferenz)

---

## 1. Grundidee und Separation of Concerns

Der Dispatcher trennt strikt was zusammen, was getrennt sein muss:

| Ebene | Datei/Ort | Was steht dort |
|---|---|---|
| Modell-Defaults | `defaults/<modell>.yaml` | Sampling, hardware-agnostisch (z. B. Gemma-Empfehlungen) |
| Engine-Defaults | `instances/<name>/engines/<engine>.yaml` | Binär-Pfad, GPU-Flags (maschinenspezifisch) |
| Profil | `instances/<name>/profiles/<name>.yaml` | Modellpfad, Kontext, Quantisierung, Betriebsparameter |
| Ensemble | `instances/<name>/ensembles/<name>.yaml` | Welche Modelle, welche Aliase, welche Sampling-Overrides |
| Dispatcher-Code | `src/dispatcher.py` | Kompilierung, Proxy-Logik, Metriken |
| Instanz-Daten | `instances/<name>/data/` | SQLite-Datenbank (lokal, nicht im Repo) |

**Für den Betrieb gilt:** Wer ein Ensemble konfiguriert, muss nur die Ensemble-Datei anfassen. Wer die Hardware wechselt, passt die Engine-Datei an. Wer Sampling-Defaults ändert, bearbeitet `defaults/<modell>.yaml`.

---

## 2. Verzeichnisstruktur

```
Llama_Dispatcher/
├── src/
│   └── dispatcher.py          # Orchestrator + Proxy + API
├── defaults/
│   ├── gemma.yaml             # Gemma Sampling-Defaults (serve-Sektion)
│   ├── llama.yaml             # Llama Sampling-Defaults
│   ├── qwen.yaml              # Qwen Sampling-Defaults
│   └── engine-templates/      # Vorlagen zum Kopieren nach instances/<name>/engines/
│       ├── cuda.yaml
│       ├── vulkan.yaml
│       └── sycl.yaml
├── instances/                 # NICHT im Haupt-Repo (separates privates Git)
│   ├── Laptop/
│   │   ├── instance.yaml      # machine_guid, nickname
│   │   ├── engines/
│   │   │   └── vulkan.yaml    # bin_dir + GPU-Flags für diesen Rechner
│   │   ├── ensembles/
│   │   │   └── thinkpad.yaml
│   │   ├── profiles/
│   │   │   └── Thinkpad_vulkan_gemma_26B_A4B.yaml
│   │   └── data/
│   │       └── metrics.db     # SQLite (nicht versioniert)
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

## 3. Instanz-Konzept und Git-Trennung

Jede Maschine ist eine **Instanz** unter `instances/<name>/`. Der Haupt-Dispatcher-Code ist öffentlich auf GitHub; die Instanzen enthalten Maschinenpfade, Modellpfade und private Daten – diese gehören **nicht** ins öffentliche Repo.

**Lösung:** `instances/` ist im Haupt-`.gitignore` ausgenommen und wird als **eigenes privates Git-Repo** verwaltet:

```bash
# Einmalig einrichten (bereits gemacht):
cd instances/
git init
git remote add origin git@github.com:<user>/llama-dispatcher-instances.git
git push -u origin master

# Täglicher Workflow nach Konfigurationsänderungen:
cd instances/
git add .
git commit -m "thinkpad: neuen Agent-Alias konfiguriert"
git push
```

Die `instances/.gitignore` schliesst automatisch aus: `*/data/*.db` und `*/data/*.ini` (generierte Lauf-Artefakte).

**Dispatcher starten mit Instanz-Angabe:**
```bash
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop
uv run src/dispatcher.py serve --ensemble 3090    --instance Speedy
```

---

## 4. Konfigurations-Kaskade

Beim Laden eines Profils werden vier Schichten zusammengeführt (**deep merge**, spätere Schichten überschreiben frühere):

```
defaults/<modell>.yaml          (1. Modell-Defaults: Sampling, hardware-agnostisch)
        ↓ deep-merge
instances/<name>/engines/<engine>.yaml  (2. Engine-Defaults: bin_dir, GPU-Flags)
        ↓ deep-merge
instances/<name>/profiles/<name>.yaml   (3. Profil: Modellpfad, Kontext, Betriebsparameter)
        ↓ deep-merge (inline, höchste Priorität)
Ensemble-Modell-Eintrag         (4. Ensemble: Alias, Sampling-Overrides, load-on-startup)
```

Das Profil referenziert die Schichten 1 und 2 explizit:
```yaml
defaults:
  model: "gemma"    # → defaults/gemma.yaml
  engine: "vulkan"  # → instances/Laptop/engines/vulkan.yaml
```

**Konsequenz:** Sampling-Defaults stehen genau einmal in `defaults/gemma.yaml`. Vulkan-spezifische Flags stehen genau einmal in `engines/vulkan.yaml`. Das Profil enthält nur was wirklich modellspezifisch ist.

---

## 5. Profil-Struktur

Profile beschreiben ein Modell auf einer bestimmten Hardware. Sie haben drei Betriebsmodus-Sektionen (`serve`, `bench`, `eval`) und eine gemeinsame Sektion (`common`).

```yaml
# instances/Laptop/profiles/Thinkpad_vulkan_gemma_26B_A4B.yaml
name: "Thinkpad_vulkan_gemma_26B_A4B"
description: "Gemma 4 26B QAT, Vulkan-Build, reduzierter Kontext"

defaults:
  model: "gemma"    # → defaults/gemma.yaml  (Sampling-Defaults)
  engine: "vulkan"  # → instances/Laptop/engines/vulkan.yaml  (bin_dir, GPU-Flags)

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
  jinja: true       # Pflicht für Gemma 4
  port: 8081        # Fallback wenn nicht im Ensemble definiert
  host: "0.0.0.0"
  ctx-checkpoints: 0
  # no-kv-offload und cache-ram kommen aus engines/vulkan.yaml

bench:
  r: 1
  pg:
    - [512, 128]
    - [16384, 128]
    - ["MAX_CONTEXT", 128]

eval:
  c: 8192
  b: 512
  ot: null   # entfernt das override-tensor-Flag für Perplexity
```

**Kurzformen** werden kanonisiert: `m` → `model`, `c` → `ctx-size`, `ngl` → `n-gpu-layers`, `ctk` → `cache-type-k`, `ot` → `override-tensor`.

---

## 6. Engine-Templates und Instanz-Engines

Engine-Dateien trennen was binär-/hardware-spezifisch ist vom Modell. Sie werden per **deep merge** in die `common:` und `serve:` Sektionen des Profils eingebettet.

**Template** (Vorlage unter `defaults/engine-templates/`):
```yaml
# defaults/engine-templates/vulkan.yaml  – NUR Vorlage, nicht direkt verwendet
bin_dir: "c:\\llama-cpp\\server\\server_vulkan"
```

**Instanz-spezifische Engine** (nach dem Template-Kopieren anpassen):
```yaml
# instances/Laptop/engines/vulkan.yaml
bin_dir: "c:\\llama.cpp\\server\\server_06_vulcan"

common:
  n-gpu-layers: 99   # alle Layer auf GPU
  split-mode: none   # kein Multi-GPU
  main-gpu: 0
  flash-attn: on

serve:
  no-kv-offload: true  # Vulkan unterstützt kein KV-Offloading
  cache-ram: 0         # verhindert Vulkan-spezifische Abstürze
```

Suchreihenfolge: `instances/<name>/engines/` → `defaults/engine-templates/` (Fallback).

---

## 7. Ensemble-Struktur

Ensembles definieren welche Modelle gemeinsam im llama.cpp-Router angeboten werden, und welche Modell-Aliase der **Proxy** nach aussen sichtbar macht.

```yaml
# instances/Laptop/ensembles/thinkpad.yaml

defaults:
  engine: "vulkan"   # → instances/Laptop/engines/vulkan.yaml  (für bin_dir)

dispatcher:
  port: 8001         # Dispatcher-Proxy-Port (Clients zeigen hierher)

engine:
  port: 8081         # llama.cpp-Server-Port (intern, Dispatcher leitet dorthin)
  host: "0.0.0.0"
  models_max: 1

models:
  # Echtes llama.cpp-Modell (belegt VRAM)
  - profile: "Thinkpad_vulkan_gemma_26B_A4B"
    alias: "sparringpartner"
    load-on-startup: true
    chat_template_kwargs:
      enable_thinking: true

  # Proxy-only Alias: kein VRAM, leitet auf "sparringpartner" weiter
  - profile: "Thinkpad_vulkan_gemma_26B_A4B"
    alias: "agent"
    target: "sparringpartner"
    chat_template_kwargs:
      enable_thinking: false
    sampling:
      temperature: 0.3
      top_k: 20
      top_p: 0.9
      min_p: 0.1
      repeat_penalty: 1.1
```

**Schlüsselkonzepte:**

| Feld | Bedeutung |
|---|---|
| `defaults.engine` | Liest `bin_dir` aus der Instanz-Engine-Datei |
| `dispatcher.port` | Port des Dispatcher-Proxys (Clients) |
| `engine.port` | Port von llama.cpp (intern) |
| `target: "alias"` | Proxy-only: kein INI-Eintrag, wird auf Ziel-Alias umgeschrieben |
| `chat_template_kwargs` | Wird vom Proxy in jeden Request injiziert (z. B. `enable_thinking`) |
| `sampling:` | Sampling-Parameter, die der Proxy injiziert und überschreibt |

---

## 8. Der Proxy – Modell-Aliase und Parameter-Injektion

Der Dispatcher ist ein **vollständiger OpenAI-kompatibler Proxy**. Clients zeigen auf `http://<host>:8001/v1/` statt direkt auf llama.cpp.

### Was der Proxy macht

Für jeden eingehenden Request:

1. **Alias-Lookup**: Findet die konfigurierten Parameter für das angeforderte Modell (`model: "agent"`)
2. **Sampling-Injektion**: Injiziert `temperature`, `top_p`, `top_k`, `min_p`, `repeat_penalty`, `chat_template_kwargs` – **Proxy-Werte überschreiben Client-Werte immer**
3. **Alias-Remapping** (bei `target:`): Schreibt `model: "agent"` → `model: "sparringpartner"` um
4. **Weiterleitung** an llama.cpp (Port 8081)
5. **Logging**: Endpoint, Modell, Tokens, Latenz, TTFT in SQLite

### Was Clients sehen

```
GET http://localhost:8001/v1/models
→ ["sparringpartner", "agent"]   ← beide sichtbar, ein Modell im VRAM
```

### Datenfluss

```
Open WebUI / Goose / curl
  POST /v1/chat/completions  { "model": "agent", "temperature": 0.9, ... }
        ↓
Dispatcher (Port 8001):
  → Sampling für "agent" laden: temp=0.3, top_k=20, enable_thinking=false
  → temperature: 0.9 → 0.3  (Proxy überschreibt)
  → model: "agent" → "sparringpartner"  (Remapping)
  → Weiterleitung: { "model": "sparringpartner", "temperature": 0.3, ... }
        ↓
llama.cpp (Port 8081): kennt nur [sparringpartner] – ein Modell, keine Swaps
```

### Warum das sinnvoll ist

- **Einheitlichkeit**: Alle Clients erhalten dieselben Parameter, unabhängig davon was sie senden
- **VRAM-Effizienz**: Mehrere Aliase, ein Modell – kein ständiges Laden/Entladen
- **Konfiguration zentral**: Thinking an/aus, Sampling-Modus – alles in der Ensemble-Datei, nicht im Client

---

## 9. Debug-Endpoints

Während der Dispatcher läuft, stehen zwei Debug-Endpoints zur Verfügung:

### `GET /debug/config`

Zeigt die aktuelle Proxy-Konfiguration:

```bash
curl http://localhost:8001/debug/config
```

Antwort:
```json
{
  "status": "running",
  "llama_port": 8081,
  "aliases": [
    {
      "alias": "sparringpartner",
      "type": "real",
      "target": null,
      "injected_params": {"temperature": 1.0, "chat_template_kwargs": {"enable_thinking": true}}
    },
    {
      "alias": "agent",
      "type": "proxy-only",
      "target": "sparringpartner",
      "injected_params": {"temperature": 0.3, "chat_template_kwargs": {"enable_thinking": false}}
    }
  ]
}
```

### `POST /debug/preview`

Simuliert die Proxy-Transformation **ohne Weiterleitung** – ideal zum Testen vor dem echten Start:

```bash
curl http://localhost:8001/debug/preview \
  -H "Content-Type: application/json" \
  -d '{"model":"agent","messages":[{"role":"user","content":"Hallo"}],"temperature":0.9}'
```

Antwort zeigt:
- `original_model` vs. `forwarded_model`
- `injected_params`: was injiziert wurde und was der Client gesendet hatte
- `overridden_by_client`: was der Client wollte aber überschrieben wurde
- `forwarded_body`: der vollständige Body der an llama.cpp gehen würde

### Compile-only (ohne Server-Start)

```bash
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop --compile-only
```

Zeigt die generierte INI und den llama.cpp-Startbefehl, startet aber nichts.

---

## 10. Serve-Modi

### Ensemble-Modus (Standard für den Betrieb)

```bash
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop
```

Ablauf:
1. Liest `instances/Laptop/ensembles/thinkpad.yaml`
2. Lädt Profile, merged Engine-Defaults und Modell-Defaults (Kaskade)
3. Schreibt `instances/Laptop/data/thinkpad_models.ini`
4. Startet llama.cpp: `llama-server --models-preset thinkpad_models.ini ...`
5. Startet Dispatcher-Proxy auf Port 8001

Der Dispatcher-Port wird aus `ensemble.dispatcher.port` gelesen; `--api-port` auf der CLI überschreibt ihn.

### Einzelprofil-Modus (für Tests und Feinschliff)

```bash
uv run src/dispatcher.py serve --profile Thinkpad_vulkan_gemma_26B_A4B --instance Laptop
```

Startet llama.cpp direkt aus dem Profil, ohne Router-INI. Kein Proxy-Aliasing.

---

## 11. Bench und Eval

```bash
uv run src/dispatcher.py bench --profile Thinkpad_vulkan_gemma_26B_A4B --instance Laptop
uv run src/dispatcher.py eval  --profile Thinkpad_vulkan_gemma_26B_A4B --instance Laptop \
    --dataset data/wikitext-2-raw.txt
```

`MAX_CONTEXT` in `bench.pg` wird zur Laufzeit auf `ctx-size - tg` berechnet.

---

## 12. Datenbank

Pro Instanz: `instances/<name>/data/metrics.db` (nicht versioniert).

### Tabellen

| Tabelle | Inhalt |
|---|---|
| `execution_runs` | Ein Eintrag pro Server-Start (Ensemble/Profil, Version, CLI, INI-Hash) |
| `serve_model_instances` | Eine Instanz pro geladenem Modell (deklarierte + effektive Parameter) |
| `metrics_serve` | Ein Eintrag pro abgeschlossener Anfrage (Tokens, Speed, TTFT, Sampling-Params) |
| `metrics_lifecycle` | Load/Evict/Unload-Events |
| `metrics_bench` | Benchmark-Ergebnisse mit Fehlerbalken |
| `metrics_eval` | Perplexity-Ergebnisse |
| `proxy_requests` | Proxy-Log: Endpoint, Modell, injizierte Params, Tokens, Latenz, TTFT |

### Zeitstempel

Alle Zeitstempel timezone-aware: `YYYY-MM-DD HH:MM:SS+HH:MM` (lokale Zeit mit UTC-Offset). Sortierbar, direkt lesbar in DB-Viewern.

### Views

- `v_serve_telemetry` – Request-Timings mit Runtime-Kontext
- `v_serve_model_instances` – geladene Modellinstanzen mit effektiven Args
- `v_router_performance` – Lifecycle-Events aggregiert
- `v_bench_results` / `v_eval_results` – Mess-Ergebnisse

---

## 13. Starten – Schnellreferenz

```bash
# Ensemble starten (Proxy + llama.cpp)
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop

# Nur kompilieren, nicht starten
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop --compile-only

# Proxy-Konfiguration prüfen (während Betrieb)
curl http://localhost:8001/debug/config

# Request-Transformation simulieren (während Betrieb)
curl http://localhost:8001/debug/preview \
  -H "Content-Type: application/json" \
  -d '{"model":"agent","messages":[{"role":"user","content":"test"}]}'

# Modelle sehen (wie Open WebUI)
curl http://localhost:8001/v1/models

# instances sichern
cd instances/ && git add . && git commit -m "Update" && git push

# Instanz Remote einrichten (einmalig)
cd instances/
git remote add origin git@github.com:<user>/llama-dispatcher-instances.git
git push -u origin master
```
