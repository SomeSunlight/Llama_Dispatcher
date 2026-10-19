"""S01 backend-contract tests (no model files, network, process or database)."""
from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inference_backend import (  # noqa: E402
    BackendCapabilities, BackendEndpoint, LlamaCppBackend,
    UnsupportedBackendCapability,
)


class BackendContractTests(unittest.TestCase):
    def setUp(self):
        self.backend = LlamaCppBackend()

    def test_llama_capabilities_do_not_claim_attach_or_unverified_vision(self):
        caps = self.backend.capabilities
        self.assertTrue(caps.native_compile)
        self.assertTrue(caps.http_proxy)
        self.assertTrue(caps.legacy_managed_start)
        self.assertTrue(caps.streaming)
        self.assertFalse(caps.http_attach)
        self.assertIsNone(caps.tools)
        self.assertIsNone(caps.vision)
        caps.require("native_compile")
        for feature in ("http_attach", "tools", "vision", "not_a_capability"):
            with self.subTest(feature=feature):
                with self.assertRaises(UnsupportedBackendCapability):
                    caps.require(feature)

    def test_compiler_calls_are_dynamic_and_keep_legacy_result_signatures(self):
        compiler = Mock()
        expected = ("llama-server", {"models": {"agent": {}}}, ["--models-preset", "out.ini"])
        compiler.compile_serve_ensemble.return_value = expected
        compiler.compile_serve_profile.return_value = expected
        compiler.compile_task_profile.return_value = expected
        overrides = {"ctx-size": 4096}
        self.assertIs(self.backend.compile_ensemble(compiler, "test", overrides), expected)
        compiler.compile_serve_ensemble.assert_called_once_with("test", overrides)
        self.assertIs(self.backend.compile_profile(compiler, "work", overrides), expected)
        compiler.compile_serve_profile.assert_called_once_with("work", overrides)
        self.assertIs(self.backend.compile_task(compiler, "work", "bench", overrides), expected)
        compiler.compile_task_profile.assert_called_once_with("work", "bench", overrides)

    def test_managed_llama_endpoint_preserves_the_current_proxy_target(self):
        endpoint = self.backend.legacy_endpoint(8181)
        self.assertEqual(endpoint.base_url, "http://127.0.0.1:8181")
        self.assertEqual(endpoint.v1_url("chat/completions"),
                         "http://127.0.0.1:8181/v1/chat/completions")
        self.assertTrue(endpoint.may_control_process)
        for port in (0, -1, 65536, True, "8081"):
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    self.backend.legacy_endpoint(port)

    def test_generic_attachment_is_immutable_and_never_process_owned(self):
        endpoint = BackendEndpoint.attach("https://engine.example:8443/")
        self.assertEqual(endpoint.v1_url("responses"),
                         "https://engine.example:8443/v1/responses")
        self.assertEqual(endpoint.ownership, "attached")
        self.assertFalse(endpoint.may_control_process)
        with self.assertRaises(FrozenInstanceError):
            endpoint.ownership = "legacy_managed"
        # Defining a non-owning descriptor is NOT yet implementing attach.
        with self.assertRaises(UnsupportedBackendCapability):
            self.backend.attach("http://127.0.0.1:8080")

    def test_endpoints_must_not_embed_authentication_or_non_http_scheme(self):
        for url in (
            "file:///tmp/model", "http://", "http://user:pw@localhost:8080",
            "https://example.test/?token=secret", "http://127.0.0.1:8000/#secret",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    BackendEndpoint.attach(url)

    def test_capabilities_are_immutable(self):
        caps = BackendCapabilities(True, True, True, False)
        with self.assertRaises(FrozenInstanceError):
            caps.http_attach = True


if __name__ == "__main__":
    unittest.main()
