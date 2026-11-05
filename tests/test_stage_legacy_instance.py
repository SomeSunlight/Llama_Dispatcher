"""Offline Speedy instance migration: preserve old metrics, refuse overwrite."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stage_legacy_instance import stage  # noqa: E402


class StageInstanceTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.root = Path(self.workspace.name)
        self.source = self.root / "legacy" / "instances" / "Speedy_Win"
        self.destination = self.root / "review"
        for folder in ("engines", "profiles", "ensembles", "data"):
            (self.source / folder).mkdir(parents=True, exist_ok=True)
        (self.source / "instance.yaml").write_text(
            "machine_guid: preserved-machine-guid\n", encoding="utf-8")
        (self.source / "ensembles" / "3090.yaml").write_text(
            "models: []\n", encoding="utf-8")
        (self.source / "engines" / "cuda.yaml").write_text(
            "bin_dir: placeholder\n", encoding="utf-8")
        (self.source / "profiles" / "agent.yaml").write_text(
            "model: placeholder\n", encoding="utf-8")
        (self.destination / ".git").mkdir(parents=True)
        (self.destination / "src").mkdir()
        (self.destination / "src" / "dispatcher.py").touch()
        (self.destination / "instances").mkdir()
        self.legacy_db = self.source / "data" / "metrics.db"
        self.legacy = sqlite3.connect(self.legacy_db)
        self.legacy.execute("PRAGMA journal_mode=WAL")
        self.legacy.execute("PRAGMA user_version=9")
        self.legacy.execute("CREATE TABLE metrics_proxy_requests (id INTEGER PRIMARY KEY, client_id TEXT)")
        self.legacy.execute("INSERT INTO metrics_proxy_requests(client_id) VALUES('old-identity')")
        self.legacy.commit()

    def tearDown(self):
        self.legacy.close()
        self.workspace.cleanup()

    def test_dry_run_no_write_and_no_overwrite(self):
        path = stage(self.source, self.destination, "Speedy_Win", apply=False)
        self.assertFalse(path.exists())
        self.assertTrue(self.legacy_db.exists())
        stage(self.source, self.destination, "Speedy_Win", apply=True)
        self.assertEqual(
            (path / "instance.yaml").read_text().strip(),
            "machine_guid: preserved-machine-guid",
        )
        self.assertTrue((path / "ensembles" / "3090.yaml").exists())
        with sqlite3.connect(path / "data" / "metrics.db") as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 9)
            self.assertEqual(db.execute(
                "SELECT client_id FROM metrics_proxy_requests").fetchone()[0], "old-identity")
        self.legacy.execute("INSERT INTO metrics_proxy_requests(client_id) VALUES('new-legacy-row')")
        self.legacy.commit()
        with sqlite3.connect(path / "data" / "metrics.db") as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM metrics_proxy_requests").fetchone()[0], 1)
        with self.assertRaisesRegex(ValueError, "already exists"):
            stage(self.source, self.destination, "Speedy_Win", apply=True)

    def test_missing_or_corrupt_source_rejected(self):
        broken = self.root / "corrupt" / "instances" / "broken"
        for folder in ("engines", "profiles", "ensembles", "data"):
            (broken / folder).mkdir(parents=True, exist_ok=True)
        (broken / "instance.yaml").write_text("machine_guid: none\n")
        (broken / "data" / "metrics.db").write_text("not sqlite")
        with self.assertRaises(sqlite3.DatabaseError):
            stage(broken, self.destination, "broken", apply=True)
        self.assertFalse((self.destination / "instances" / "broken").exists())


if __name__ == "__main__":
    unittest.main()
