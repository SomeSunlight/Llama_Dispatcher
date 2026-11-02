"""Non-network self-tests for the OPTIONAL S03 real-run smoke harness."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.s03_live_smoke import (  # noqa: E402
    SmokeError, has_chat_answer, loopback_url, last_rowid, new_audit_rows, run, stream_chat,
)


class SmokeRunnerContracts(unittest.TestCase):
    def test_loopback_only_no_credentials_in_url(self):
        self.assertEqual(loopback_url("http://127.0.0.1:18001/"),
                         "http://127.0.0.1:18001")
        for url in ("https://example.com:18001", "http://10.0.0.2:18001",
                    "http://127.0.0.1:18001/v1", "http://user:secret@localhost:18001",
                    "http://127.0.0.1:18001?token=secret"):
            with self.subTest(url=url), self.assertRaises(SmokeError):
                loopback_url(url)

    def test_visible_chat_answer_is_required(self):
        self.assertFalse(has_chat_answer({"choices": [{"message": {"content": ""}}]}))
        self.assertFalse(has_chat_answer({"choices": [{"message": {"reasoning_content": "thinking"}}]}))
        self.assertFalse(has_chat_answer({"choices": []}))
        self.assertTrue(has_chat_answer({"choices": [{"message": {"content": "OK"}}]}))

    def test_reasoning_only_stream_fails_even_with_done(self):
        class FakeResponse:
            status = 200
            headers = {"content-type": "text/event-stream"}
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def __iter__(self):
                return iter((
                    b'data: {"choices":[{"delta":{"reasoning_content":"thinking"}}]}\n',
                    b'data: [DONE]\n',
                ))
        with patch("scripts.s03_live_smoke.request.urlopen", return_value=FakeResponse()):
            with self.assertRaisesRegex(SmokeError, "only reasoning/no visible answer"):
                stream_chat("http://127.0.0.1:18001", "example", {"stream": True}, 3)

    def test_stream_with_visible_answer_passes(self):
        class FakeResponse:
            status = 200
            headers = {"content-type": "text/event-stream"}
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def __iter__(self):
                return iter((
                    b'data: {"choices":[{"delta":{"reasoning_content":"thinking"}}]}\n',
                    b'data: {"choices":[{"delta":{"content":"OK"}}]}\n',
                    b'data: [DONE]\n',
                ))
        with patch("scripts.s03_live_smoke.request.urlopen", return_value=FakeResponse()):
            result = stream_chat("http://127.0.0.1:18001", "example", {"stream": True}, 3)
        self.assertTrue(result["answer_present"])
        self.assertEqual(result["data_events"], 2)

    def test_read_only_sqlite_audit_filter(self):
        with tempfile.TemporaryDirectory() as d:
            db_file = Path(d) / "metrics.db"
            with closing(sqlite3.connect(db_file)) as conn, conn:
                conn.execute("PRAGMA user_version = 9")
                conn.execute("""CREATE TABLE metrics_proxy_requests (
                    client_id TEXT, client_model TEXT, target_model TEXT,
                    stream INTEGER, status_code INTEGER, run_id TEXT,
                    policy_mode TEXT, alias_remapped INTEGER)""")
                conn.execute("""INSERT INTO metrics_proxy_requests VALUES
                    ('other','agent','strata',0,200,NULL,'enforce',1),
                    ('s03-smoke','agent','strata',1,200,NULL,'enforce',1)""")
            self.assertEqual(last_rowid(db_file), 2)
            with closing(sqlite3.connect(db_file)) as conn, conn:
                conn.execute("""INSERT INTO metrics_proxy_requests VALUES
                    ('s03-smoke','agent','strata',0,200,NULL,'enforce',1),
                    ('other','agent','strata',1,200,NULL,'enforce',1)""")
            rows = new_audit_rows(db_file, 2, "s03-smoke", "agent")
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["run_id_is_null"])
            self.assertFalse(rows[0]["stream"])
            self.assertEqual(rows[0]["target"], "strata")

    def test_nondestructive_probe_does_not_send_inference(self):
        captured = []
        def fake_send(_base, path, _token, body=None, timeout=15.0):
            captured.append((path, body))
            if path == "/v1/models":
                return ((401, {}) if _token is None else
                        (200, {"data": [{"id": "agent"}]}))
            if path == "/debug/config":
                return 200, {"backend": "strata", "status": "attached",
                             "ownership": "attached", "aliases": [
                                 {"alias": "agent", "target": "strata",
                                  "injected_params": {"temperature": 0.2}}]}
            if path == "/debug/strata":
                return 200, {"backend": "strata", "ownership": "attached",
                             "available": True, "loaded": True}
            if path == "/debug/preview":
                return 200, {"original_model": "agent", "forwarded_model": "strata",
                             "forwarded_body": {"model": "strata",
                                                "messages": "<redacted>",
                                                "temperature": 0.2},
                             "policy_mode": "enforce"}
            if path == "/v1/load":
                return 404, {}
            raise AssertionError(f"Unexpected network call: {path}")
        options = Namespace(base_url="http://localhost:18001",
                            client_token_env="S03_SMOKE_CLIENT_TOKEN", alias="agent",
                            inference=False, db=None)
        with patch.dict(os.environ, {"S03_SMOKE_CLIENT_TOKEN": "only-a-test"}), \
                patch("scripts.s03_live_smoke.send", side_effect=fake_send):
            result = run(options)
        self.assertTrue(result["checks"]["native_strata_available"])
        self.assertEqual(result["checks"]["inference"],
                         "skipped: add --inference to send two small real requests")
        self.assertEqual([x[0] for x in captured],
                         ["/v1/models", "/debug/config", "/v1/models",
                          "/debug/strata", "/debug/preview", "/v1/load"])


if __name__ == "__main__":
    unittest.main()
