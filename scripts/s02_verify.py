"""S02: one reusable test runner, host-specific launch captured separately.

No real Goose/Open WebUI/Strata needed. A running local Dispatcher can be
inspected without changes. With --save-start, an owner intentionally records its
observed OS process argv into an ignored, local reports/s02-*.launch.json.
--start can then run ONLY this previously captured, explicitly selected
test Dispatcher; it never takes over an existing listener.
"""
from __future__ import annotations

import argparse
from collections import deque
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
sys.path.insert(0, str(ROOT / "scripts"))
from s00_provenance import find_launch, ProvenanceError  # noqa: E402

_INSTANCE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
DEFAULT_URL = "http://127.0.0.1:8001"



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


def manual_fixture_paths(instance: str) -> tuple[Path, Path]:
    """Persistent only across the manual start/check steps; never checked in."""
    require(bool(_INSTANCE_RE.fullmatch(instance)), "Invalid instance name.")
    folder = ROOT / "reports"
    return (
        folder / f"s02-{instance}.manual-clients.json",
        folder / f"s02-{instance}.manual-secrets.json",
    )


def _write_private_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(obj, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def prepare_manual(instance: str, url: str) -> None:
    """Set up disposable clients without starting/stopping the native engine."""
    require(not is_listening(url),
            "The Dispatcher port is occupied. Stop your existing *test* "
            "Dispatcher yourself before preparing the manual authentication test.")
    config_path, secrets_path = manual_fixture_paths(instance)
    require(not config_path.exists() and not secrets_path.exists(),
            "A manual test configuration already exists. Use --verify-manual "
            "or --cleanup-manual before creating another.")
    raw = {
        "goose": secrets.token_urlsafe(48),
        "open-webui": secrets.token_urlsafe(48),
    }
    client_config = {
        "schema_version": 1,
        "clients": [
            {"id": name, "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
             "policy": "enforce" if name == "goose" else "default"}
            for name, token in raw.items()
        ],
    }
    _write_private_json(config_path, client_config)
    try:
        _write_private_json(secrets_path, {
            "schema_version": 1, "instance": instance, "url": url, "tokens": raw,
        })
    except Exception:
        config_path.unlink(missing_ok=True)
        raise
    print("  Two disposable clients prepared. No service was started.")
    print("  In the PowerShell terminal where you normally launch the Dispatcher:")
    print(f"  $env:DISPATCHER_CLIENT_CONFIG = '{str(config_path).replace(chr(39), chr(39)*2)}'")
    print("  Then run your NORMAL working 'uv run src/dispatcher.py serve ...' command.")
    print("  Keep this Dispatcher running. In a SECOND PowerShell terminal run:")
    command = f"uv run --frozen python scripts/s02_verify.py --instance {instance}"
    if url != DEFAULT_URL:
        command += f" --base-url {url}"
    print(f"  {command} --verify-manual --inference")
    print("  This sends two tiny real model requests and verifies both client IDs in SQLite.")
    print("  The two disposable secrets remain local in Git-ignored reports/ until cleanup.")


def load_manual(instance: str, url: str) -> dict[str, str]:
    config_path, secrets_path = manual_fixture_paths(instance)
    require(config_path.is_file() and secrets_path.is_file(),
            "No prepared manual test. Use --prepare-manual before starting the Dispatcher.")
    try:
        credentials = json.loads(secrets_path.read_text(encoding="utf-8"))
        doc = json.loads(config_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise CheckError("Manual test configuration is unreadable.") from exc
    tokens = credentials.get("tokens")
    require(credentials.get("schema_version") == 1
            and credentials.get("instance") == instance
            and credentials.get("url") == url
            and isinstance(tokens, dict)
            and set(tokens) == {"goose", "open-webui"}
            and all(isinstance(v, str) and len(v) >= 40 for v in tokens.values()),
            "Manual test credentials are invalid or not for this instance/port.")
    require(doc.get("schema_version") == 1 and isinstance(doc.get("clients"), list),
            "Manual test client digest file is invalid.")
    for name, token in tokens.items():
        wanted = hashlib.sha256(token.encode()).hexdigest()
        require(any(x.get("id") == name and x.get("token_sha256") == wanted
                    for x in doc["clients"] if isinstance(x, dict)),
                "Manual test token does not match the configured credential digest.")
    return tokens


def cleanup_manual(instance: str) -> None:
    """Remove disposable local tokens/config only; never touch the Dispatcher."""
    paths = manual_fixture_paths(instance)
    for p in paths:
        p.unlink(missing_ok=True)
    print("  Manual S02 test credentials removed from local reports/ (not secure erasure).")
    print("  No running process was stopped or modified.")


def check_command(command: list[str], instance: str) -> None:
    require(isinstance(command, list) and all(isinstance(x, str) and x for x in command),
            "Saved start command must be a non-empty argv list.")
    executable = Path(command[0]).name.lower()
    require(executable.startswith("python") and
            (executable.endswith(".exe") if os.name == "nt"
             else executable.rstrip("0123456789.") == "python"),
            "Only a directly observed Python interpreter may be started.")
    scripts = [x for x in command if Path(x).name.lower() == "dispatcher.py"]
    require(len(scripts) == 1, "Expected exactly one Dispatcher Python script.")
    expected = (ROOT / "src" / "dispatcher.py").resolve()
    observed = Path(scripts[0])
    if not observed.is_absolute():
        observed = ROOT / observed
    require(observed.resolve() == expected,
            "Captured command references a different Dispatcher checkout.")
    require("serve" in command, "Only a test Dispatcher 'serve' command is allowed.")
    require("--instance" in command and command[command.index("--instance")+1:
                                              command.index("--instance")+2] == [instance],
            "The start command must explicitly select the same --instance.")
    require("--ensemble" in command or "--profile" in command,
            "Expected your existing --ensemble or --profile.")
    forbidden = {"--launch-command", "--rebaseline", "--api-key", "--password",
                 "--client-secret", "--auth-token", "--token", "--secret"}
    require(not any(x.split("=")[0] in forbidden for x in command),
            "Refusing to save startup commands with secret-bearing flags.")
    require(not any("strata" in part.lower() or "caddy" in part.lower()
                    for part in command), "Never start Strata/Caddy from S02 runner.")


def launch_file(instance: str) -> Path:
    require(bool(_INSTANCE_RE.fullmatch(instance)), "Invalid instance name.")
    return ROOT / "reports" / f"s02-{instance}.launch.json"


def split_captured_command(captured: dict) -> list[str]:
    """Return executable/argv without a shell. Windows uses native argv rules."""
    if "argv" in captured:
        return list(captured["argv"])
    require(os.name == "nt" and isinstance(captured.get("command"), str),
            "The operating system did not provide executable arguments.")
    import ctypes
    from ctypes import wintypes

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    parse = shell.CommandLineToArgvW
    parse.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    parse.restype = ctypes.POINTER(wintypes.LPWSTR)
    count = ctypes.c_int(0)
    pointer = parse(captured["command"], ctypes.byref(count))
    require(bool(pointer), "Could not decode Windows process arguments.")
    try:
        return [pointer[i] for i in range(count.value)]
    finally:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        free = kernel.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(ctypes.cast(pointer, ctypes.c_void_p))


def save_start(instance: str, url: str) -> None:
    """Explicitly store the already running *local* Python invocation."""
    require(is_listening(url), "Start your existing test Dispatcher first.")
    _, port = endpoint(url)
    try:
        captured = find_launch(instance, proxy_port=port)
    except ProvenanceError as exc:
        raise CheckError(str(exc)) from None
    require(captured.get("capture") != "user_declared_unverified",
            "A verified OS process command is required.")
    command = split_captured_command(captured)
    check_command(command, instance)
    dest = launch_file(instance)
    dest.parent.mkdir(exist_ok=True)
    manifest = {
        "schema": "s02-test-start-v1", "instance": instance, "url": url,
        "argv": command, "captured_utc": datetime.now(timezone.utc).isoformat(),
    }
    fd = os.open(dest, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(f"  Startup saved locally: {dest.name}")
    print("  No process was started or stopped. Stop your test Dispatcher before --start.")


def load_start(instance: str, url: str) -> list[str]:
    dest = launch_file(instance)
    require(dest.is_file(),
            "No saved start command. While your test Dispatcher is running, "
            "execute --save-start once; then stop it and run --start.")
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CheckError("Saved start command is unreadable or invalid.") from exc
    require(data.get("schema") == "s02-test-start-v1"
            and data.get("instance") == instance and data.get("url") == url,
            "Saved startup manifest does not match this instance and local URL.")
    command = data.get("argv")
    check_command(command, instance)
    return command


def dispatcher_log_path(instance: str) -> Path:
    """A durable, private, unique log path per explicit local S02 test run."""
    require(bool(_INSTANCE_RE.fullmatch(instance)), "Invalid instance name.")
    folder = ROOT / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return folder / f"s02-{instance}.dispatcher-{stamp}-{os.getpid()}.log"


def log_tail(path: Path, *, max_lines: int = 30, max_chars: int = 320) -> str:
    """Print a useful bounded excerpt; do not echo obvious secret headers."""
    if not path.is_file():
        return "(Dispatcher log file is missing.)"
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        lines = deque(stream, maxlen=max_lines)
    if not lines:
        return "(Dispatcher produced no output before exiting.)"
    safe = []
    for line in lines:
        value = line.rstrip("\r\n")[:max_chars]
        value = re.sub(
            r"(?i)(\b(?:authorization|api[-_]?key|token|password|secret)\b"
            r"\s*[:=]\s*(?:Bearer\s+)?)[^\s,;]+",
            r"\1<redacted>", value,
        )
        safe.append(value)
    return "\n".join(safe)


def replay_with_test_python(captured: list[str], instance: str) -> list[str]:
    """Use the Python environment that passed S02 unit tests.

    Process introspection can capture the *system* Python executable of an
    existing Dispatcher, while `uv run --frozen python` gives this runner a
    correctly provisioned virtualenv. Reusing the system executable would
    fail to import installed dependencies (e.g. PyYAML). Keep the captured
    script and flags verbatim, changing ONLY the interpreter executable.
    """
    check_command(captured, instance)
    # IMPORTANT: keep sys.executable verbatim. On Linux/WSL the venv Python
    # may be a symlink to the base interpreter. Path.resolve() follows that
    # symlink and would silently remove venv site-packages from the subprocess.
    current = Path(sys.executable)
    require(current.is_file(), "The current test Python interpreter is missing.")
    return [str(current), *captured[1:]]


def describe_captured_options(command: list[str]) -> dict[str, str | None]:
    """Read only operational selectors from saved argv, never print entire argv.

    These are the arguments captured from the already working dispatcher.
    Diagnostic only: unknown options and any potential credential material
    are not printed or modified. The replay keeps all argv[1:] verbatim.
    """
    values: dict[str, str | None] = {}
    for key in ("--instance", "--ensemble", "--profile", "--model-root"):
        value = next(
            (arg.split("=", 1)[1] for arg in command[1:]
             if arg.startswith(key + "=")),
            None,
        )
        if value is None and key in command:
            pos = command.index(key)
            if pos + 1 < len(command):
                value = command[pos + 1]
        values[key] = value
    return values


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
            raise CheckError(
                f"Test Dispatcher exited during startup (exit code {proc.returncode})."
            )
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
    parser.add_argument("--instance", required=True,
                        help="Your existing local Dispatcher instance name (e.g. Laptop_Win)")
    parser.add_argument("--base-url", default=DEFAULT_URL,
                        help="Local Dispatcher URL, normally http://127.0.0.1:8001")
    parser.add_argument("--save-start", action="store_true",
                        help="Capture the existing running test Dispatcher start command locally")
    parser.add_argument("--prepare-manual", action="store_true",
                        help="Generate private throwaway clients for your normal PowerShell start")
    parser.add_argument("--verify-manual", action="store_true",
                        help="Test an already-running, manually started authenticated Dispatcher")
    parser.add_argument("--cleanup-manual", action="store_true",
                        help="Remove temporary manual test credentials; never stop a process")
    parser.add_argument("--start", action="store_true",
                        help="Start ONLY your previously captured local test Dispatcher")
    parser.add_argument("--inference", action="store_true",
                        help="Send two small real model requests when --start is used")
    args = parser.parse_args()
    url = args.base_url.rstrip("/")
    try:
        require(bool(_INSTANCE_RE.fullmatch(args.instance)), "Invalid instance name.")
        endpoint(url)
        mode_count = sum(bool(x) for x in (
            args.save_start, args.prepare_manual, args.verify_manual,
            args.cleanup_manual, args.start,
        ))
        require(mode_count <= 1, "Select only one S02 execution mode.")
        require(not args.inference or args.start or args.verify_manual,
                "--inference is supported only with --start or --verify-manual.")
        print(f"S02 verification: {args.instance} (local Dispatcher, not Strata)")
        if args.cleanup_manual:
            cleanup_manual(args.instance)
            print("S02 MANUAL CONFIG CLEANED")
            return 0
        unit_tests()
        if args.prepare_manual:
            prepare_manual(args.instance, url)
            print("S02 MANUAL AUTH READY")
            return 0
        if args.verify_manual:
            tokens = load_manual(args.instance, url)
            require(is_listening(url), "Start the local Dispatcher yourself first.")
            verify_identity(url, tokens, args.inference)
            verify_sqlite(args.instance, require_clients=args.inference)
            print("S02 PASS — manually started Dispatcher, two independent client IDs")
            print("  When finished, stop the Dispatcher yourself. Clean up in PowerShell:")
            cleanup = f"uv run --frozen python scripts/s02_verify.py --instance {args.instance}"
            if url != DEFAULT_URL:
                cleanup += f" --base-url {url}"
            print(f"  {cleanup} --cleanup-manual")
            return 0
        if args.save_start:
            save_start(args.instance, url)
            print("S02 START COMMAND SAVED")
            return 0
        require(args.start or not args.inference,
                "--inference requires --start to verify both temporary clients.")
        if args.start:
            captured = load_start(args.instance, url)
            command = replay_with_test_python(captured, args.instance)
            print(f"  Dispatcher test Python: {command[0]}")
            captured_opts = describe_captured_options(captured)
            for name, value in captured_opts.items():
                if value is not None:
                    print(f"  Captured {name}: {value}")
            if captured_opts["--model-root"] is None:
                print("  Note: captured command contains no --model-root override.")
            print("  Replay: all captured Dispatcher flags are unchanged; "
                  "test authentication, console I/O and process group differ.")
            require(not is_listening(url),
                    "Port is occupied: stop your EXISTING *test* Dispatcher yourself. "
                    "This script will never take over another process.")
            backup_old_database(args.instance)
            log_path = dispatcher_log_path(args.instance)
            print(f"  Dispatcher console log: {log_path}", flush=True)
            with tempfile.TemporaryDirectory(prefix="s02-private-") as folder:
                directory = Path(folder)
                tokens = auth_fixture(directory)
                env = os.environ.copy()
                env["DISPATCHER_CLIENT_CONFIG"] = str(directory / "clients.json")
                # Python stdout is fully buffered when redirected to a file;
                # force immediate logging, especially for fast startup crashes.
                env["PYTHONUNBUFFERED"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"
                try:
                    with log_path.open("x", encoding="utf-8") as log:
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
                except Exception:
                    # After the child has exited, the log handle is closed and
                    # its last lines are available even on Windows.
                    print("  Dispatcher log — last 30 lines:", file=sys.stderr)
                    print(log_tail(log_path), file=sys.stderr)
                    print(f"  Full local log: {log_path}", file=sys.stderr)
                    raise
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
