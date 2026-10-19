"""S00: proxy contract with an in-memory HTTP upstream and audit sink.

This intentionally pins *observed* limitations (fragmented SSE, upstream HTTP
status) rather than changing production code before S01.
"""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import dispatcher_core as core  # noqa: E402


def request_for(payload):
    body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": [(b"host", b"localhost"), (b"content-type", b"application/json"),
                    (b"authorization", b"Bearer synthetic-test-only")],
    }, receive)


class FakeUpstream:
    def __init__(self, chunks, status=200, failure=None):
        self.chunks = chunks
        self.status_code = status
        self.failure = failure
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self

    async def aiter_bytes(self):
        for chunk in self.chunks:
            yield chunk
        if self.failure:
            raise self.failure


class ProxyCharacterization(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Mock()
        self.orc = SimpleNamespace(
            is_running=True,
            _proxy_target_port=8181,
            _active_run_id="run-001",
            _active_model_aliases=["base", "agent"],
            _proxy_sampling_params={
                "agent": {
                    "temperature": 0.2,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            },
            _proxy_alias_targets={"agent": "base"},
            _proxy_profiles={"agent": "work", "base": "work"},
            db=self.db,
        )
        p = patch.object(core, "orchestrator", self.orc)
        p.start()
        self.addCleanup(p.stop)

    def fake_upstream(self, chunks, status=200, failure=None):
        fake = FakeUpstream(chunks, status, failure)
        p = patch.object(core.httpx, "AsyncClient", lambda **_kwargs: fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    @staticmethod
    def payload(stream=False):
        return {
            "model": "agent", "stream": stream,
            "messages": [{"role": "user", "content": "private content"}],
            "temperature": 0.9,
            "chat_template_kwargs": {"enable_thinking": True, "other": "client"},
            "max_tokens": 32,
            "tools": [{"type": "function", "function": {"name": "probe"}}],
        }

    async def test_models_exposes_public_aliases_not_paths(self):
        result = await core.api_models()
        data = json.loads(result.body)
        self.assertEqual([m["id"] for m in data["data"]], ["base", "agent"])
        self.assertEqual({m["owned_by"] for m in data["data"]}, {"llama-dispatcher"})

    async def test_preview_replaces_thinking_object_and_remaps_without_forwarding(self):
        response = await core.debug_preview(request_for(self.payload()))
        body = json.loads(response.body)
        self.assertEqual(body["original_model"], "agent")
        self.assertEqual(body["forwarded_model"], "base")
        self.assertTrue(body["alias_rewritten"])
        self.assertEqual(body["forwarded_body"]["temperature"], 0.2)
        self.assertEqual(body["forwarded_body"]["chat_template_kwargs"],
                         {"enable_thinking": False})
        self.assertEqual(body["forwarded_body"]["max_tokens"], 32)
        self.assertIn("temperature", body["overridden_by_client"])
        self.db.insert_proxy_request.assert_not_called()

    async def test_nonstream_forwarding_usage_and_prompt_free_audit(self):
        payload = {"choices": [{"finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 11, "completion_tokens": 5}}
        raw = json.dumps(payload).encode("utf-8")
        fake = self.fake_upstream([raw[:8], raw[8:]])
        response = await core.proxy_to_llama("chat/completions", request_for(self.payload()))
        received = b"".join([chunk async for chunk in response.body_iterator])
        self.assertEqual(received, raw)
        self.assertEqual(len(fake.calls), 1)
        method, url, options = fake.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "http://127.0.0.1:8181/v1/chat/completions")
        forwarded = json.loads(options["content"])
        self.assertEqual(forwarded["model"], "base")
        self.assertEqual(forwarded["temperature"], 0.2)
        self.assertEqual(forwarded["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(forwarded["max_tokens"], 32)
        self.assertEqual(forwarded["tools"], self.payload()["tools"])
        self.assertNotIn("host", options["headers"])
        self.assertNotIn("content-length", options["headers"])

        logged = self.db.insert_proxy_request.call_args.kwargs
        self.assertEqual(logged["client_model"], "agent")
        self.assertEqual(logged["target_model"], "base")
        self.assertEqual(logged["resolved_profile"], "work")
        self.assertEqual(logged["alias_remapped"], 1)
        self.assertEqual((logged["prompt_tokens"], logged["completion_tokens"]), (11, 5))
        self.assertEqual(logged["finish_reason"], "stop")
        self.assertIsNotNone(logged["ttft"])
        self.assertEqual(logged["client_params"]["temperature"], 0.9)
        self.assertEqual(logged["effective_params"]["temperature"], 0.2)
        self.assertEqual(logged["parameter_changes"]["model"]["source"], "alias_target")
        self.assertEqual(logged["parameter_changes"]["temperature"]["source"],
                         "dispatcher_policy")
        self.assertNotIn("messages", logged["client_params"])
        self.assertNotIn("messages", logged["effective_params"])
        self.assertNotIn("prompt", logged["effective_params"])
        self.assertNotIn("input", logged["effective_params"])
        self.assertNotIn("private content", json.dumps(logged["client_params"]))
        self.assertNotIn("Bearer", json.dumps(logged["effective_params"]))

    async def test_complete_sse_event_captures_usage(self):
        event = {"usage": {"prompt_tokens": 3, "completion_tokens": 7},
                 "choices": [{"finish_reason": "length"}]}
        chunk = ("data: " + json.dumps(event) + "\n\n").encode()
        self.fake_upstream([chunk, b"data: [DONE]\n\n"])
        response = await core.proxy_to_llama("chat/completions", request_for(self.payload(True)))
        self.assertEqual(b"".join([b async for b in response.body_iterator]),
                         chunk + b"data: [DONE]\n\n")
        logged = self.db.insert_proxy_request.call_args.kwargs
        self.assertEqual((logged["prompt_tokens"], logged["completion_tokens"]), (3, 7))
        self.assertEqual(logged["finish_reason"], "length")
        self.assertEqual(logged["stream"], 1)

    async def test_fragmented_sse_event_currently_loses_usage(self):
        # KNOWN S00 LIMITATION: parser calls splitlines() independently for each
        # httpx byte chunk. It does not buffer incomplete "data: {...}" lines.
        event = b'data: {"usage":{"prompt_tokens":3,"completion_tokens":7}}\n\n'
        self.fake_upstream([event[:25], event[25:]])
        response = await core.proxy_to_llama("chat/completions", request_for(self.payload(True)))
        self.assertEqual(b"".join([b async for b in response.body_iterator]), event)
        logged = self.db.insert_proxy_request.call_args.kwargs
        self.assertIsNone(logged["prompt_tokens"])
        self.assertIsNone(logged["completion_tokens"])

    async def test_early_consumer_close_still_logs_request(self):
        self.fake_upstream([b"data: {}\n\n", b"data: [DONE]\n\n"])
        response = await core.proxy_to_llama("chat/completions", request_for(self.payload(True)))
        iterator = response.body_iterator
        self.assertEqual(await anext(iterator), b"data: {}\n\n")
        await iterator.aclose()
        self.db.insert_proxy_request.assert_called_once()
        self.assertIsNone(self.db.insert_proxy_request.call_args.kwargs["completion_tokens"])

    async def test_upstream_status_and_failure_are_logged_as_currently_implemented(self):
        # KNOWN S00 LIMITATION: the outgoing StreamingResponse is created with
        # implicit 200, even when upstream reports 502. The DB records 502.
        self.fake_upstream([b'{"error":"unavailable"}'], status=502)
        response = await core.proxy_to_llama("chat/completions", request_for(self.payload()))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join([b async for b in response.body_iterator]),
                         b'{"error":"unavailable"}')
        self.assertEqual(self.db.insert_proxy_request.call_args.kwargs["status_code"], 502)

        self.db.reset_mock()
        self.fake_upstream([b"abc"], failure=RuntimeError("fake upstream disconnected"))
        response = await core.proxy_to_llama("chat/completions", request_for(self.payload(True)))
        with self.assertRaisesRegex(RuntimeError, "fake upstream disconnected"):
            _ = [b async for b in response.body_iterator]
        self.db.insert_proxy_request.assert_called_once()

    async def test_inactive_backend_returns_503_without_network_or_audit(self):
        self.orc.is_running = False
        response = await core.proxy_to_llama("chat/completions", request_for(self.payload()))
        self.assertEqual(response.status_code, 503)
        self.db.insert_proxy_request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
