"""No external HTTP or inference: characterize S00's one-command smoke runner."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import s00_verify as smoke  # noqa: E402


class SmokeRunnerTests(unittest.TestCase):
    def fake_api(self):
        calls = []

        def send(method, route, body):
            calls.append((method, route, body))
            if route == "/v1/models":
                return {"object": "list", "data": [
                    {"id": "base", "object": "model"},
                    {"id": "agent", "object": "model"},
                ]}
            if route == "/debug/config":
                return {"status": "running", "llama_port": 8181, "aliases": [
                    {"alias": "base", "type": "real", "target": None,
                     "injected_params": {"temperature": 0.5}},
                    {"alias": "agent", "type": "proxy-only", "target": "base",
                     "injected_params": {
                         "temperature": 0.2,
                         "chat_template_kwargs": {"enable_thinking": False},
                     }},
                ]}
            if route == "/debug/preview":
                policy = {"base": {"temperature": 0.5},
                          "agent": {"temperature": 0.2,
                                    "chat_template_kwargs": {"enable_thinking": False}}}[body["model"]]
                alias = body["model"]
                target = "base" if alias == "agent" else alias
                expected = {**body, **policy, "model": target}
                return {
                    "original_model": alias,
                    "forwarded_model": target,
                    "alias_rewritten": target != alias,
                    "forwarded_body": expected,
                    "injected_params": {
                        k: {"from_profile": v, "client_sent": body.get(k)}
                        for k, v in policy.items() if body.get(k) != v
                    },
                    "overridden_by_client": {
                        k: body[k] for k, v in policy.items()
                        if k in body and body[k] != v and k != "chat_template_kwargs"
                    },
                }
            raise AssertionError(f"Unexpected route: {route}")
        return send, calls

    def test_checks_all_aliases_and_picks_proxy_alias(self):
        send, calls = self.fake_api()
        inspection, model = smoke.inspect_live(send)
        self.assertEqual(inspection["alias_count"], 2)
        self.assertEqual(inspection["previews_checked"], 2)
        self.assertEqual(inspection["proxy_only_aliases"], 1)
        self.assertEqual(model, "agent")
        self.assertEqual(len(calls), 4)
        self.assertEqual([c[1] for c in calls], [
            "/v1/models", "/debug/config", "/debug/preview", "/debug/preview"])
        self.assertEqual(calls[-1][2]["max_tokens"], 3)

    def test_preview_mismatch_is_fail_not_a_false_success(self):
        send, _ = self.fake_api()
        def corrupt(method, route, body):
            result = send(method, route, body)
            if route == "/debug/preview":
                result["forwarded_body"]["max_tokens"] = 999
            return result
        with self.assertRaisesRegex(smoke.SmokeFailure, "Forwarded preview differs"):
            smoke.inspect_live(corrupt)

    def test_rejects_remote_servers_and_direct_strata_paths(self):
        self.assertEqual(smoke.validate_base_url("http://127.0.0.1:8001/"),
                         "http://127.0.0.1:8001")
        for address in ("https://example.com:443", "http://192.168.1.10:8001",
                        "http://localhost:8080/strata/v1",
                        "http://localhost:8001/v1",
                        "http://localhost:8001?api_key=x"):
            with self.subTest(address=address):
                with self.assertRaises(smoke.SmokeFailure):
                    smoke.validate_base_url(address)

    def test_readonly_database_probe_does_not_migrate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.db"
            with sqlite3.connect(path) as conn:
                conn.executescript("""
                    PRAGMA user_version = 8;
                    CREATE TABLE metrics_proxy_requests (id INTEGER);
                    CREATE TABLE execution_runs (id INTEGER);
                    CREATE TABLE serve_model_instances (id INTEGER);
                    CREATE VIEW v_proxy_request_summary AS
                      SELECT id FROM metrics_proxy_requests;
                """)
                conn.execute("INSERT INTO metrics_proxy_requests VALUES (11)")
            self.assertEqual(smoke.read_db_metadata(path)["schema_version"], 8)
            with sqlite3.connect(path) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM metrics_proxy_requests").fetchone()[0], 1)

    def test_one_command_unit_only_generates_safe_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            with patch.object(smoke, "run_unit_tests", return_value=(True, "31")):
                exit_code = smoke.main([
                    "--unit-only", "--label", "Laptop_Win", "--report", str(report)])
            self.assertEqual(exit_code, 0)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data["overall"], "PASS")
            self.assertEqual(data["checks"]["unit_tests"]["count"], "31")
            self.assertEqual(data["checks"]["live_preview"]["status"], "SKIP")
            self.assertNotIn("messages", data)

    def test_live_runner_report_is_automatic_and_does_not_run_inference_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            send, calls = self.fake_api()
            report = Path(tmp) / "report.json"
            with patch.object(smoke, "run_unit_tests", return_value=(True, "40")), \
                 patch.object(smoke, "http_json",
                              side_effect=lambda base, method, route, payload, timeout:
                              send(method, route, payload)), \
                 patch.object(smoke, "pin_startup", return_value={"status": "PASS", "capture": "mock_observed"}), \
                 patch.object(smoke, "infer", side_effect=AssertionError("unexpected inference")):
                exit_code = smoke.main(["--label", "Speedy_Win",
                                         "--report", str(report)])
            self.assertEqual(exit_code, 0)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data["checks"]["live_preview"]["status"], "PASS")
            self.assertEqual(data["checks"]["inference"]["status"], "SKIP")
            self.assertEqual(data["checks"]["startup_provenance"]["status"], "PASS")
            self.assertEqual(data["checks"]["live_preview"]["previews_checked"], 2)
            self.assertEqual(len(calls), 4)
            self.assertNotIn(smoke.PROBE_PROMPT, report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
