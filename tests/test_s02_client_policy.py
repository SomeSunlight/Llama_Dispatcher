"""S02: opt-in authentication, per-client policy and private audit boundaries."""
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import dispatcher_core as core  # noqa: E402
from client_policy import (  # noqa: E402
    ClientIdentity, ClientSecurity, ClientConfigurationError,
    apply_request_policy, load_client_security,
)
from database_manager import MetricsDatabase  # noqa: E402


def digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def security():
    return ClientSecurity((
        ClientIdentity("goose", digest("goose-test-token"), "enforce"),
        ClientIdentity("webui", digest("webui-test-token"), "default"),
    ))


def make_request(body, identity):
    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}
    req = Request({
        "type": "http", "method": "POST", "path": "/v1/chat/completions",
        "headers": [
            (b"content-type", b"application/json"),
            (b"authorization", b"Bearer goose-test-token"),
            (b"x-client-id", b"spoofed"),
            (b"x-forwarded-user", b"spoofed"),
        ],
    }, receive)
    req.state.client_id = identity.client_id
    req.state.policy_mode = identity.policy
    return req


class FakeUpstream:
    status_code = 200

    def __init__(self, data):
        self.data = data
        self.kwargs = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *unused):
        return False

    def stream(self, method, url, **kwargs):
        self.kwargs = kwargs
        return self

    async def aiter_bytes(self):
        yield self.data


class ConfigAndPolicyTests(unittest.TestCase):
    def test_legacy_mode_is_not_silently_authenticated(self):
        with patch.dict("os.environ", {}, clear=True):
            old = load_client_security()
        self.assertFalse(old.enabled)
        self.assertIsNone(old.authenticate("Bearer arbitrary"))

    def test_independent_revocable_tokens_and_rotation(self):
        current = security()
        self.assertEqual(current.authenticate("Bearer goose-test-token").client_id, "goose")
        self.assertEqual(current.authenticate("bEaReR webui-test-token").client_id, "webui")
        for value in ("", "Bearer revoked", "Basic goose-test-token",
                      "Bearer goose-test-token ", "goose-test-token"):
            self.assertIsNone(current.authenticate(value))
        rotated = ClientSecurity((ClientIdentity("goose", digest("new-token"), "enforce"),))
        self.assertIsNone(rotated.authenticate("Bearer goose-test-token"))
        self.assertIsNone(rotated.authenticate("Bearer webui-test-token"))
        self.assertEqual(rotated.authenticate("Bearer new-token").client_id, "goose")

    def test_private_config_validated_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "clients.json"
            path.write_text(json.dumps({"schema_version": 1, "clients": [
                {"id": "goose", "token_sha256": digest("one"), "policy": "enforce"},
                {"id": "webui", "token_sha256": digest("two"), "policy": "passthrough"},
            ]}), encoding="utf-8")
            loaded = load_client_security(str(path))
            self.assertEqual([c.client_id for c in loaded.clients], ["goose", "webui"])
            for value in (
                {"schema_version": 1, "clients": []},
                {"schema_version": 1, "clients": [{"id": "goose", "token_sha256": "raw-token"}]},
                {"schema_version": 1, "clients": [
                    {"id": "x", "token_sha256": digest("one")},
                    {"id": "y", "token_sha256": digest("one")},
                ]},
            ):
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ClientConfigurationError):
                    load_client_security(str(path))
            with self.assertRaises(ClientConfigurationError):
                load_client_security(str(Path(folder) / "nonexistent.json"))

    def test_default_enforce_passthrough_are_unambiguous(self):
        client = {"temperature": 0.9, "model": "agent"}
        profile = {"temperature": 0.2, "top_p": 0.8}
        enforce, en = apply_request_policy(client, profile, "enforce")
        default, de = apply_request_policy(client, profile, "default")
        passthrough, pa = apply_request_policy(client, profile, "passthrough")
        self.assertEqual((enforce["temperature"], default["temperature"],
                          passthrough["temperature"]), (0.2, 0.9, 0.9))
        self.assertEqual(en, profile)
        self.assertEqual(de, {"top_p": 0.8})
        self.assertEqual(pa, {})
        self.assertNotIn("top_p", passthrough)
        self.assertEqual(client, {"temperature": 0.9, "model": "agent"})

    def test_private_fields_do_not_enter_audit_snapshots(self):
        payload = {
            "model": "agent", "temperature": 0.9,
            "messages": [{"content": "private prompt"}],
            "tools": [{"description": "private function definition"}],
            "extra_body": {"hidden": "private custom extension"},
            "api_key": "private credential",
            "chat_template_kwargs": {
                "enable_thinking": False, "private_custom": "private nested"
            },
        }
        observed = json.dumps(core._request_params_snapshot(payload))
        self.assertIn("temperature", observed)
        self.assertIn("enable_thinking", observed)
        self.assertNotIn("private", observed)


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_credential_required_for_all_control_and_inference_routes(self):
        with patch.object(core, "CLIENT_SECURITY", security()):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=core.app),
                base_url="http://localhost",
            ) as client:
                for url in ("/v1/models", "/v1/chat/completions", "/debug/config",
                            "/debug/preview", "/switch", "/stop"):
                    response = await client.get(url)
                    self.assertEqual(response.status_code, 401, url)
                    self.assertEqual(response.headers["www-authenticate"], "Bearer")
                response = await client.get("/v1/models", headers={
                    "X-Client-Id": "goose", "X-Forwarded-User": "goose",
                })
                self.assertEqual(response.status_code, 401)
                response = await client.get("/v1/models", headers={
                    "Authorization": "Bearer revoked",
                })
                self.assertEqual(response.status_code, 401)

    async def test_authenticated_models_and_preview_do_not_echo_private_payload(self):
        orc = SimpleNamespace(
            _active_model_aliases=["agent"], _proxy_sampling_params={
                "agent": {"temperature": 0.2}
            }, _proxy_alias_targets={"agent": "base"},
            _proxy_target_port=8181, is_running=True,
        )
        with patch.object(core, "CLIENT_SECURITY", security()), \
             patch.object(core, "orchestrator", orc):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=core.app),
                base_url="http://localhost",
            ) as client:
                headers = {"Authorization": "Bearer webui-test-token"}
                response = await client.get("/v1/models", headers=headers)
                self.assertEqual(response.status_code, 200)
                response = await client.post("/debug/preview", headers=headers, json={
                    "model": "agent", "temperature": 0.9,
                    "messages": [{"content": "secret prompt"}],
                })
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["policy_mode"], "default")
                self.assertEqual(data["forwarded_body"]["model"], "base")
                self.assertEqual(data["forwarded_body"]["temperature"], 0.9)
                self.assertEqual(data["forwarded_body"]["messages"], "<redacted>")
                self.assertNotIn("secret prompt", response.text)


class ProxyAndSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_identity_policy_headers_and_sqlite_fields_through_proxy(self):
        orc = SimpleNamespace(
            is_running=True, _proxy_target_port=8181, _active_run_id=None,
            _proxy_sampling_params={"agent": {"temperature": 0.2, "top_p": 0.8}},
            _proxy_alias_targets={"agent": "base"}, _proxy_profiles={"agent": "work"},
            db=Mock(),
        )
        fake = FakeUpstream(b'{"choices":[{"finish_reason":"stop"}]}')
        with patch.object(core, "CLIENT_SECURITY", security()), \
             patch.object(core, "orchestrator", orc), \
             patch.object(core.httpx, "AsyncClient", lambda **kwargs: fake):
            identity = security().authenticate("Bearer webui-test-token")
            req = make_request({
                "model": "agent", "temperature": 0.9,
                "messages": [{"content": "private prompt"}],
                "tools": [{"description": "private tool"}],
                "stream": False,
            }, identity)
            response = await core.proxy_to_llama("chat/completions", req)
            self.assertEqual(response.status_code, 200)
            _ = b"".join([chunk async for chunk in response.body_iterator])
        self.assertEqual(json.loads(fake.kwargs["content"])["temperature"], 0.9)
        self.assertEqual(json.loads(fake.kwargs["content"])["top_p"], 0.8)
        self.assertEqual(json.loads(fake.kwargs["content"])["model"], "base")
        self.assertNotIn("authorization", fake.kwargs["headers"])
        self.assertNotIn("x-client-id", fake.kwargs["headers"])
        self.assertNotIn("x-forwarded-user", fake.kwargs["headers"])
        logged = orc.db.insert_proxy_request.call_args.kwargs
        self.assertEqual(logged["client_id"], "webui")
        self.assertEqual(logged["policy_mode"], "default")
        self.assertEqual(logged["parameter_changes"]["model"]["source"], "alias_target")
        self.assertNotIn("private", json.dumps(logged))

    async def test_fresh_and_existing_databases_preserve_null_historical_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metrics.db"
            db = MetricsDatabase(path, ROOT / "src" / "init_db.sql")
            db.insert_proxy_request(
                run_id=None, endpoint="chat/completions", model_requested="base",
                client_model="agent", resolved_profile="work", target_model="base",
                alias_remapped=1, stream=0, req_temperature=0.2, req_top_p=None,
                req_top_k=None, req_min_p=None, req_max_tokens=3,
                req_enable_thinking=None, effective_repeat_penalty=None,
                client_params={"model": "agent"}, effective_params={"model": "base"},
                parameter_changes={}, prompt_tokens=None, completion_tokens=None,
                finish_reason=None, duration=0.3, ttft=None, status_code=200,
            )
            db.insert_proxy_request(
                run_id=None, endpoint="chat/completions", model_requested="base",
                client_model="agent", resolved_profile="work", target_model="base",
                alias_remapped=1, stream=0, req_temperature=0.2, req_top_p=None,
                req_top_k=None, req_min_p=None, req_max_tokens=3,
                req_enable_thinking=None, effective_repeat_penalty=None,
                client_params={}, effective_params={}, parameter_changes={},
                prompt_tokens=None, completion_tokens=None, finish_reason=None,
                duration=0.1, ttft=None, status_code=200,
                client_id="goose", policy_mode="enforce",
            )
            with sqlite3.connect(path) as con:
                self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 9)
                self.assertEqual(con.execute(
                    "SELECT client_id,policy_mode FROM metrics_proxy_requests ORDER BY id"
                ).fetchall(), [(None, None), ("goose", "enforce")])
                self.assertEqual(con.execute(
                    "SELECT client_id,policy_mode FROM v_proxy_request_summary "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone(), ("goose", "enforce"))
            MetricsDatabase(path, ROOT / "src" / "init_db.sql")  # idempotent
