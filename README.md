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
13. [CLI-Referenz](#13-cli-referenz)
14. [Parameternamen-System](#14-parameternamen-system)
15. [Starten – Schnellreferenz](#15-starten--schnellreferenz)

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

**Lösung:** `instances/` ist im Haupt-`.gitignore` ausgenommen. Jede Instanz ist ein **eigenes privates Git-Repo**:

| Repo | Sichtbarkeit | Inhalt |
|---|---|---|
| `SomeSunlight/Llama_Dispatcher` | öffentlich | Code, Defaults, Dokumentation |
| `SomeSunlight/Llama_Dispatcher_Laptop` | privat | Laptop-Profile, Engines, Ensembles |
| `SomeSunlight/Llama_Dispatcher_Speedy` | privat | Speedy-Profile, Engines, Ensembles |

### Fresh Install auf neuem Rechner

Der Trick beim Klonen: `git clone <url> <zielverzeichnis>` erlaubt einen eigenen Ordnernamen –
so landet die Instanz direkt im richtigen Unterverzeichnis, ohne dass der GitHub-Reponame stört.

```powershell
# Schritt 1: Hauptrepo klonen
git clone https://github.com/SomeSunlight/Llama_Dispatcher.git
cd Llama_Dispatcher

# Schritt 2: Instanz-Repos in die EXAKT richtigen Unterverzeichnisse klonen
git clone https://github.com/SomeSunlight/Llama_Dispatcher_Laptop.git instances/Laptop
git clone https://github.com/SomeSunlight/Llama_Dispatcher_Speedy.git instances/Speedy

# Schritt 3: Python-Umgebung
uv sync
```

Nach dem Klonen `instance.yaml` prüfen: die `machine_guid` identifiziert die Maschine eindeutig
in der Metrics-Datenbank. Auf einem neuen Gerät eine neue GUID eintragen oder mit `--instance NeuerName`
eine frische Instanz anlegen (wird automatisch erstellt).

### Täglicher Workflow nach Konfigurationsänderungen

```bash
# Laptop-Instanz sichern
cd instances/Laptop
git add .
git commit -m "thinkpad: neuen Agent-Alias konfiguriert"
git push

# Speedy-Instanz sichern
cd instances/Speedy
git add .
git commit -m "3090: Kontext erhöht"
git push
```

### Was `--instance` bewirkt

```bash
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop
```

Mit `--instance Laptop` zeigt der Dispatcher auf `instances/Laptop/profiles|ensembles|data/`
und liest die `machine_guid` aus `instances/Laptop/instance.yaml`.

**Ohne `--instance`** läuft der Dispatcher im **Legacy-Modus**: er sucht Profile und Ensembles
direkt unter `profiles/` und `ensembles/` im Projektroot – **kein Prompt**, kein Fehler, nur
falscher Pfad. Wer die Instanzstruktur nutzt, muss `--instance` immer angeben.

Existiert die angegebene Instanz noch nicht, legt der Dispatcher sie automatisch an
(leere Verzeichnisse, neue `machine_guid` in `instance.yaml`).

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

## 13. CLI-Referenz

### Aufruf-Syntax

```bash
uv run src/dispatcher.py <modus> [optionen] [llama.cpp-overrides...]
```

### Modi (Pflichtargument)

| Modus | Beschreibung |
|---|---|
| `serve` | Startet llama.cpp + Dispatcher-Proxy. Benötigt `--ensemble` **oder** `--profile` |
| `bench` | Benchmark (pp/tg-Geschwindigkeit). Benötigt `--profile` |
| `eval` | Perplexity-Messung. Benötigt `--profile` und `--dataset` |

### Optionen

| Option | Default | Beschreibung |
|---|---|---|
| `--ensemble NAME` | – | Name des Ensemble-YAMLs (ohne `.yaml`). Für `serve` im Router-Modus mit Proxy |
| `--profile NAME` | – | Name des Profil-YAMLs (ohne `.yaml`). Für `serve` Einzelmodell, `bench`, `eval` |
| `--instance NAME` | – | Instanzname (Ordner unter `instances/`). **Ohne diesen Parameter läuft der Dispatcher im Legacy-Modus** und sucht Profile/Ensembles im Projektroot. Kein Prompt. |
| `--api-port PORT` | aus Ensemble oder `8001` | Port des Dispatcher-Proxys. Überschreibt `dispatcher.port` im Ensemble-YAML |
| `--dataset PFAD` | `data/wikitext-2-raw.txt` | Textdatei für `eval` (Perplexity) |
| `--compile-only` | – | Kompiliert INI und zeigt den llama.cpp-Startbefehl, startet aber nichts |

### Ad-hoc llama.cpp-Overrides

**Alle** llama.cpp-Parameter können direkt an der CLI übergeben werden – sie überschreiben
das Profil/Ensemble mit der höchsten Priorität. Der Dispatcher erkennt und kanonisiert
sämtliche Schreibweisen automatisch (kurz, lang, Binde- oder Unterstrich):

```bash
# Kontext auf 8192 begrenzen (für schnelle Tests)
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop --ctx-size 8192

# Parallelität und Threads überschreiben
uv run src/dispatcher.py bench --profile Thinkpad_vulkan_gemma_26B_A4B --instance Laptop \
    --parallel 2 --threads 8

# Sampling für diesen Start überschreiben
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop \
    --temperature 0.5 --top-k 40
```

Boolean-Flags werden als `true`/`false` oder als nacktes Flag akzeptiert:
```bash
--flash-attn true   # explizit
--flash-attn        # äquivalent (Flag ohne Wert = true)
--no-kv-offload     # negierendes Präfix für Schalter
```

---

## 14. Parameternamen-System

### Das Problem

YAML verbietet Unterstriche in Schlüsseln nicht, aber llama.cpp verwendet Bindestriche
(`--ctx-size`, `--cache-type-k`). Obendrauf gibt es Kurz- und Langformen (`-c` vs. `--ctx-size`).
Das Ensemble/Profil kann aus drei Quellen stammen (Defaults, Engine, Profil), die jeweils
unterschiedliche Konventionen verwenden könnten. Ohne klare Regel sind Tippfehler
still und wirkungslos.

### Die Lösung: Kanonisierung

Der Dispatcher normalisiert **jeden** Schlüssel beim Einlesen auf die **kanonische Form**:
→ Bindestriche, Langform, ohne führende Dashes.

Kanonisierungsschritte (in Reihenfolge):
1. Führende `-` oder `--` entfernen
2. Alle `_` durch `-` ersetzen
3. Kurzform in Langform übersetzen (via `PARAM_MAPPING`)

**Resultat:** `top_k`, `top-k`, `-tk` (falls definiert) – alles wird zu `top-k`.

### Empfehlung für YAMLs

**Bindestriche verwenden.** Der Dispatcher akzeptiert beides, aber Bindestriche entsprechen
dem llama.cpp-Standard und sind in `debug/config` und der Datenbank so zu sehen.

```yaml
# ✅ Bevorzugt
cache-type-k: "q8_0"
flash-attn: true

# ✅ Funktioniert auch (wird zu oben kanonisiert)
cache_type_k: "q8_0"
flash_attn: true

# ✅ Kurzform in common:/serve: funktioniert
ngl: 99    # → n-gpu-layers
c: 65536   # → ctx-size
```

### Gruppen-Schlüssel (nur YAML, nicht an llama.cpp)

Diese Schlüssel existieren **nicht** in llama.cpp – sie sind YAML-Komfort-Wrapper.
Ihr Inhalt wird vor der Kanonisierung flach ausgepackt:

```yaml
sampling:         # → Inhalt wird direkt in die Parameter-Liste gepackt
  temperature: 1.0
  top-k: 64
  top-p: 0.95

# Äquivalent zu:
temperature: 1.0
top-k: 64
top-p: 0.95
```

Gültige Gruppen-Schlüssel: `sampling`, `sampler`, `generation`, `defaults`

### Vollständige Kurzform-Tabelle (PARAM_MAPPING)

| Kurzform / Alias | Kanonische Langform |
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

> Alle anderen Schlüssel: `_` → `-` reicht. `cache_type_k` → `cache-type-k` automatisch.

### Was mit eingehenden Request-Parametern passiert (Proxy)

Wenn ein Client `temperature: 0.9` sendet und das Ensemble `temperature: 0.3` konfiguriert hat,
**überschreibt der Proxy den Client-Wert immer**. Das ist so gewollt.

Die Sampling-Parameter, die der Proxy verwaltet (und ggf. überschreibt), sind:

`temperature`, `top-p`, `top-k`, `min-p`, `repeat-penalty`, `presence-penalty`,
`frequency-penalty`, `typical-p`, `dynatemp-range`, `dynatemp-exp`, `mirostat-lr`,
`mirostat-ent`, `dry-multiplier`, `dry-base`, `dry-allowed-length`, `dry-penalty-last-n`,
`sampler-seq`, `repeat-last-n`

**In der Datenbank** werden sie in der kanonischen Form (Bindestriche) gespeichert.
**Im JSON-Body** an llama.cpp werden sie mit Unterstrichen geschrieben (`top_k`, `temperature`)
– das erwartet die OpenAI-kompatible llama.cpp-API.

`chat_template_kwargs` ist ein Sonderfall: er wird als Proxy-Parameter injiziert,
erscheint aber nicht in der llama.cpp-INI.

---

## 15. Starten – Schnellreferenz

```bash
# Ensemble starten (Proxy + llama.cpp)
uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop
uv run src/dispatcher.py serve --ensemble 3090    --instance Speedy

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

# Instanz sichern (Laptop)
cd instances/Laptop && git add . && git commit -m "Update" && git push

# Fresh Install auf neuem Rechner (alle 3 Repos in einem Rutsch)
git clone https://github.com/SomeSunlight/Llama_Dispatcher.git
cd Llama_Dispatcher
git clone https://github.com/SomeSunlight/Llama_Dispatcher_Laptop.git instances/Laptop
git clone https://github.com/SomeSunlight/Llama_Dispatcher_Speedy.git instances/Speedy
uv sync
```
