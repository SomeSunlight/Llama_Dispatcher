"""S00 owner smoke runner: repeatable, local-only and non-destructive.

Default: run all unit tests, inspect an ALREADY running Dispatcher over loopback,
and save a sanitized JSON result. Never starts/stops an engine or changes configs.
--inference explicitly opts into two tiny real inference calls.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request
from urllib.parse import urlsplit

from s00_provenance import ProvenanceError, pin_startup, rebaseline_startup

ROOT = Path(__file__).resolve().parents[1]
PROBE_PROMPT = "S00 synthetic test"
PROBE_TEMPERATURE = 0.913
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


class SmokeFailure(Exception):
    """An expected, human-actionable smoke-test failure."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise SmokeFailure(message)


def validate_base_url(base_url: str) -> str:
    url = urlsplit(base_url)
    require(url.scheme == "http" and url.hostname in LOOPBACK,
            "Use a local http://127.0.0.1:PORT URL (never public Caddy/Strata).")
    require(not url.username and not url.password and not url.query and not url.fragment,
            "URL credentials, queries and fragments are not accepted.")
    require(url.path in ("", "/"), "Supply the Dispatcher root URL, without /v1.")
    require(url.port is not None, "Specify the Dispatcher proxy port explicitly.")
    return base_url.rstrip("/")


def http_json(base_url: str, method: str, route: str, payload: dict | None,
              timeout: float) -> dict:
    content = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(
        base_url + route,
        data=content,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            require(resp.status == 200, f"{route} returned HTTP {resp.status}.")
            parsed = json.load(resp)
    except error.HTTPError as exc:
        raise SmokeFailure(f"{route} returned HTTP {exc.code}. Check the Dispatcher proxy port.") from None
    except (error.URLError, TimeoutError, OSError) as exc:
        raise SmokeFailure(f"{route} could not be reached ({type(exc).__name__}). "
                           "Is the llama.cpp Dispatcher already running on this port?") from None
    except (ValueError, UnicodeDecodeError):
        raise SmokeFailure(f"{route} did not return valid JSON.") from None
    require(isinstance(parsed, dict), f"{route} returned a non-object JSON value.")
    return parsed


def preview_payload(alias: str) -> dict:
    return {
        "model": alias,
        "messages": [{"role": "user", "content": PROBE_PROMPT}],
        "temperature": PROBE_TEMPERATURE,
        "chat_template_kwargs": {"enable_thinking": True, "s00_synthetic": True},
        "max_tokens": 3,
        "stream": False,
    }


def inspect_live(send) -> tuple[dict, str]:
    """Verify public aliases, preview semantics and pass-through for ALL aliases.

    send(method, route, payload) is injectable for deterministic mock-based tests.
    No real inference or administrative HTTP endpoints are invoked here.
    """
    models = send("GET", "/v1/models", None)
    config = send("GET", "/debug/config", None)
    require(models.get("object") == "list" and isinstance(models.get("data"), list),
            "/v1/models does not have the expected OpenAI-compatible list shape.")
    ids = [item.get("id") for item in models["data"] if isinstance(item, dict)]
    require(ids and len(ids) == len(models["data"]) and
            all(isinstance(x, str) and x for x in ids) and len(set(ids)) == len(ids),
            "No usable unique aliases were returned by /v1/models.")
    require(config.get("status") == "running" and config.get("llama_port") is not None,
            "Dispatcher is not running a llama.cpp backend yet (/debug/config).")
    rows = config.get("aliases")
    require(isinstance(rows, list) and all(isinstance(x, dict) for x in rows),
            "/debug/config returned an unexpected aliases structure.")
    by_alias = {row.get("alias"): row for row in rows}
    require(len(by_alias) == len(rows) and set(ids) == set(by_alias),
            "/v1/models and /debug/config advertise different aliases.")

    count_proxy_only = 0
    for alias in ids:
        entry = by_alias[alias]
        target = entry.get("target")
        if target:
            require(target in ids, f"Alias {alias!r} targets a missing public model.")
            count_proxy_only += 1
        policy = entry.get("injected_params", {})
        require(isinstance(policy, dict), f"Policy for {alias!r} is not an object.")
        original = preview_payload(alias)
        result = send("POST", "/debug/preview", original)
        require(result.get("original_model") == alias and
                result.get("forwarded_model") == (target or alias) and
                result.get("alias_rewritten") is bool(target),
                f"Alias remapping mismatch for {alias!r}.")
        forwarded = result.get("forwarded_body")
        require(isinstance(forwarded, dict), f"Missing forwarded_body for {alias!r}.")
        expected = dict(original)
        expected.update(policy)  # policy objects, including chat_template_kwargs, REPLACE
        expected["model"] = target or alias
        require(forwarded == expected,
                f"Forwarded preview differs from the expected policy for {alias!r}.")
        injected = result.get("injected_params")
        overridden = result.get("overridden_by_client")
        require(isinstance(injected, dict) and isinstance(overridden, dict),
                f"Missing injected/overridden preview fields for {alias!r}.")
        for key, value in policy.items():
            if original.get(key) != value:
                require(key in injected and injected[key].get("from_profile") == value,
                        f"Preview does not report injection of {key!r} for {alias!r}.")
                if key in original and key != "chat_template_kwargs":
                    require(overridden.get(key) == original[key],
                            f"Preview does not report overridden {key!r} for {alias!r}.")
    return {
        "alias_count": len(ids),
        "real_aliases": len(ids) - count_proxy_only,
        "proxy_only_aliases": count_proxy_only,
        "previews_checked": len(ids),
        "server_status": config["status"],
        "server_port_observed": config["llama_port"],
    }, next((alias for alias in ids if by_alias[alias].get("target")), ids[0])


def read_db_metadata(path: Path) -> dict | None:
    """Inspect optional existing instance DB strictly read-only; never migrate it."""
    if not path.is_file():
        return None
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=3) as conn:
            conn.execute("PRAGMA query_only = ON")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    except sqlite3.Error as exc:
        raise SmokeFailure(f"Existing metrics DB cannot be read ({type(exc).__name__}).") from None
    require(version == 9 and
            {"metrics_proxy_requests", "v_proxy_request_summary",
             "execution_runs", "serve_model_instances"}.issubset(names),
            "Existing metrics DB does not have the expected v9 schema/views.")
    return {"schema_version": version, "proxy_table": True, "summary_view": True}


def infer(base_url: str, model: str, timeout: float) -> dict:
    """Explicit opt-in; verifies real non-stream and stream paths, no response content saved."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROBE_PROMPT}],
        "max_tokens": 3,
        "stream": False,
    }
    nonstream = http_json(base_url, "POST", "/v1/chat/completions", body, timeout)
    require(isinstance(nonstream.get("choices"), list) and nonstream["choices"],
            "Non-streamed inference returned no choices.")
    stream_body = {**body, "stream": True}
    req = request.Request(
        base_url + "/v1/chat/completions",
        method="POST",
        data=json.dumps(stream_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    events = 0
    done = False
    try:
        with request.urlopen(req, timeout=timeout) as response:
            require(response.status == 200, "Streamed inference returned non-200 HTTP.")
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    done = True
                    break
                try:
                    event = json.loads(payload)
                except ValueError:
                    raise SmokeFailure("Live SSE event was invalid JSON.") from None
                require(isinstance(event, dict), "Live SSE event was not a JSON object.")
                events += 1
    except error.HTTPError as exc:
        raise SmokeFailure(f"Inference returned HTTP {exc.code}.") from None
    except (error.URLError, TimeoutError, OSError) as exc:
        raise SmokeFailure(f"Inference failed ({type(exc).__name__}). "
                           "Check model availability and --inference-timeout.") from None
    require(events > 0, "No SSE JSON events were received from live inference.")
    return {"model_alias": model, "non_stream": "pass", "sse_events": events,
            "sse_done_observed": done}


def run_unit_tests() -> tuple[bool, str]:
    # Child stdout is piped, not a terminal. On Windows it otherwise defaults
    # to cp1252, which cannot print existing migration diagnostics (e.g. →).
    # Decode with the matching encoding regardless of the parent console.
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=child_env, check=False,
    )
    output = proc.stdout + "\n" + proc.stderr
    match = re.search(r"Ran (\d+) tests?", output)
    if proc.returncode:
        print(output, file=sys.stderr)
    return proc.returncode == 0, (match.group(1) if match else "unknown")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S00: unit tests + live local Dispatcher smoke")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001",
                        help="Already running local Dispatcher proxy (not direct llama.cpp/Strata)")
    parser.add_argument("--instance", help="Required for live run: instance name; also checks local DB read-only")
    parser.add_argument("--launch-command", help="Only if OS process inspection fails: record an operator-declared exact serve command (not OS-verified)")
    parser.add_argument("--rebaseline", action="store_true", help="Explicitly archive previous start/config baseline and accept the current observed one")
    parser.add_argument("--label", default=None, help="Label in result (e.g. Speedy_Win)")
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    parser.add_argument("--unit-only", action="store_true", help="Skip live probes if server retired")
    parser.add_argument("--inference", action="store_true",
                        help="Opt in to two real three-token requests, one streaming")
    parser.add_argument("--inference-timeout", type=float, default=300)
    parser.add_argument("--http-timeout", type=float, default=8)
    args = parser.parse_args(argv)
    safe_label = re.sub(r"[^A-Za-z0-9_-]", "_",
                        args.label or args.instance or ("Windows" if sys.platform == "win32" else "WSL_or_Linux"))
    report_path = args.report or ROOT / "reports" / f"s00-{safe_label}.json"
    result = {
        "schema": "s00-smoke-v1",
        "at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": safe_label,
        "platform": platform.system(),
        "checks": {},
        "overall": "FAIL",
    }
    try:
        if args.unit_only and (args.inference or args.rebaseline or args.launch_command):
            raise SmokeFailure("--unit-only cannot combine with --inference, --rebaseline or --launch-command.")
        if not args.unit_only:
            require(bool(args.instance), "Live S00 requires --instance NAME to capture and verify startup provenance.")
        if args.http_timeout <= 0 or args.inference_timeout <= 0:
            raise SmokeFailure("Timeouts must be positive.")
        base_url = validate_base_url(args.base_url) if not args.unit_only else None
        print("[S00] Running repository unit tests...")
        passed, count = run_unit_tests()
        result["checks"]["unit_tests"] = {"status": "PASS" if passed else "FAIL", "count": count}
        require(passed, "Unit tests failed; see test output above.")
        if not args.unit_only:
            print(f"[S00] Checking existing local Dispatcher at {base_url}...")
            def send(method: str, route: str, payload: dict | None) -> dict:
                print(f"[S00] HTTP {method} {route} (Dispatcher proxy)")
                return http_json(base_url, method, route, payload, args.http_timeout)
            inspection, selected_model = inspect_live(send)
            result["checks"]["live_preview"] = {"status": "PASS", **inspection}
            print(f"[S00] Verified {inspection['previews_checked']} live alias previews; "
                  "no model inference in this stage.")
            print("[S00] Capturing running process command and checking pinned launch baseline...")
            try:
                provenance = (rebaseline_startup if args.rebaseline else pin_startup)(
                    args.instance, report_path.parent, args.launch_command,
                    proxy_port=urlsplit(base_url).port)
            except ProvenanceError as exc:
                raise SmokeFailure(str(exc)) from None
            result["checks"]["startup_provenance"] = provenance
            if args.instance:
                db = ROOT / "instances" / args.instance / "data" / "metrics.db"
                metadata = read_db_metadata(db)
                if metadata is None:
                    result["checks"]["sqlite"] = {
                        "status": "SKIP", "reason": "No local instance metrics.db at expected path"
                    }
                else:
                    result["checks"]["sqlite"] = {"status": "PASS", **metadata}
            if args.inference:
                print("[S00] Opt-in inference: two tiny requests (may trigger model load)...")
                result["checks"]["inference"] = {
                    "status": "PASS", **infer(base_url, selected_model, args.inference_timeout)
                }
            else:
                result["checks"]["inference"] = {
                    "status": "SKIP", "reason": "requires explicit --inference"
                }
        else:
            result["checks"]["live_preview"] = {"status": "SKIP", "reason": "--unit-only"}
        result["overall"] = "PASS"
    except SmokeFailure as exc:
        result["error"] = str(exc)
    except (OSError, ValueError) as exc:
        result["error"] = f"Test runner failed ({type(exc).__name__})."
    finally:
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
            print(f"[S00] {result['overall']} — {report_path}")
        except OSError:
            print("[S00] Could not write the JSON report.", file=sys.stderr)
        for name, info in result["checks"].items():
            print(f"  {name}: {info['status']}")
        if result.get("error"):
            print(f"  Reason: {result['error']}", file=sys.stderr)
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
