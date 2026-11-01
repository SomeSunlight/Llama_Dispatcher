"""S03 live acceptance against an ALREADY RUNNING local Dispatcher and Strata.

Never starts/stops a service, changes native config, or sends native management API
requests. Only --inference sends small synthetic chat requests. Reports contain no
tokens, prompts, response content, headers or sensitive raw engine data.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class SmokeError(Exception):
    pass


def require(value: bool, reason: str) -> None:
    if not value:
        raise SmokeError(reason)


def loopback_url(url: str) -> str:
    parts = urlsplit(url)
    require(parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"},
            "Dispatcher URL must be local loopback HTTP; use a private tunnel for remote hosts.")
    require(parts.port is not None and parts.path in {"", "/"} and not (
        parts.username or parts.password or parts.query or parts.fragment),
        "Use the Dispatcher root URL with an explicit port and without URL credentials.")
    return url.rstrip("/")


def send(base: str, route: str, token: str | None, body: dict | None = None,
         timeout: float = 15.0) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"accept": "application/json"}
    if body is not None:
        headers["content-type"] = "application/json"
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    req = request.Request(base + route, data=data,
                          method="POST" if body is not None else "GET", headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            result = json.load(resp)
    except error.HTTPError as exc:
        code = exc.code
        # Discard native error text, which might contain runtime details or a prompt.
        exc.close()
        result = {}
    except (error.URLError, TimeoutError, OSError) as exc:
        raise SmokeError(f"{route}: unable to reach Dispatcher ({type(exc).__name__}).") from None
    except (ValueError, UnicodeDecodeError):
        raise SmokeError(f"{route}: response is not JSON.") from None
    require(isinstance(result, dict), f"{route}: response JSON must be an object.")
    return code, result


def last_rowid(db_file: Path) -> int:
    require(db_file.is_file(), "Specified metrics database file does not exist.")
    try:
        with closing(sqlite3.connect(db_file.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only = ON")
            require(db.execute("PRAGMA user_version").fetchone()[0] == 9,
                    "Expected Dispatcher SQLite schema v9.")
            return int(db.execute("SELECT COALESCE(MAX(rowid),0) FROM metrics_proxy_requests").fetchone()[0])
    except sqlite3.Error:
        raise SmokeError("Unable to open Dispatcher metrics database in read-only mode.") from None


def new_audit_rows(db_file: Path, after_rowid: int, client_id: str,
                   alias: str) -> list[dict]:
    try:
        with closing(sqlite3.connect(db_file.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only = ON")
            rows = db.execute(
                """SELECT client_id, client_model, target_model, stream, status_code,
                          run_id, policy_mode, alias_remapped
                   FROM metrics_proxy_requests
                   WHERE rowid > ? AND client_id = ? AND client_model = ?
                   ORDER BY rowid""", (after_rowid, client_id, alias)).fetchall()
    except sqlite3.Error:
        raise SmokeError("Unable to inspect Dispatcher audit records in read-only mode.") from None
    return [
        {"client_id": cid, "alias": ca, "target": target, "stream": bool(stream),
         "status": status, "run_id_is_null": run_id is None,
         "policy": policy, "alias_remapped": bool(remapped)}
        for cid, ca, target, stream, status, run_id, policy, remapped in rows
    ]


def stream_chat(base: str, token: str, payload: dict, timeout: float) -> dict:
    headers = {"authorization": "Bearer " + token, "content-type": "application/json",
               "accept": "text/event-stream"}
    req = request.Request(base + "/v1/chat/completions",
                          data=json.dumps(payload).encode(), method="POST", headers=headers)
    events = 0
    done = False
    started = time.monotonic()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            require(resp.status == 200, f"Streaming response returned HTTP {resp.status}.")
            require("text/event-stream" in resp.headers.get("content-type", ""),
                    "Expected text/event-stream response.")
            # Read incrementally: no response content ever saved or printed.
            for raw in resp:
                if not raw.startswith(b"data: "):
                    continue
                val = raw[6:].strip()
                if val == b"[DONE]":
                    done = True
                    break
                try:
                    obj = json.loads(val)
                except ValueError:
                    raise SmokeError("Stream contains invalid JSON data events.") from None
                require(isinstance(obj, dict), "Stream data event is not a JSON object.")
                events += 1
    except error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise SmokeError(f"Streaming inference failed with HTTP {code}.") from None
    except (error.URLError, TimeoutError, OSError) as exc:
        raise SmokeError(f"Streaming inference transport failed ({type(exc).__name__}).") from None
    require(events > 0, "No SSE JSON data events arrived.")
    require(done, "Streaming inference did not end with data: [DONE].")
    return {"http_status": 200, "data_events": events, "done": done,
            "duration_s": round(time.monotonic() - started, 3)}


def run(args: argparse.Namespace) -> dict:
    base = loopback_url(args.base_url)
    token = os.environ.get(args.client_token_env, "")
    require(bool(token) and token.strip() == token,
            f"Environment variable {args.client_token_env} must hold a valid client token.")
    db = Path(args.db).expanduser() if args.db else None
    result: dict = {
        "schema_version": 1, "utc": datetime.now(timezone.utc).isoformat(),
        "dispatcher": "loopback", "checks": {},
        "inference_requested": args.inference,
    }
    checks = result["checks"]

    code, _ = send(base, "/v1/models", None)
    require(code == 401, "Unauthenticated /v1/models must return 401.")
    checks["unauthenticated_rejected"] = True

    code, conf = send(base, "/debug/config", token)
    require(code == 200 and conf.get("backend") == "strata"
            and conf.get("status") == "attached" and conf.get("ownership") == "attached",
            "Dispatcher is not in authenticated S03 attached Strata mode.")
    aliases = conf.get("aliases")
    require(isinstance(aliases, list) and aliases, "Missing attached aliases.")
    configurations = {item.get("alias"): item for item in aliases if isinstance(item, dict)}
    require(len(configurations) == len(aliases), "Invalid or duplicate alias configuration.")

    code, models = send(base, "/v1/models", token)
    ids = {m.get("id") for m in models.get("data", []) if isinstance(m, dict)}
    require(code == 200 and ids == set(configurations), "Public /v1/models does not match aliases.")
    alias = args.alias or next(iter(configurations))
    require(alias in configurations, "Requested alias not exposed by Dispatcher.")
    target = configurations[alias].get("target")
    require(isinstance(target, str) and target, "Selected alias has no native target.")
    result["alias"] = alias
    result["native_target"] = target
    checks["public_aliases"] = sorted(ids)

    code, probe = send(base, "/debug/strata", token)
    require(code == 200 and probe.get("backend") == "strata" and
            probe.get("ownership") == "attached" and probe.get("available") is True,
            "Native Strata discovery is not available or target ID does not match.")
    checks["native_strata_available"] = True
    checks["reported_loaded"] = probe.get("loaded")

    test_payload = {
        "model": alias, "messages": [{"role": "user", "content": "S03 synthetic check; respond OK."}],
        "temperature": 0.913, "max_tokens": 32, "stream": False,
    }
    code, preview = send(base, "/debug/preview", token, test_payload)
    require(code == 200 and preview.get("original_model") == alias and
            preview.get("forwarded_model") == target,
            "Alias forwarding preview does not match the configured native target.")
    require(preview.get("forwarded_body", {}).get("messages") == "<redacted>",
            "Diagnostic preview leaked request content.")
    mode = preview.get("policy_mode")
    require(mode in {"default", "enforce", "passthrough"}, "Unknown S02 client policy.")
    expected = configurations[alias].get("injected_params", {})
    forwarded = preview["forwarded_body"]
    for key, value in expected.items():
        if mode == "enforce" or (mode == "default" and key not in test_payload):
            require(forwarded.get(key) == value or
                    (key == "chat_template_kwargs" and isinstance(forwarded.get(key), dict)),
                    f"Alias policy {key} did not reach effective preview.")
    checks["policy_mode"] = mode
    checks["alias_forwarding"] = True
    checks["preview_redacted"] = True

    # Negative native controls: must be blocked locally by Dispatcher, never forwarded.
    # /v1/load isn't a documented S03 inference endpoint.
    code, _ = send(base, "/v1/load", token,
                   {"model": "dummy-control-should-not-be-sent"})
    require(code == 404, "Native management route /v1/load must return 404.")
    checks["native_control_blocked"] = True

    if not args.inference:
        checks["inference"] = "skipped: add --inference to send two small real requests"
        return result

    before = last_rowid(db) if db else None
    code, obj = send(base, "/v1/chat/completions", token, test_payload, args.timeout)
    require(code == 200 and isinstance(obj.get("choices"), list),
            f"Nonstream native inference failed or returned a non-chat payload (HTTP {code}).")
    checks["nonstream_inference"] = {"http_status": code,
                                     "choices": len(obj["choices"])}
    streamed = {**test_payload, "stream": True}
    checks["stream_inference"] = stream_chat(base, token, streamed, args.timeout)

    if db and before is not None:
        rows = []
        for _ in range(15):
            rows = new_audit_rows(db, before, args.client_id, alias)
            if len(rows) >= 2:
                break
            time.sleep(0.2)
        require(len(rows) == 2, "Expected two new real audit records for this client and alias.")
        require({row["stream"] for row in rows} == {False, True},
                "Expected one streaming and one non-streaming SQLite record.")
        require(all(row["status"] == 200 and row["target"] == target and
                    row["run_id_is_null"] and row["policy"] == mode for row in rows),
                "SQLite audit records do not match HTTP/alias/ownership/policy.")
        checks["sqlite_audit"] = {"verified": True, "rows": rows}
    else:
        checks["sqlite_audit"] = "unverified: provide --db and --client-id"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18001")
    parser.add_argument("--client-token-env", default="S03_SMOKE_CLIENT_TOKEN",
                        help="Name of env variable holding the S02 client bearer (not its value)")
    parser.add_argument("--client-id", default="s03-smoke",
                        help="Expected S02 client id for optional SQLite audit verification")
    parser.add_argument("--alias", default=None, help="Public alias to test, default first advertised")
    parser.add_argument("--inference", action="store_true",
                        help="Opt in to two small real Strata inference requests")
    parser.add_argument("--db", default=None, help="Explicit path to local Dispatcher metrics.db")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--report", default=None, help="Optional JSON output file (no sensitive content)")
    args = parser.parse_args()
    try:
        require(args.timeout > 0, "Timeout must be positive.")
        data = run(args)
    except SmokeError as exc:
        print(f"[S03] FAIL — {exc}", file=sys.stderr)
        return 1
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    print(text)
    if args.report:
        out = Path(args.report).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"[S03] Sanitized report: {out}")
    print("[S03] PASS — real Strata inference verified." if args.inference else
          "[S03] PASS — attach discovery and policy only; inference not sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
