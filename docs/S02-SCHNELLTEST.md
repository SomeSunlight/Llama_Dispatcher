# S02 — Kurztest auf Laptop / Windows

## Empfohlen für Laptop/Windows mit SYCL: normaler PowerShell-Start

Der native `llama-server.exe` ist beim automatischen `--start`-Test mit
Windows `0xC0000135` (fehlende DLL) abgestürzt, funktioniert aber mit deinem
bekannten PowerShell-Startkommando. Darum können wir Authentifizierung und
Inferenz **ohne automatisches Starten durch Python** prüfen. Das ist auch
näher an der künftigen Attach-/Prozessmanager-Architektur.

**1. Der alte Testdispatcher ist beendet.** Im Projektverzeichnis:

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --prepare-manual
```

Das Skript erzeugt zwei lokale Einmal-Testtokens und zeigt eine einzelne
`$env:DISPATCHER_CLIENT_CONFIG = '...'`-Zeile.

**2. In der normalen PowerShell 7** diese angezeigte Zeile ausführen und
den Dispatcher **wie immer** starten:

```powershell
uv run src/dispatcher.py serve --ensemble thinkpad-sycl-gemma_26B --instance Laptop_Win --model-root c:\AI_Models\LLM\GGUF_Raw
```

Keine Änderungen an SYCL, PATH oder den llama.cpp-Dateien. Laufen lassen.

**3. Im zweiten PowerShell-Terminal** den vollständigen Test durchführen:

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --verify-manual --inference
```

Geprüft werden zwei getrennte simulierte Clients, Zugriffskontrollen,
Parameterregeln, winzige echte Modellanfragen und die Einträge in SQLite v9.
Das Skript startet oder beendet dabei **keinen** Prozess.

Anschliessend den Dispatcher selbst mit Ctrl+C beenden und die lokalen
Einmal-Testschlüssel entfernen:

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --cleanup-manual
```

Die Einmal-Testschlüssel liegen bis dahin lokal in zwei Git-ignorierten Dateien
unter `reports/` (darunter eine Datei mit **rohen**, kurzlebigen Tokens).
Nicht hochladen oder in Git aufnehmen. Das Skript überschreibt diese Dateien
nicht ohne vorherige Bereinigung; bestehende `C:\llama.cpp\clients.json` bleibt
unverändert. Im PowerShell-Terminal nach dem Test die Variable optional entfernen
mit `Remove-Item Env:DISPATCHER_CLIENT_CONFIG`.

**Automatischer Start `--start --inference` bleibt optional** für nichtproduktive
Testinstanzen ohne solche Windows-/SYCL-Unterschiede. Der bekannte Fehler
`0xC0000135` wird damit nicht als gelöst ausgegeben: Der neue Testpfad
umgeht lediglich den abweichenden Test-Launcher.

---

## Wozu?

Wir prüfen zwei **simulierte** Clients (Goose und Open WebUI):
Jeder bekommt ein anderes Test-Token. Der Dispatcher muss beide unterscheiden,
verschiedene Parameterregeln anwenden, unerlaubte Anfragen abweisen und die
richtige Client-ID in SQLite protokollieren.

**Goose, Open WebUI und Strata müssen dazu nicht laufen.**
Es genügt die vorhandene Laptop-Windows-Instanz mit llama.cpp.

## Drei Schritte — keine Skriptänderungen

**1. Während der normale Laptop-Windows-Dispatcher noch läuft:** Das bereits
bewährte Startkommando einmalig automatisch erfassen:

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --save-start
```

Das Programm liest das tatsächliche Startkommando aus dem lokalen
Betriebssystem und speichert die Einstellungen **nur auf diesem Rechner** in
`reports/s02-Laptop_Win.launch.json`. Beim späteren Teststart verwendet es
jedoch **denselben Python-Interpreter wie `uv run --frozen`**; nur die erfassten
Dispatcher-Argumente werden übernommen. Dadurch werden die Projektbibliotheken
wie PyYAML zuverlässig gefunden. Diese Datei ist Git-ignoriert,
enthält lokale Startpfade und muss normalerweise nie bearbeitet werden.
Das Programm startet oder beendet dabei **nichts**.

**2. Den normalen Laptop-Windows-Testdispatcher selbst regulär beenden**, sodass
der lokale API-Port frei wird. Der Test darf keinen fremden Prozess übernehmen.

**3. Den automatischen Live-Test durchführen:**

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --start --inference
```

Jetzt startet das Programm **nur** den zuvor erfassten Testdispatcher,
erzeugt zwei **einmalige** private Token, überprüft Authentifizierung,
Parameterregeln, HTTP und zwei sehr kurze Inferenzanfragen, liest SQLite v9
und beendet seinen eigenen Testprozess wieder.

**Abgleich der Startparameter:** Der Test zeigt beim Start nun die
ursprünglich erfassten Werte für `--instance`, `--ensemble` und
`--model-root` an. Vergleiche sie mit deinem sonst funktionierenden
`uv run src/dispatcher.py serve ...`. Der Test behält die übrigen
Dispatcher-Argumente bei, startet aber aus Sicherheitsgründen in einer eigenen
Prozessgruppe, leitet seine Konsolenausgabe ins Log um und verwendet temporäre
Test-Authentifizierung. Diese Unterschiede können bei nativen SYCL-Starts
relevant sein und müssen bei einem Absturz untersucht werden.

Wenn `llama-server.exe` unmittelbar beendet wird, erscheint zusätzlich dessen
**nativer Exit-Code** (unter Windows auch hexadezimal). Damit lassen sich z. B.
fehlende Laufzeitbibliotheken von normalen Modellfehlern unterscheiden, ohne
einen solchen Fehler vorab zu behaupten.

**Wenn der Dispatcher beim Start scheitert:** Das Skript zeigt automatisch
die letzten 30 Zeilen seiner gewohnten Konsolenausgabe und den Exit-Code.
Das vollständige Log bleibt auf dem jeweiligen Rechner unter
`reports/s02-Laptop_Win.dispatcher-<Zeitstempel>-<PID>.log`.
Diese privaten Diagnose-Dateien werden von Git ignoriert und weder hochgeladen
noch zusammen mit den Einmal-Tokens gelöscht. Bitte vor dem Teilen überprüfen:
Sie können lokale Modellpfade, Konfigurationsdetails und andere private Angaben
enthalten. Du brauchst keinen zusätzlichen Logger im Dispatcher.

Deine vorhandene `C:\llama.cpp\clients.json` wird nicht verwendet oder
verändert. Der Test erstellt seine Wegwerf-Tokens selbst.

## Auch auf anderen Maschinen?

**Ein einziges `scripts/s02_verify.py` für alle Rechner.**
Die Befehle bleiben gleich, nur `--instance` ist anders, z. B.
`Laptop_WSL` oder `Speedy_Win`. Das erfasste Startkommando ist jeweils
lokal gespeichert, nicht im gemeinsamen Testcode. Wenn der API-Port
nicht 8001 ist, kann `--base-url http://127.0.0.1:PORT` ergänzt werden.

**Nicht für den produktiven Strata-Prozess verwenden.**
S03 prüft Strata separat; dieser S02-Runner darf nur eine bewusst ausgewählte,
nichtproduktive llama.cpp-Testinstanz starten.

Bei Problemen genügt die letzte `S02 PASS`- oder `S02 FAIL`-Meldung
plus wenige Zeilen darum herum. Eine längere Ausgabe bitte als Logdatei
anhängen.

Ausführliche Hintergründe: [S02-client-identities.md](S02-client-identities.md).
