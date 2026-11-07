"""S03 quiet readiness: healthy probe silent; real requests and failures visible."""
import logging
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import dispatcher_core as core  # noqa: E402
from client_policy import ClientIdentity  # noqa: E402


class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_healthy_and_unhealthy_without_client_key(self):
        with patch.object(core, "CLIENT_SECURITY", core.ClientSecurity()):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=core.app),
                base_url="http://127.0.0.1",
            ) as cli:
                with patch.object(core, "orchestrator", None):
                    self.assertEqual((await cli.get("/health")).status_code, 503)
                with patch.object(core, "orchestrator", SimpleNamespace(
                    is_running=False, _active_model_aliases=["agent"],
                )):
                    self.assertEqual((await cli.get("/health")).status_code, 503)
                with patch.object(core, "orchestrator", SimpleNamespace(
                    is_running=True, _active_model_aliases=[],
                )):
                    self.assertEqual((await cli.get("/health")).status_code, 503)
                with patch.object(core, "orchestrator", SimpleNamespace(
                    is_running=True, _active_model_aliases=["agent"],
                )):
                    r = await cli.get("/health")
                    self.assertEqual(r.status_code, 200)
                    self.assertEqual(r.text, "")
                    self.assertNotIn("agent", r.text)

    async def test_s02_protected_request_remains_enforced(self):
        import hashlib
        token = "test-private"
        identity = ClientIdentity("test-app", hashlib.sha256(
            token.encode()).hexdigest(), "passthrough")
        with patch.object(core, "CLIENT_SECURITY", core.ClientSecurity((identity,))):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=core.app),
                base_url="http://127.0.0.1",
            ) as cli:
                self.assertEqual((await cli.get("/v1/models")).status_code, 401)
                self.assertEqual((await cli.get("/v1/models", headers={
                    "X-AIW-Probe": "yes",
                })).status_code, 401)
                with patch.object(core, "orchestrator", SimpleNamespace(
                    is_running=True, _active_model_aliases=["agent"],
                )):
                    self.assertEqual((await cli.get("/health")).status_code, 200)


class HealthLoggingTests(unittest.TestCase):
    def record(self, method, path, status):
        return logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 1,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:9000", method, path, "1.1", status), None)

    def test_only_successful_exact_readiness_hidden(self):
        flt = core._HealthyReadinessAccessFilter()
        self.assertFalse(flt.filter(self.record("GET", "/health", 200)))
        for method, path, code in (
            ("GET", "/v1/models", 200),
            ("GET", "/v1/models", 401),
            ("POST", "/health", 200),
            ("GET", "/health", 503),
            ("GET", "/health?debug=1", 200),
            ("GET", "/health", 401),
            ("GET", "/strata/v1/models", 401),
        ):
            self.assertTrue(flt.filter(self.record(method, path, code)),
                            f"{method} {path} {code} must stay visible")

    def test_filter_installed_once(self):
        log = logging.getLogger("uvicorn.access")
        before = list(log.filters)
        try:
            core.install_quiet_health_logging()
            core.install_quiet_health_logging()
            self.assertEqual(log.filters.count(core._HEALTH_ACCESS_FILTER), 1)
        finally:
            log.filters[:] = before


if __name__ == "__main__":
    unittest.main()
