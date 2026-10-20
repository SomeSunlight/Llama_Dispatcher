# S02 in drei Minuten verstehen und testen

**Du brauchst jetzt nur Laptop/Windows. Kein Goose, kein Open WebUI und kein Strata.**

## Was wird geprüft?

Die Tests tun so, als gäbe es zwei Clients: **Goose** und **Open WebUI**.
Sie prüfen, ob der Dispatcher die zwei Zugangsschlüssel unterscheiden kann,
welche Parameterregeln er anwendet und ob SQLite die richtige Client-ID erfasst.
Das sind *simulierte* Clients; sie müssen nicht installiert oder gestartet sein.

## A. Bestehenden Dispatcher testen (jetzt sofort)

Den **bereits laufenden** Laptop/Windows-Dispatcher mit dem aktuellen PR-Code
normal starten. Dann in deinem gewohnten PyCharm-Terminal:

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win
```

Der Befehl führt automatisch alle Unit-Tests aus, prüft die laufende lokale
HTTP-Schnittstelle und das SQLite-v9-Schema. Es wird **nichts gestartet oder
gestoppt**, keine Inferenz gesendet und kein Modell verändert.

Die isolierten Unit-Tests prüfen bereits beide simulierten Clients, Tokens,
Regeln, abgewiesene Zugriffe, Header-Spoofing und Datenbank-Provenienz.
Bei der laufenden alten (authentifizierungsfreien) Instanz ist der
zusätzliche *echte* Zwei-Token-Test ausdrücklich SKIP.

## B. Vollständiger Zwei-Client-Live-Test (optional, später)

Nur für eine nichtproduktive **llama.cpp-Testinstanz**:

1. In `scripts/s02_verify.py` **oben** bei `Laptop_Win` das
   `start_command: None` durch eine Python-Liste mit **deinem vorhandenen
   Dispatcher-Startkommando** ersetzen. Eine kommentierte Vorlage steht direkt
   darunter. Bestehende `--instance`, `--ensemble`, `--bin-dir`,
   `--model-root` unverändert übernehmen.
2. Den bestehenden **Laptop-Windows-Testdispatcher selbst beenden**, damit
   Port 8001 frei ist. Das Programm beendet niemals einen fremden Prozess.
3. Im gewohnten Projektordner ausführen:

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --start --inference
```

Das Programm erzeugt **selbst** zwei einmalige Test-Token, startet **nur**
den konfigurierten lokalen Test-Dispatcher, prüft 401/200, Identitäten,
Policy, Alias-Vorschauen, zwei winzige Modellanfragen und SQLite-v9-Logs.
Es schaltet danach seinen selbst gestarteten Prozess ab. Eine ältere SQLite-DB
wird vor der automatischen Schema-Migration mit SQLite sicher als `*.bak`
gesichert. Bei Fehlern bricht es ab, statt Prozesse zu übernehmen.

Deine vorhandene `C:\llama.cpp\clients.json` wird **nicht benötigt,
überschrieben oder gelöscht**. Sie ist für eine spätere echte
Client-Konfiguration gedacht. Für diesen technischen Test reichen automatisch
erzeugte Einmal-Schlüssel.

## Auf welchen Rechnern?

| Ort | Sinnvolle Nutzung |
| --- | --- |
| **Laptop / Windows** | **Jetzt:** S02-Testinstanz, ohne Goose/Open WebUI |
| Laptop / WSL | Optional später dieselben Tests; hier laufen deine echten Clients |
| Speedy / Windows | Erst später Strata-Anschluss (S03); **produktives Strata nicht anrühren** |
| Speedy / WSL | Nur wenn dort tatsächlich eine separate Testinstanz besteht |

Auf anderen Rechnern einfach die richtige `--instance` angeben und dort
das jeweilige lokale Testkommando konfigurieren. Es ist **kein** zentraler
Testlauf über Rechnergrenzen hinweg: jeder Rechner prüft seinen eigenen
Dispatcher und seine eigene SQLite-Datei.

**Die Ausgabe am Schluss genügt.** Bei FAIL die Ausgabe als `.log`-Datei
anhängen. Kein manuelles Kopieren ganzer Testprotokolle in den Chat nötig.

Details/Architektur: [S02-client-identities.md](S02-client-identities.md).
