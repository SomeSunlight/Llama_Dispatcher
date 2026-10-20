"""S02: one-command, owner-safe verification of client identities.

Edit the CONFIG block once per host. No real Goose/Open WebUI/Strata needed.
Default mode NEVER starts/stops a process. Optional isolated mode launches ONLY
a specifically configured llama.cpp test Dispatcher on a free loopback port.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

# =========== USER CONFIGURATION: CHANGE ONLY THIS BLOCK =====================
# Run with: uv run --frozen python scripts/s02_verify.py --instance Laptop_Win
# start_command=None: inspect your ALREADY running local Dispatcher; no stops.
# To activate the fully automatic, isolated authenticated end-to-end stage,
# set the list to your EXISTING laptop llama.cpp startup argv, then add --start.
# Never configure a productive Speedy Strata/Caddy process as start_command.
MACHINES = {
    "Laptop_Win": {"url": "http://127.0.0.1:8001", "start_command": None},
    "Laptop_WSL": {"url": "http://127.0.0.1:8001", "start_command": None},
    "Speedy_Win": {"url": "http://127.0.0.1:8001", "start_command": None},
    "Speedy_WSL": {"url": "http://127.0.0.1:8001", "start_command": None},
}
# Optional isolated start_command example (one argv element per quoted string):
# ["uv", "run", "--frozen", "python", "src/dispatcher.py", "serve",
#  "--ensemble", "YOUR_EXISTING_ENSEMBLE", "--instance", "Laptop_Win",
#  "--model-root", r"C:\\YOUR_EXISTING_MODEL_ROOT", "--bin-dir", r"C:\\YOUR_BIN_DIR"]
# ===========================================================================


class CheckError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def endpoint(url: str) -> tuple[str, int]:
    from urllib.parse import urlsplit
    p = urlsplit(url)
    require(p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost", "::1")
            and p.port is not None and p.path in ("", "/")
            and not p.username and not p.password and not p.query and not p.fragment,
            "Only a local Dispatcher URL (http://127.0.0.1:PORT) is allowed.")
    return (p.hostname, p.port)


def is_listening(url: str) -> bool:
    host, port = endpoint(url)
    try:
        with socket.create_connection((host, port), timeout=0.7):
            return True
    except OSError:
        return False


def auth_fixture(folder: Path) -> dict[str, str]:
    """Unique one-time identities and private digest-only configuration."""
    raw = {"goose": secrets.token_urlsafe(48),
           "open-webui": secrets.token_urlsafe(48)}
    doc = {
        "schema_version": 1,
        "clients": [
            {"id": name, "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
             "policy": mode}
            for (name, token), mode in zip(raw.items(), ("enforce", "default"))
        ],
    }
    path = folder / "clients.json"
    with path.open("x", encoding="utf-8") as fd:
        json.dump(doc, fd)
    if os.name == "posix":
        path.chmod(0o600)
    return raw


def check_command(command: list[str], instance: str) -> None:
    require(isinstance(command, list) and all(isinstance(x, str) and x for x in command),
            "start_command must be a non-empty argv list, not a shell command.")
    require("src/dispatcher.py" in [x.replace("\\", "/") for x in command],
            "Only the repository's src/dispatcher.py is accepted for auto-start.")
    require("serve" in command, "Only a test Dispatcher 'serve' command is allowed.")
    require("--instance" in command and command[command.index("--instance")+1:
                                              command.index("--instance")+2] == [instance],
            "The start command must explicitly select the same --instance.")
    require("--ensemble" in command or "--profile" in command,
            "Specify your EXISTING --ensemble or --profile.")
    require(not any(part in command for part in ("--launch-command", "--rebaseline")),
            "Startup must not suppress provenance checks.")
    require(not any("strata" in part.lower() or "caddy" in part.lower()
                    for part in command), "Never start Strata/Caddy from S02 runner.")


def http_json(url: str, route: str, token: str | None = None,
              body: dict | None = None, timeout: int = 15) -> tuple[int, dict]:
    raw = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(url.rstrip("/") + route, data=raw, method="POST" if body is not None else "GET",
                  headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return (resp.status, json.load(resp))
    except HTTPError as exc:
        try:
            return (exc.code, json.load(exc))
        except ValueError:
            return (exc.code, {})
    except (URLError, OSError, TimeoutError) as exc:
        raise CheckError(f"Local Dispatcher is not reachable ({type(exc).__name__}).") from None


def verify_identity(url: str, tokens: dict[str, str],
                    run_inference: bool) -> None:
    unauth, _ = http_json(url, "/v1/models")
    require(unauth == 401, "Missing bearer credential should yield HTTP 401.")
    spoof_req = Request(url.rstrip("/") + "/v1/models",
                        headers={"X-Client-ID": "goose", "X-Forwarded-User": "goose"})
    try:
        urlopen(spoof_req, timeout=10)
        raise CheckError("Spoofed X-Client-ID unexpectedly passed authentication.")
    except HTTPError as exc:
        require(exc.code == 401, "Spoofed identity was not rejected with HTTP 401.")
    checked = {}
    for name, token in tokens.items():
        status, models = http_json(url, "/v1/models", token)
        require(status == 200 and models.get("data"),
                f"{name}: authenticated model list unavailable.")
        alias = models["data"][0]["id"]
        status, result = http_json(url, "/debug/preview", token, {
            "model": alias, "temperature": 0.91, "messages": [
                {"role": "user", "content": "S02 private synthetic test content"}
            ],
        })
        require(status == 200, f"{name}: authenticated preview unavailable.")
        require(result.get("policy_mode") == ("enforce" if name == "goose" else "default"),
                f"{name}: wrong policy mode.")
        require(result.get("forwarded_body", {}).get("messages") == "<redacted>",
                f"{name}: preview exposed synthetic conversation content.")
        checked[name] = alias
    print("  Auth: PASS (two clients, invalid token, spoofed header, preview and policies)")
    if run_inference:
        for name, token in tokens.items():
            status, data = http_json(url, "/v1/chat/completions", token, {
                "model": checked[name], "messages": [
                    {"role": "user", "content": "S02 synthetic test"}
                ], "max_tokens": 3, "stream": False,
            }, timeout=300)
            require(status == 200 and isinstance(data.get("choices"), list),
                    f"{name}: tiny inference failed (HTTP {status}).")
        print("  Inference: PASS (two clients, 3-token responses)")
    else:
        print("  Inference: SKIP (explicit --inference required)")


def verify_sqlite(instance: str, require_clients: bool) -> None:
    db = ROOT / "instances" / instance / "data" / "metrics.db"
    require(db.is_file(), "Instance metrics.db missing; cannot verify persisted identity.")
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        v = conn.execute("PRAGMA user_version").fetchone()[0]
        require(v == 9, f"Expected SQLite schema v9, observed v{v}.")
        cols = {x[1] for x in conn.execute("PRAGMA table_info(metrics_proxy_requests)")}
        require({"client_id", "policy_mode"}.issubset(cols), "Missing client audit columns.")
        if require_clients:
            recent = list(conn.execute(
                "SELECT DISTINCT client_id FROM metrics_proxy_requests "
                "WHERE client_id IS NOT NULL ORDER BY id DESC LIMIT 20"
            ))
            names = {row[0] for row in recent}
            require({"goose", "open-webui"}.issubset(names),
                    "Test requests from both clients were not found in SQLite.")
    print("  SQLite: PASS (schema v9" +
          (", both client identities" if require_clients else "") + ")")


def unit_tests() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if proc.returncode:
        tail = (proc.stdout + "\n" + proc.stderr).splitlines()[-85:]
        print("\n".join(tail), file=sys.stderr)
    require(proc.returncode == 0, "Unit tests failed (see details above).")
    count = re.search(r"Ran (\d+) tests?", proc.stderr + proc.stdout)
    print(f"  Unit tests: PASS ({count.group(1) if count else '?'} tests)")


def wait_for_server(url: str, proc: subprocess.Popen, token: str,
                    timeout: int = 300) -> None:
    """Wait for a real configured model, not merely the open HTTP listener."""
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if proc.poll() is not None:
            raise CheckError("Test Dispatcher exited during startup; inspect its local process log.")
        if is_listening(url):
            try:
                status, data = http_json(url, "/v1/models", token, timeout=3)
                if status == 200 and data.get("data"):
                    return
            except (CheckError, ValueError):
                pass
        time.sleep(1)
    raise CheckError("Dispatcher did not report a ready model within startup timeout.")


def backup_old_database(instance: str) -> None:
    db = ROOT / "instances" / instance / "data" / "metrics.db"
    if not db.exists():
        return
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        current = src.execute("PRAGMA user_version").fetchone()[0]
        if current >= 9:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = db.with_name(f"metrics.before-s02-{stamp}.bak")
        require(not destination.exists(), "Backup name collision; retry later.")
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            require(dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                    "Database backup integrity failed.")
    print(f"  Database backup: {destination.name} (online SQLite backup)")


def stop_our_process(proc: subprocess.Popen, url: str, token: str | None) -> None:
    if proc.poll() is not None:
        return
    if token:
        # Graceful existing /stop API shuts down the child model first.
        try:
            http_json(url, "/stop", token, {}, timeout=8)
        except (CheckError, ValueError):
            pass
    if os.name == "nt":
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except OSError:
            proc.terminate()
    else:
        try:
            os.killpg(proc.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="S02: easy, cross-platform client verification")
    parser.add_argument("--instance", required=True, choices=sorted(MACHINES))
    parser.add_argument("--start", action="store_true",
                        help="Launch ONLY the configured local test Dispatcher with throwaway clients")
    parser.add_argument("--inference", action="store_true",
                        help="Send two small real model requests when --start is used")
    args = parser.parse_args()
    config = MACHINES[args.instance]
    url = config["url"]
    try:
        endpoint(url)
        print(f"S02 verification: {args.instance} (local Dispatcher, not Strata)")
        unit_tests()
        require(args.start or not args.inference,
                "--inference requires --start to verify both temporary clients.")
        if args.start:
            command = config["start_command"]
            require(command is not None, "Set start_command in the top config block first.")
            check_command(command, args.instance)
            require(not is_listening(url),
                    "Port is occupied: stop your EXISTING *test* Dispatcher yourself. "
                    "This script will never take over another process.")
            backup_old_database(args.instance)
            with tempfile.TemporaryDirectory(prefix="s02-private-") as folder:
                directory = Path(folder)
                tokens = auth_fixture(directory)
                env = os.environ.copy()
                env["DISPATCHER_CLIENT_CONFIG"] = str(directory / "clients.json")
                with (directory / "dispatcher.log").open("w", encoding="utf-8") as log:
                    proc = subprocess.Popen(command, cwd=ROOT, env=env,
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                            start_new_session=os.name != "nt")
                    try:
                        wait_for_server(url, proc, tokens["goose"])
                        verify_identity(url, tokens, args.inference)
                        if args.inference:
                            verify_sqlite(args.instance, require_clients=True)
                        else:
                            verify_sqlite(args.instance, require_clients=False)
                    finally:
                        stop_our_process(proc, url, tokens["goose"])
            print("  Test Dispatcher: stopped (only the process started by this script)")
        else:
            require(is_listening(url),
                    "No local Dispatcher running. Start your existing test Dispatcher "
                    "normally, or configure start_command and use --start.")
            status, _ = http_json(url, "/v1/models")
            require(status in (200, 401),
                    f"Dispatcher model listing returned unexpected HTTP {status}.")
            print("  Live HTTP: PASS (existing local server; no process changes)")
            if status == 200:
                verify_sqlite(args.instance, require_clients=False)
                print("  Auth live test: SKIP (server is in legacy mode)")
            else:
                print("  Auth live test: SKIP (authenticated server; use --start for "
                      "self-contained throwaway credentials)")
        print("S02 PASS")
        return 0
    except (CheckError, OSError, sqlite3.Error, ValueError) as exc:
        print(f"S02 FAIL — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
