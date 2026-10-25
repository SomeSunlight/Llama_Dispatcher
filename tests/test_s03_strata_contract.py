"""S03 mock-first contracts: no native engine, network, model files or processes."""
from __future__ import annotations

import json
import hashlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import dispatcher_core as core  # noqa: E402
from strata_attach import StrataBackend, StrataConfigurationError  # noqa: E402
from client_policy import ClientIdentity, ClientSecurity  # noqa: E402


def configuration():
    return {
        "schema_version": 1,
        "endpoint": "http://127.0.0.1:8080",
        "credential_env": "S03_NATIVE_KEY",
        "aliases": {
            "agent": {"model": "strata", "parameters": {
                "reasoning_effort": "low", "temperature": 0.2,
            }},
            "sparringpartner": {"model": "strata", "parameters": {
                "reasoning_effort": "high", "temperature": 0.6,
            }},
        },
    }


def incoming(body, *, client="goose", policy="enforce"):
    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}
    request = Request({
        "type": "http", "method": "POST", "path": "/v1/chat/completions",
        "headers": [
            (b"authorization", b"Bearer disposable-client-credential"),
            (b"x-client-id", b"spoofed"),
            (b"cookie", b"private=cookie"),
            (b"content-type", b"application/json"),
        ],
    }, receive)
    request.state.client_id = client
    request.state.policy_mode = policy
    return request


class ConfigurationContracts(unittest.TestCase):
    def test_explicit_attached_endpoint_and_secret_separation(self):
        backend = StrataBackend.from_mapping(
            configuration(), environ={"S03_NATIVE_KEY": "native-test-secret"}
        )
        self.assertEqual(backend.endpoint.ownership, "attached")
        self.assertFalse(backend.endpoint.may_control_process)
        self.assertEqual(set(backend.aliases), {"agent", "sparringpartner"})
        self.assertEqual(backend.headers()["authorization"], "Bearer native-test-secret")
        self.assertNotIn("native-test-secret", repr(backend))
        self.assertNotIn("native-test-secret", json.dumps(configuration()))

    def test_invalid_or_unsafe_config_fails_closed(self):
        for change in (
            {"endpoint": "http://user:password@localhost:8080"},
            {"endpoint": "http://example.com:8080"},
            {"endpoint": "http://127.0.0.1:8080/v1"},
            {"endpoint": "file:///tmp/engine"},
            {"credential_env": "INVALID-VAR"},
            {"aliases": {}},
            {"aliases": {"agent": {"model": "strata", "parameters": {"messages": "leak"}}}},
            {"aliases": {"agent": {"model": "strata", "parameters": {"reasoning_effort": "invalid"}}}},
        ):
            with self.subTest(change=change):
                data = configuration()
                data.update(change)
                with self.assertRaises(StrataConfigurationError):
                    StrataBackend.from_mapping(data, environ={"S03_NATIVE_KEY": "test"})
        with self.assertRaises(StrataConfigurationError):
            StrataBackend.from_mapping(configuration(), environ={})

    def test_reasoning_is_unambiguous_and_no_unsafe_merge(self):
        backend = StrataBackend.from_mapping(configuration(), environ={"S03_NATIVE_KEY": "key"})
        body, injected = backend.resolve({
            "model": "agent", "reasoning_effort": "high", "temperature": 0.9,
            "messages": [{"role": "user", "content": "secret"}],
        }, "default")
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(body["temperature"], 0.9)
        self.assertEqual(body["model"], "strata")
        self.assertEqual(injected, {})
        body, _ = backend.resolve({"model": "agent"}, "enforce")
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(body["temperature"], 0.2)
        self.assertNotIn("chat_template_kwargs", body)
        with self.assertRaises(ValueError):
            backend.resolve({
                "model": "agent", "reasoning_effort": "low",
                "chat_template_kwargs": {"enable_thinking": False}
            }, "passthrough")
        with self.assertRaises(ValueError):
            backend.resolve({"model": "unknown"}, "enforce")


class FragmentedSSE(httpx.AsyncByteStream):
    """Mock a real transport with deliberately split SSE event boundaries."""

    def __init__(self, data):
        self.data = data

    async def __aiter__(self):
        yield self.data[:17]
        yield self.data[17:55]
        yield self.data[55:]


class HttpContracts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.status = 200
        self.streaming = False
        self.last_body = None

        def respond(request):
            self.requests.append(request)
            path = request.url.path
            if path == "/health":
                return httpx.Response(200, json={"status": "ok", "loaded": True, "images": True})
            if path == "/v1/status":
                return httpx.Response(200, json={"loaded": True, "auto_load": False})
            if path == "/v1/models":
                return httpx.Response(200, json={"data": [{"id": "strata"}]})
            if path == "/v1/chat/completions":
                self.last_body = json.loads(request.content)
                if self.streaming:
                    return httpx.Response(
                        self.status, headers={"content-type": "text/event-stream"},
                        stream=FragmentedSSE(
                            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0}]}}]}\n\n'
                            b'data: {"usage":{"prompt_tokens":7,"completion_tokens":3}}\n\n'
                            b'data: [DONE]\n\n'
                        ),
                    )
                return httpx.Response(
                    self.status, json={"choices": [{"finish_reason": "stop"}],
                                       "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
                )
            raise AssertionError(f"Unexpected upstream request {request.method} {path}")

        self.transport = httpx.MockTransport(respond)
        self.backend = StrataBackend.from_mapping(
            configuration(), environ={"S03_NATIVE_KEY": "native-test-secret"},
            transport=self.transport,
        )
        self.db = Mock()
        self.orc = SimpleNamespace(
            strata_attach=self.backend,
            db=self.db, _active_run_id=None,
            _active_model_aliases=list(self.backend.aliases),
            _proxy_sampling_params=self.backend.sampling,
            _proxy_alias_targets=self.backend.targets,
            _proxy_profiles={},
            is_running=True, _proxy_target_port=None,
            current_process=None,
        )
        self.patch = patch.object(core, "orchestrator", self.orc)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    async def test_read_only_capability_probe(self):
        status = await self.backend.probe()
        self.assertTrue(status["available"])
        self.assertTrue(status["loaded"])
        self.assertEqual(status["native_model"], "strata")
        self.assertEqual([r.method for r in self.requests], ["GET", "GET", "GET"])
        self.assertEqual([r.url.path for r in self.requests],
                         ["/health", "/v1/status", "/v1/models"])
        self.assertTrue(all(r.headers["authorization"] == "Bearer native-test-secret"
                            for r in self.requests))

    async def test_nonstream_tools_vision_and_identity_audit(self):
        body = {
            "model": "agent", "temperature": 0.9,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "private prompt"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,private-image"}},
            ]}],
            "tools": [{"type": "function", "function": {"name": "private_tool"}}],
            "custom_native_extension": {"secret": "leave upstream only"},
        }
        reply = await core.proxy_to_llama("chat/completions", incoming(body))
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(json.loads(reply.body)["usage"]["prompt_tokens"], 7)
        self.assertEqual(self.last_body["model"], "strata")
        self.assertEqual(self.last_body["temperature"], 0.2)
        self.assertEqual(self.last_body["tools"], body["tools"])
        self.assertEqual(self.last_body["messages"], body["messages"])
        self.assertEqual(self.last_body["custom_native_extension"],
                         body["custom_native_extension"])
        sent = self.requests[-1]
        self.assertEqual(sent.headers["authorization"], "Bearer native-test-secret")
        self.assertNotIn("cookie", sent.headers)
        self.assertNotIn("x-client-id", sent.headers)
        log = self.db.insert_proxy_request.call_args.kwargs
        self.assertIsNone(log["run_id"])  # attached != Dispatcher launched
        self.assertEqual(log["client_id"], "goose")
        self.assertEqual(log["policy_mode"], "enforce")
        self.assertEqual(log["client_model"], "agent")
        self.assertEqual(log["target_model"], "strata")
        self.assertNotIn("private", json.dumps(log))
        self.assertEqual(log["prompt_tokens"], 7)

    async def test_streaming_preserves_raw_sse_and_usage(self):
        self.streaming = True
        body = {"model": "sparringpartner", "stream": True,
                "messages": [{"role": "user", "content": "secret"}]}
        reply = await core.proxy_to_llama("chat/completions", incoming(body))
        self.assertEqual(reply.status_code, 200)
        raw = b"".join([chunk async for chunk in reply.body_iterator])
        self.assertIn(b'tool_calls', raw)
        self.assertTrue(raw.endswith(b"data: [DONE]\n\n"))
        self.assertEqual(self.last_body["reasoning_effort"], "high")
        log = self.db.insert_proxy_request.call_args.kwargs
        self.assertEqual((log["prompt_tokens"], log["completion_tokens"]), (7, 3))

    async def test_http_error_status_and_offline_503(self):
        self.status = 429
        reply = await core.proxy_to_llama("chat/completions", incoming({"model": "agent"}))
        self.assertEqual(reply.status_code, 429)
        self.assertEqual(self.db.insert_proxy_request.call_args.kwargs["status_code"], 429)
        self.db.reset_mock()
        self.backend.transport = httpx.MockTransport(
            lambda req: (_ for _ in ()).throw(httpx.ConnectError("offline", request=req))
        )
        reply = await core.proxy_to_llama("chat/completions", incoming({"model": "agent"}))
        self.assertEqual(reply.status_code, 503)
        self.assertNotIn("offline", reply.body.decode())
        self.assertNotIn("native-test-secret", reply.body.decode())

    async def test_early_stream_close_records_unknown_usage_not_fake_zero(self):
        self.streaming = True
        response = await core.proxy_to_llama(
            "chat/completions", incoming({"model": "agent", "stream": True})
        )
        it = response.body_iterator
        self.assertTrue((await anext(it)).startswith(b"data: "))
        await it.aclose()
        saved = self.db.insert_proxy_request.call_args.kwargs
        self.assertIsNone(saved["prompt_tokens"])
        self.assertIsNone(saved["completion_tokens"])
        self.assertIsNone(saved["run_id"])

    async def test_native_control_routes_are_never_forwarded(self):
        response = await core.proxy_to_llama("unload", incoming({"model": "agent"}))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.requests, [])
        self.db.insert_proxy_request.assert_not_called()

    async def test_asgi_auth_and_redacted_preview_for_attached_backend(self):
        digest = lambda token: hashlib.sha256(token.encode()).hexdigest()
        auth = ClientSecurity((
            ClientIdentity("goose", digest("client-test-goose"), "enforce"),
            ClientIdentity("webui", digest("client-test-webui"), "default"),
        ))
        with patch.object(core, "CLIENT_SECURITY", auth):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=core.app),
                base_url="http://dispatcher.test",
            ) as client:
                self.assertEqual((await client.get("/debug/strata")).status_code, 401)
                h = {"authorization": "Bearer client-test-goose"}
                probe = await client.get("/debug/strata", headers=h)
                self.assertEqual(probe.status_code, 200)
                self.assertEqual(probe.json()["ownership"], "attached")
                self.assertNotIn("native-test-secret", probe.text)
                preview = await client.post("/debug/preview", headers=h, json={
                    "model": "agent", "messages": [{"content": "secret image or prompt"}],
                    "temperature": {"private": "nested client field"},
                    "custom_native_extension": {"private": "unknown extension"},
                })
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(preview.json()["forwarded_body"]["model"], "strata")
                self.assertEqual(preview.json()["forwarded_body"]["messages"], "<redacted>")
                self.assertEqual(preview.json()["forwarded_body"]["custom_native_extension"],
                                 "<redacted>")
                self.assertEqual(preview.json()["overridden_by_client"]["temperature"],
                                 "<redacted>")
                self.assertNotIn("secret image or prompt", preview.text)
                self.assertNotIn("unknown extension", preview.text)
                self.assertNotIn("nested client field", preview.text)
                self.assertEqual(
                    (await client.post("/stop", headers=h)).status_code, 409
                )

    async def test_attach_never_exposes_native_process_controls(self):
        stop = await core.api_stop()
        self.assertEqual(stop.status_code, 409)
        from dispatcher_core import ServeRequest
        switch = await core.api_switch_ensemble(ServeRequest(ensemble="other"))
        self.assertEqual(switch.status_code, 409)
        self.assertFalse(any(r.method in ("POST", "DELETE") and
                             any(x in r.url.path for x in ("stop", "load", "unload"))
                             for r in self.requests))


if __name__ == "__main__":
    unittest.main()
