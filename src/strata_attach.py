"""S03 Strata attach contract: read-only discovery, explicit aliases, no process ownership.

Strata is started, stopped, loaded and calibrated by its independent owner.
This module has no subprocess, OS process discovery or lifecycle control.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

from client_policy import apply_request_policy
from inference_backend import BackendCapabilities, BackendEndpoint


class StrataConfigurationError(ValueError):
    """Invalid private attach configuration; never include a credential value."""


_ALIAS = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:/-]{0,127}$")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_POLICY_KEYS = frozenset({
    "temperature", "top_p", "top_k", "min_p", "max_tokens", "max_completion_tokens",
    "presence_penalty", "frequency_penalty", "repeat_penalty", "seed",
    "reasoning_effort", "chat_template_kwargs", "reasoning_budget_tokens",
})
_REASONING = frozenset({"none", "low", "medium", "high", "xhigh"})


class StrataBackend:
    """One pre-existing Strata HTTP endpoint, possibly with several logical aliases."""

    name = "strata"
    capabilities = BackendCapabilities(
        native_compile=False, http_proxy=True, legacy_managed_start=False,
        http_attach=True, streaming=True, tools=None, vision=None,
    )

    def __init__(
        self,
        endpoint: BackendEndpoint,
        aliases: Mapping[str, Mapping[str, Any]],
        credential: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if endpoint.ownership != "attached":
            raise StrataConfigurationError("Strata endpoint must be externally owned.")
        self.endpoint = endpoint
        self.aliases = {k: dict(v) for k, v in aliases.items()}
        self.sampling = {k: dict(v["parameters"]) for k, v in self.aliases.items()}
        self.targets = {k: v["model"] for k, v in self.aliases.items()}
        self._credential = credential
        self.transport = transport

    def __repr__(self) -> str:
        return f"StrataBackend(endpoint={self.endpoint!r}, aliases={list(self.aliases)!r}, credential=<redacted>)"

    @classmethod
    def from_file(
        cls, filename: str | Path, *,
        environ: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "StrataBackend":
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise StrataConfigurationError("Unable to read valid private Strata attach JSON.") from None
        return cls.from_mapping(data, environ=environ, transport=transport)

    @classmethod
    def from_mapping(
        cls, config: Any, *,
        environ: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "StrataBackend":
        if not isinstance(config, dict) or config.get("schema_version") != 1:
            raise StrataConfigurationError("Strata attach requires schema_version=1.")
        if set(config) != {"schema_version", "endpoint", "credential_env", "aliases"}:
            raise StrataConfigurationError("Unexpected or missing Strata attach configuration keys.")
        url = config["endpoint"]
        if not isinstance(url, str):
            raise StrataConfigurationError("Strata endpoint must be an HTTP(S) URL.")
        try:
            endpoint = BackendEndpoint.attach(url)
            parsed = urlsplit(endpoint.base_url)
            if parsed.path not in ("", "/") or parsed.port is None:
                raise ValueError()
            if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
                raise ValueError()
        except ValueError:
            raise StrataConfigurationError(
                "Strata endpoint requires a root HTTP(S) URL; cleartext is loopback-only."
            ) from None

        env = config["credential_env"]
        if not isinstance(env, str) or not _ENV.fullmatch(env):
            raise StrataConfigurationError("Invalid Strata credential environment variable name.")
        key = (os.environ if environ is None else environ).get(env)
        if not isinstance(key, str) or not key or key.strip() != key or "\n" in key or "\r" in key:
            raise StrataConfigurationError("Strata credential environment variable is unset or invalid.")

        aliases = config["aliases"]
        if not isinstance(aliases, dict) or not aliases:
            raise StrataConfigurationError("At least one explicit Strata alias is required.")
        validated = {}
        for alias, definition in aliases.items():
            if not isinstance(alias, str) or not _ALIAS.fullmatch(alias):
                raise StrataConfigurationError("Invalid Strata alias name.")
            if not isinstance(definition, dict) or set(definition) != {"model", "parameters"}:
                raise StrataConfigurationError("Each alias needs model and parameters.")
            model, params = definition["model"], definition["parameters"]
            if not isinstance(model, str) or not _ALIAS.fullmatch(model):
                raise StrataConfigurationError("Invalid native Strata model identifier.")
            if not isinstance(params, dict) or not set(params) <= _POLICY_KEYS:
                raise StrataConfigurationError("Unsupported per-alias policy parameter.")
            if "reasoning_effort" in params and params["reasoning_effort"] not in _REASONING:
                raise StrataConfigurationError("Unsupported reasoning_effort in Strata alias.")
            ctk = params.get("chat_template_kwargs")
            if ctk is not None and not isinstance(ctk, dict):
                raise StrataConfigurationError("chat_template_kwargs must be an object.")
            if ctk is not None and (not set(ctk) <= {"enable_thinking", "preserve_thinking", "reasoning_effort", "thinking_budget"} or
                                    any(not isinstance(v, (str, bool, int, float, type(None)))
                                        for v in ctk.values())):
                raise StrataConfigurationError("Invalid chat_template_kwargs values.")
            if "reasoning_effort" in params and isinstance(ctk, dict) and "enable_thinking" in ctk:
                raise StrataConfigurationError("Do not combine reasoning_effort and enable_thinking.")
            validated[alias] = {"model": model, "parameters": dict(params)}
        return cls(endpoint, validated, key, transport=transport)

    def headers(self) -> dict[str, str]:
        """Native credential only. Never relay a client token, cookie or trust header."""
        return {"authorization": f"Bearer {self._credential}", "content-type": "application/json"}

    def new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self.transport,
            timeout=httpx.Timeout(connect=5.0, read=None, write=30.0, pool=5.0),
            trust_env=False, follow_redirects=False,
        )

    def resolve(self, body: dict[str, Any], mode: str) -> tuple[dict[str, Any], dict[str, Any]]:
        alias = body.get("model")
        if not isinstance(alias, str) or alias not in self.aliases:
            raise ValueError("Unknown Strata model alias.")
        forwarded, injected = apply_request_policy(body, self.sampling[alias], mode)
        ctk = forwarded.get("chat_template_kwargs")
        if "reasoning_effort" in forwarded and isinstance(ctk, dict) and "enable_thinking" in ctk:
            raise ValueError("Conflicting Strata reasoning controls.")
        forwarded["model"] = self.targets[alias]
        return forwarded, injected

    async def probe(self) -> dict[str, Any]:
        """Read-only, conservative discovery. No autoload, restart or calibration."""
        result: dict[str, Any] = {
            "available": False, "loaded": None,
            "native_model": None, "images": None, "auto_load": None,
        }
        try:
            async with self.new_client() as client:
                health = await client.get(self.endpoint.base_url + "/health", headers=self.headers(),
                                          timeout=5.0)
                status = await client.get(self.endpoint.base_url + "/v1/status", headers=self.headers(),
                                          timeout=5.0)
                models = await client.get(self.endpoint.base_url + "/v1/models", headers=self.headers(),
                                          timeout=5.0)
                if any(x.status_code != 200 for x in (health, status, models)):
                    return result
                h, s, m = health.json(), status.json(), models.json()
                if not all(isinstance(x, dict) for x in (h, s, m)):
                    return result
                native_ids = {i.get("id") for i in m.get("data", [])
                              if isinstance(i, dict) and isinstance(i.get("id"), str)}
                expected_ids = set(self.targets.values())
                result["available"] = bool(native_ids & expected_ids)
                result["native_model"] = next(iter(sorted(native_ids & expected_ids)), None)
                result["loaded"] = s.get("loaded", h.get("loaded")) if isinstance(
                    s.get("loaded", h.get("loaded")), bool) else None
                result["auto_load"] = s.get("auto_load") if isinstance(s.get("auto_load"), bool) else None
                result["images"] = h.get("images") if isinstance(h.get("images"), bool) else None
        except (httpx.RequestError, httpx.TimeoutException, ValueError, TypeError, KeyError):
            return result
        return result

    async def proxy(self, path: str, request: Any, db: Any):
        """Preflight upstream headers/status before returning streaming body."""
        import time
        from fastapi.responses import JSONResponse, Response, StreamingResponse
        from dispatcher_core import (
            _extract_response_stats, _extract_thinking, _parameter_changes,
            _request_params_snapshot,
        )

        # Inference whitelist is essential: /v1/load and /v1/unload are native controls.
        if request.method != "POST" or path not in (
            "chat/completions", "completions", "responses"
        ):
            return JSONResponse(
                {"error": {"message": "Unsupported Strata inference endpoint.",
                           "type": "invalid_request_error"}}, status_code=404,
            )
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError()
            mode = getattr(request.state, "policy_mode", "enforce")
            forwarded, injected = self.resolve(body, mode)
        except (ValueError, TypeError):
            return JSONResponse(
                {"error": {"message": "Invalid model alias, JSON or reasoning controls.",
                           "type": "invalid_request_error"}}, status_code=400,
            )

        outgoing_body = json.dumps(forwarded, ensure_ascii=False).encode("utf-8")
        is_stream = forwarded.get("stream") is True
        client_model = body.get("model")
        client_id = getattr(request.state, "client_id", None)
        start = time.monotonic()
        stats: dict[str, Any] = {
            "prompt_tokens": None, "completion_tokens": None, "finish_reason": None,
            "ttft": None, "status_code": 503,
        }

        def audit() -> None:
            # Attached does not claim a Dispatcher-launched execution_run.
            # S04 owns subsequent additive engine-neutral schema changes.
            try:
                original = _request_params_snapshot(body)
                effective = _request_params_snapshot(forwarded)
                injected_safe = _request_params_snapshot(injected)
                db.insert_proxy_request(
                    run_id=None, endpoint=path, model_requested=forwarded["model"],
                    client_model=client_model, resolved_profile=None,
                    target_model=forwarded["model"],
                    alias_remapped=int(client_model != forwarded["model"]),
                    stream=int(is_stream), req_temperature=forwarded.get("temperature"),
                    req_top_p=forwarded.get("top_p"), req_top_k=forwarded.get("top_k"),
                    req_min_p=forwarded.get("min_p"),
                    req_max_tokens=forwarded.get("max_tokens"),
                    req_enable_thinking=_extract_thinking(forwarded),
                    effective_repeat_penalty=forwarded.get("repeat_penalty"),
                    client_params=original, effective_params=effective,
                    parameter_changes=_parameter_changes(
                        original, effective, client_model, forwarded["model"], None,
                    ),
                    prompt_tokens=stats["prompt_tokens"],
                    completion_tokens=stats["completion_tokens"],
                    finish_reason=stats["finish_reason"],
                    duration=time.monotonic() - start, ttft=stats["ttft"],
                    status_code=stats["status_code"],
                    injected_params=json.dumps(injected_safe, sort_keys=True)
                    if injected_safe else None,
                    client_id=client_id, policy_mode=mode,
                )
            except Exception:
                # Do not echo exceptions potentially containing private response data.
                print("[STRATA] Unable to record a proxy request summary.")

        client = self.new_client()
        try:
            outgoing = client.build_request(
                request.method, self.endpoint.v1_url(path), content=outgoing_body,
                headers=self.headers(),
            )
            upstream = await client.send(outgoing, stream=True)
            stats["status_code"] = upstream.status_code
        except httpx.RequestError:
            await client.aclose()
            audit()
            return JSONResponse(
                {"error": {"message": "Attached Strata backend unavailable.",
                           "type": "server_error"}}, status_code=503,
            )

        response_headers = {
            "content-type": upstream.headers.get(
                "content-type", "text/event-stream" if is_stream else "application/json"
            )
        }
        if "retry-after" in upstream.headers:
            response_headers["retry-after"] = upstream.headers["retry-after"]

        if not is_stream or upstream.status_code >= 400:
            try:
                raw = await upstream.aread()
                if raw:
                    stats["ttft"] = time.monotonic() - start
                if not is_stream:
                    try:
                        _extract_response_stats(json.loads(raw), stats)
                    except (ValueError, TypeError):
                        pass
                return Response(raw, status_code=upstream.status_code,
                                headers=response_headers)
            except httpx.RequestError:
                stats["status_code"] = 503
                return JSONResponse(
                    {"error": {"message": "Attached Strata backend unavailable.",
                               "type": "server_error"}}, status_code=503,
                )
            finally:
                await upstream.aclose()
                await client.aclose()
                audit()

        async def stream_bytes():
            # SSE is passed through byte-for-byte, including tool and reasoning
            # deltas. Only bounded, reassembled lines feed summary-only metrics.
            pending = bytearray()
            try:
                async for chunk in upstream.aiter_raw():
                    if stats["ttft"] is None:
                        stats["ttft"] = time.monotonic() - start
                    pending.extend(chunk)
                    if len(pending) > 1048576:
                        pending.clear()
                    while b"\n" in pending:
                        line, _, remainder = pending.partition(b"\n")
                        pending = bytearray(remainder)
                        if line.startswith(b"data: "):
                            try:
                                _extract_response_stats(json.loads(line[6:]), stats)
                            except (ValueError, TypeError):
                                pass
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()
                audit()

        return StreamingResponse(
            stream_bytes(), status_code=upstream.status_code, headers=response_headers,
        )
