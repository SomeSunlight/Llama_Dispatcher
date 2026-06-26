# Contributing to the Llama Dispatcher

Dieses Projekt folgt strengen Prinzipien in Bezug auf Abhängigkeiten, Konfigurations-Architektur, Proxy-Verhalten, Datenbankintegrität und beobachtbare Runtime-Transparenz.

## 1. Environment & Dependencies

- **Strict `uv` Usage:** Wir verwenden weder `pip`, `conda` noch `poetry` direkt. Alle Abhängigkeiten werden exklusiv über `uv add <package>` verwaltet.
- **Isolierung:** Tests und Ausführungen erfolgen über `uv run`.

## 2. Instanz-Trennung

Der Haupt-Code-Repo (`src/`, `defaults/`, Dokumentation) ist öffentlich. Die maschinenspezifischen Konfigurationen unter `instances/` sind **im Haupt-`.gitignore`** ausgenommen und werden als **eigenes privates Repo** verwaltet.

Nichts unter `instances/` darf in das öffentliche Repo aufgenommen werden – dort stehen Modellpfade, Maschinenpfade und private Betriebsdaten. Das `instances/`-Repo hat ein eigenes `.gitignore`, das `*/data/*.db` und `*/data/*.ini` (Lauf-Artefakte) ausschliesst.

## 3. Separation of Concerns – was gehört wohin

Die Konfigurations-Kaskade hat eine klare Zuständigkeitsgrenze:

| Ebene | Ort | Zuständigkeit |
|---|---|---|
| Modell-Defaults | `defaults/<modell>.yaml` | Hardware-agnostisches Sampling (einmal für alle Maschinen) |
| Engine-Defaults | `instances/<name>/engines/<engine>.yaml` | Binary-Pfad, GPU-Flags (maschinenspezifisch) |
| Profil | `instances/<name>/profiles/` | Modellpfad, Kontext, Quantisierung, Betriebsmodi |
| Ensemble | `instances/<name>/ensembles/` | Welche Modelle, Proxy-Aliase, Sampling-Overrides |

**Niemals** Engine-Flags in Profilen, Modellpfade in Engine-Dateien oder Sampling-Defaults doppelt ablegen. Jede Information existiert genau einmal an der richtigen Stelle.

## 4. Parameter-Kanonisierung

- Neue llama.cpp-Parameter müssen in `PARAM_MAPPING` in `dispatcher.py` eingetragen werden.
- Kurzformen (`c`, `ngl`, `ctk`, `ctv`, `ot`) und Schreibvarianten (`top_p`, `top-p`) werden intern auf kanonische Langformen ohne führende Dashes gemappt.
- JSON-Felder in der Datenbank speichern Parameter ohne führende Dashes in kanonischer Langform.

Wichtige Mappings:

```
c          → ctx-size
ngl        → n-gpu-layers
ctk        → cache-type-k
ctv        → cache-type-v
ot         → override-tensor   (nicht override-kv – das ist GGUF-Metadaten)
top_p      → top-p
repeat_penalty → repeat-penalty
```

## 5. Proxy-Architektur – Grundprinzipien

Der Dispatcher ist ein **vollständiger OpenAI-kompatibler Proxy**. Das ist eine bewusste Architekturentscheidung mit klaren Regeln:

**Proxy-Werte überschreiben Client-Werte immer.** Wenn `temperature: 0.3` im Ensemble konfiguriert ist, erhält llama.cpp `0.3` – egal was der Client sendet. Das ist der Sinn der zentralen Konfiguration.

**`target:` Aliase** existieren nur im Proxy, nicht in der llama.cpp-INI. Ein `target:` verweist auf einen echten Alias. Der Proxy injiziert die Sampling-Parameter des proxy-only Alias und schreibt das `model:`-Feld um. So können mehrere „Persönlichkeiten" dasselbe Modell im VRAM teilen ohne es doppelt zu laden.

**`chat_template_kwargs`** ist ein Proxy-Only-Key: Er wird nicht in die llama.cpp-INI geschrieben, aber vom Proxy in jeden Request injiziert. So kann `enable_thinking` zentral für alle Clients gesteuert werden.

**Keine magischen Rewrites ohne Konfiguration.** Alle Transformationen basieren auf expliziter YAML-Konfiguration im Ensemble. Der Code beschreibt nur was die Konfiguration vorgibt.

## 6. Profile und Ensembles

**Profile** sind modell- und hardware-nahe Schablonen für einen Betriebsmodus. Sie können direkt gestartet werden (`serve --profile <name>`). Das ist der empfohlene Weg für Tests und Feinschliff, bevor ein Profil in ein Ensemble aufgenommen wird.

**Ensembles** definieren den Proxy-Betrieb: welche echten Modelle in der INI stehen, welche Aliase der Proxy nach aussen sichtbar macht, und welche Parameter pro Alias injiziert werden. `model_defaults:` im Ensemble (der `[*]`-Abschnitt der INI) ist optional und nur sinnvoll für Parameter die wirklich für alle echten Modelle gelten sollen – nicht als Ersatz für `defaults/<modell>.yaml`.

## 7. Engine-Templates

Engine-Templates unter `defaults/engine-templates/` sind Vorlagen zum Kopieren. Sie werden **nicht direkt vom Dispatcher verwendet**. Instanz-spezifische Engines unter `instances/<name>/engines/` verwenden `common:` und `serve:` Sektionen, die per deep merge in das Profil eingebettet werden.

Suchreihenfolge: `instances/<name>/engines/` → `defaults/engine-templates/` (nur als Fallback, wenn keine Instanz-Engine vorhanden).

## 8. Datenbank-Integrität

Die aktuelle DB ist `instances/<name>/data/metrics.db`. Es gibt keine Migration von älteren Versionen; das Schema wird neu über `src/init_db.sql` aufgebaut.

**Zeitstempel:** Timezone-aware, Format `YYYY-MM-DD HH:MM:SS+HH:MM`. Direkt lesbar, sortierbar, UTC-korrekt.

`execution_runs` ist der historische Lauf-Kopf und wird nach dem Schreiben nicht verändert.

Für Schema-Evolution:
- Keine destruktiven Updates an bestehenden Messdaten.
- `PRAGMA user_version` verwenden.
- Migrationen kontrolliert in `database_manager.py` abbilden.

## 9. Runtime-Instanzen sind Pflicht

- Ein `execution_run` → der Hauptprozess.
- Eine `serve_model_instance` → pro effektiv geladenem Modell.
- `metrics_serve` verweist auf **beide** (historische Klammer + konkrete Modellherkunft).

Auch im Einzelprofil-Modus muss genau eine Runtime-Instanz erfasst werden. Das macht Auswertungen homogen zwischen Einzel- und Ensemble-Modus.

## 10. Proxy-Requests werden geloggt

Der Proxy loggt **jeden** durchgeleiteten Request in `proxy_requests`:
- Endpoint, angefordetes Modell, Stream-Flag
- Injizierte Parameter (als JSON)
- Token-Counts (Prompt + Completion)
- Latenz, TTFT, Status-Code, finish_reason
- `req_enable_thinking` (aus `chat_template_kwargs`)

Das ist die einzige Stelle wo Client-Request-Parameter beobachtet werden – weil der Dispatcher als Proxy dazwischenliegt. llama.cpp selbst sieht nur das bereits transformierte Request.

## 11. FastAPI und Asynchronität

- Externe Payloads für FastAPI-Endpunkte müssen über Pydantic-Modelle oder explizite Validierung geprüft werden.
- Keine blockierenden Aufrufe (`time.sleep`, `subprocess.run`) im Orchestrator.
- Subprozesse asynchron starten und Logs asynchron lesen.

## 12. Metriken und Fehlerbalken

- `metrics_bench.speed_error` ist Pflicht.
- `metrics_eval.perplexity_error` ist Pflicht, soweit verfügbar.
- Keine Messung ohne Fehlerwert wenn Wiederholungen verfügbar sind.

## 13. Entwicklungsstil

- Kleine, nachvollziehbare Änderungen bevorzugen.
- Beobachtete, deklarierte und unbekannte Fakten strikt trennen.
- Konfiguration beschreibt Absicht; Code setzt sie um – nie umgekehrt.
- Neue Features zuerst mit `--compile-only` oder `/debug/preview` testbar machen.
