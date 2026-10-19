"""S00 local-only start provenance; does not start, change or stop the Dispatcher.

Captures observed process command line where possible and pins the first observed
startup + instance configuration in a private, git-ignored baseline. Do not post
baseline files without inspection: they include local absolute paths and argv.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCH_ERROR = (
    "Cannot identify a running Dispatcher launched with --instance {instance}. "
    "Start the existing working Dispatcher first and confirm its --instance; "
    "if process inspection is unavailable, use --launch-command to record a "
    "USER-DECLARED start command (not verified against the running process)."
)


class ProvenanceError(ValueError):
    pass


def _require(condition: bool, explanation: str) -> None:
    if not condition:
        raise ProvenanceError(explanation)


def _argument(argv: list[str], flag: str) -> str | None:
    for idx, val in enumerate(argv):
        if val == flag and idx + 1 < len(argv):
            return argv[idx + 1]
        if val.startswith(flag + "="):
            return val[len(flag) + 1:]
    return None


def _matches(instance: str, argv: list[str]) -> bool:
    return (
        any(Path(x.replace("\\", "/")).name.lower() == "dispatcher.py" for x in argv)
        and "serve" in argv
        and _argument(argv, "--instance") == instance
    )


def _linux_candidates(instance: str) -> list[dict]:
    found = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            raw = (proc / "cmdline").read_bytes()
            argv = [x.decode("utf-8", errors="replace")
                    for x in raw.split(b"\x00") if x]
            if not _matches(instance, argv):
                continue
            # Prefer the real Python Dispatcher process to uv's parent.
            exe = Path(argv[0]).name.lower()
            if not (exe.startswith("python") or exe == "dispatcher.py"):
                continue
            cwd = os.readlink(proc / "cwd")
            found.append({
                "pid": int(proc.name),
                "command": shlex.join(argv),
                "argv": argv,
                "cwd": cwd,
                "capture": "procfs_python_argv",
            })
        except (OSError, PermissionError):
            continue
    return found


def _windows_candidates(instance: str) -> list[dict]:
    # CommandLine is sourced from OS process metadata, not reconstructed from
    # config or assumed from a README. No remote calls or shell interpolation.
    ps = (
        "$ErrorActionPreference = 'Stop'; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -match '^python(\\d+)?(w)?\\.exe$' "
        "-and $_.CommandLine -like '*dispatcher.py*' } | "
        "Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if completed.returncode != 0:
        return []
    raw = completed.stdout.strip()
    if not raw:
        return []
    result = json.loads(raw)
    rows = result if isinstance(result, list) else [result]
    found = []
    # Windows process CommandLine may contain quotes around paths and values.
    expected = re.compile(
        r'(?<!\S)--instance(?:=|\s+)(?:"' + re.escape(instance) +
        r'"|' + re.escape(instance) + r')(?=\s|$)'
    )
    for row in rows:
        cmd = row.get("CommandLine") or ""
        if ("dispatcher.py" in cmd and re.search(r"(?<!\S)serve(?=\s|$)", cmd)
                and expected.search(cmd)):
            ensemble = re.search(r'(?<!\S)--ensemble(?:=|\s+)(?:"([^"]+)"|([^\s]+))', cmd)
            found.append({
                "pid": row.get("ProcessId"),
                "command": cmd,
                "capture": "win32_process_commandline",
                "ensemble": next((x for x in ensemble.groups() if x), None)
                if ensemble else None,
            })
    return found


def _windows_listener_pids(port: int) -> set[int]:
    """Read the owner(s) of the local listening TCP socket, never touch them.

    Only used to disambiguate multiple Python launchers for the same instance,
    e.g. the Windows Python virtualenv redirector and its real child process.
    """
    _require(1 <= port <= 65535, "Invalid Dispatcher proxy port for process lookup.")
    ps = (
        "$ErrorActionPreference = 'Stop'; "
        f"$ids = @(Get-NetTCPConnection -State Listen -LocalPort {port} "
        "| Select-Object -ExpandProperty OwningProcess -Unique); "
        "ConvertTo-Json -InputObject $ids -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if proc.returncode != 0:
        return set()
    try:
        payload = json.loads(proc.stdout)
    except (ValueError, TypeError):
        return set()
    if isinstance(payload, int):
        payload = [payload]
    if not isinstance(payload, list):
        return set()
    # Ignore system PID 0 and malformed output, without exposing other processes.
    return {int(x) for x in payload if isinstance(x, int) and x > 0}


def _select_windows_candidate(candidates: list[dict], port: int | None) -> dict:
    """Select only the Python process that owns the Dispatcher proxy socket.

    Never infer ownership from parent/child proximity or simply choose the
    first matching process. Other same-instance processes may be legitimate.
    """
    if len(candidates) == 1:
        return candidates[0]
    _require(bool(candidates), "No matching Python Dispatcher process found.")
    _require(port is not None,
             "Several Python processes use this instance. Specify a local "
             "Dispatcher proxy port for safe TCP-listener ownership checks.")
    owners = _windows_listener_pids(port)
    matches = [c for c in candidates if c.get("pid") in owners]
    _require(len(matches) == 1,
             f"Found {len(candidates)} matching Python processes, but could "
             f"not uniquely match one to the TCP listener on port {port}. "
             "No process was stopped. Check Get-NetTCPConnection "
             f"-LocalPort {port} -State Listen and the owning Python process. "
             "If the listener cannot be resolved, --launch-command can "
             "record your manually confirmed startup as unverified.")
    selected = dict(matches[0])
    selected["capture"] = "win32_tcp_listener_process"
    return selected


def _declared(instance: str, command: str) -> dict:
    # Operator-supplied Windows command is not roundtripped through POSIX shlex.
    match = re.search(r'(?<!\S)--instance(?:=|\s+)(?:"([^"]+)"|([^\s]+))', command)
    value = next((x for x in match.groups() if x), None) if match else None
    _require(value == instance, f"Declared command must use --instance {instance}.")
    _require("dispatcher.py" in command and re.search(r"(?<!\S)serve(?=\s|$)", command),
             "Declared command must be a Dispatcher serve invocation.")
    match = re.search(r'(?<!\S)--ensemble(?:=|\s+)(?:"([^"]+)"|([^\s]+))', command)
    ensemble = next((x for x in match.groups() if x), None) if match else None
    _require(bool(ensemble), "S00 live smoke currently requires --ensemble NAME.")
    return {"command": command, "capture": "user_declared_unverified",
            "ensemble": ensemble}


def find_launch(instance: str, declared_command: str | None = None,
                proxy_port: int | None = None) -> dict:
    try:
        candidates = (
            _windows_candidates(instance) if os.name == "nt"
            else _linux_candidates(instance)
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        candidates = []

    if len(candidates) > 1:
        if os.name == "nt":
            try:
                captured = _select_windows_candidate(candidates, proxy_port)
            except ProvenanceError:
                if declared_command:
                    # Only explicit opt-in, accurately labelled as unverified.
                    # Never imply that an arbitrary Python process owns the port.
                    return _declared(instance, declared_command)
                raise
        else:
            if declared_command:
                return _declared(instance, declared_command)
            raise ProvenanceError(
                f"Multiple running Dispatcher Python processes use --instance "
                f"{instance}; cannot identify the proxy owner automatically. "
                "No process was stopped.")
    else:
        captured = candidates[0] if candidates else None

    if captured:
        if declared_command:
            # Compare semantic required options; never claim exact byte-for-byte
            # equality of Windows shell quoting with Win32 process argv.
            asserted = _declared(instance, declared_command)
            observed_ensemble = (
                _argument(captured["argv"], "--ensemble")
                if "argv" in captured else captured.get("ensemble")
            )
            _require(asserted["ensemble"] == observed_ensemble,
                     "Observed ensemble differs from --launch-command.")
        return captured
    _require(bool(declared_command), LAUNCH_ERROR.format(instance=instance))
    return _declared(instance, declared_command)


def _git_head(folder: Path) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(folder), "rev-parse", "--verify", "HEAD"],
                           capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def config_snapshot(instance: str, ensemble: str) -> dict:
    folder = ROOT / "instances" / instance
    _require(folder.is_dir(), f"Instance folder is missing: instances/{instance}. "
             "Check out the correct instance repository BEFORE starting Dispatcher.")
    _require((folder / "instance.yaml").is_file(),
             f"Missing instances/{instance}/instance.yaml.")
    target = folder / "ensembles" / (ensemble + ".yaml")
    _require(target.is_file(), f"Missing ensemble instances/{instance}/ensembles/{ensemble}.yaml. "
             "The new Windows/WSL instance rename may not be finished.")
    files = sorted(
        [folder / "instance.yaml"] +
        [x for section in ("ensembles", "profiles", "engines")
         for x in (folder / section).glob("*.yaml")]
    )
    items = {str(path.relative_to(folder)).replace("\\", "/"):
             hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    digest = hashlib.sha256(
        json.dumps(items, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "core_commit": _git_head(ROOT),
        "instance_commit": _git_head(folder),
        "instance_yaml_sha256": digest,
        "yaml_count": len(items),
    }


def pin_startup(instance: str, report_dir: Path, declared_command: str | None,
                proxy_port: int | None = None) -> dict:
    """Pin baseline on first run; subsequent runs fail for changed launch/config.

    Report contains only SHA256, source and git revision; complete argv stays
    in local *.baseline.json, never in the shareable smoke report.
    """
    launch = find_launch(instance, declared_command, proxy_port=proxy_port)
    ensemble = (
        _argument(launch["argv"], "--ensemble")
        if "argv" in launch else launch.get("ensemble")
    )
    _require(bool(ensemble), "Running Dispatcher has no --ensemble parameter.")
    snapshot = config_snapshot(instance, ensemble)
    manifest = {
        "schema": "s00-start-v1",
        "instance": instance,
        "ensemble": ensemble,
        "command": launch["command"],
        "capture": launch["capture"],
        **snapshot,
    }
    path = report_dir / f"s00-{instance}.baseline.json"
    report_dir.mkdir(parents=True, exist_ok=True)
    if path.exists():
        baseline = json.loads(path.read_text(encoding="utf-8"))
        # The precise observed command may include the Python interpreter's
        # absolute path, so exact comparison is useful for reproducibility.
        keys = ("schema", "instance", "ensemble", "command",
                "core_commit", "instance_commit", "instance_yaml_sha256")
        changed = [key for key in keys if baseline.get(key) != manifest.get(key)]
        _require(not changed,
                 "Start/config baseline changed (" + ", ".join(changed) +
                 "). Review the local .baseline.json and use --rebaseline "
                 "only when you intentionally accept a new baseline.")
    else:
        # Restrictive permissions where the host honors POSIX mode.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"first_recorded_utc": datetime.now(timezone.utc).isoformat(),
                       **manifest}, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    return {
        "status": "PASS",
        "capture": launch["capture"],
        "ensemble": ensemble,
        "command_sha256": hashlib.sha256(
            launch["command"].encode("utf-8")).hexdigest(),
        "core_commit": snapshot["core_commit"],
        "instance_commit": snapshot["instance_commit"],
        "instance_yaml_sha256": snapshot["instance_yaml_sha256"],
        "yaml_count": snapshot["yaml_count"],
        "baseline_file": path.name,
    }


def rebaseline_startup(instance: str, report_dir: Path,
                       declared_command: str | None,
                       proxy_port: int | None = None) -> dict:
    """Explicit baseline refresh, never automatic."""
    launch = find_launch(instance, declared_command, proxy_port=proxy_port)
    ensemble = (
        _argument(launch["argv"], "--ensemble")
        if "argv" in launch else launch.get("ensemble")
    )
    _require(bool(ensemble), "Running Dispatcher has no --ensemble parameter.")
    snapshot = config_snapshot(instance, ensemble)
    path = report_dir / f"s00-{instance}.baseline.json"
    report_dir.mkdir(parents=True, exist_ok=True)
    # Do not silently overwrite old baseline: save it as a timestamped copy.
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path.rename(report_dir / f"s00-{instance}.{stamp}.baseline.json")
    return pin_startup(instance, report_dir, declared_command, proxy_port=proxy_port)
