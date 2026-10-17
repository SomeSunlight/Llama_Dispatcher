"""S00 start-provenance baseline has no network, engine or real process dependency."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import s00_provenance as prov  # noqa: E402


class ProvenanceTests(unittest.TestCase):
    def test_match_exact_instance_and_command(self):
        argv = ["/usr/bin/python3", "src/dispatcher.py", "serve",
                "--ensemble", "3090", "--instance", "Speedy_Win",
                "--model-root", "/mnt/c/AI Models/LLM"]
        self.assertTrue(prov._matches("Speedy_Win", argv))
        self.assertFalse(prov._matches("Speedy", argv))
        self.assertFalse(prov._matches("Speedy_WSL", argv))
        self.assertEqual(prov._argument(argv, "--model-root"), "/mnt/c/AI Models/LLM")

    def test_declared_command_requires_explicit_correct_instance_and_ensemble(self):
        cmd = r"uv run src/dispatcher.py serve --ensemble 3090 --instance Speedy_Win --model-root c:\AI_Models\LLM\GGUF_Raw"
        launch = prov._declared("Speedy_Win", cmd)
        self.assertEqual(launch["ensemble"], "3090")
        self.assertEqual(launch["command"], cmd)
        self.assertEqual(launch["capture"], "user_declared_unverified")
        with self.assertRaisesRegex(prov.ProvenanceError, "must use --instance"):
            prov._declared("Speedy_WSL", cmd)
        with self.assertRaisesRegex(prov.ProvenanceError, "requires --ensemble"):
            prov._declared("Speedy_Win", "uv run src/dispatcher.py serve --instance Speedy_Win")

    def test_pins_command_and_config_and_detects_drift(self):
        cmd = r"python src/dispatcher.py serve --ensemble 3090 --instance Speedy_Win --model-root c:\AI_Models"
        launch = {"command": cmd, "capture": "win32_process_commandline",
                  "ensemble": "3090"}
        snap = {"core_commit": "sha-core", "instance_commit": "sha-config",
                "instance_yaml_sha256": "hash-yaml", "yaml_count": 5}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(prov, "find_launch", return_value=launch), \
             patch.object(prov, "config_snapshot", return_value=snap):
            folder = Path(temp)
            first = prov.pin_startup("Speedy_Win", folder, None)
            self.assertEqual(first["status"], "PASS")
            private = folder / "s00-Speedy_Win.baseline.json"
            self.assertTrue(private.exists())
            pinned = json.loads(private.read_text(encoding="utf-8"))
            self.assertEqual(pinned["command"], cmd)
            self.assertNotIn(cmd, json.dumps(first))
            self.assertEqual(prov.pin_startup("Speedy_Win", folder, None),
                             first)
            snap["instance_yaml_sha256"] = "changed"
            with self.assertRaisesRegex(prov.ProvenanceError, "baseline changed"):
                prov.pin_startup("Speedy_Win", folder, None)
            self.assertEqual(json.loads(private.read_text())["instance_yaml_sha256"],
                             "hash-yaml")

    def test_config_snapshot_checks_instance_before_mutation(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(prov, "ROOT", Path(temp)):
            with self.assertRaisesRegex(prov.ProvenanceError, "Instance folder is missing"):
                prov.config_snapshot("Speedy_Win", "3090")
            base = Path(temp) / "instances" / "Speedy_Win"
            (base / "ensembles").mkdir(parents=True)
            (base / "instance.yaml").write_text("nickname: Speedy_Win")
            with self.assertRaisesRegex(prov.ProvenanceError, "Missing ensemble"):
                prov.config_snapshot("Speedy_Win", "3090")
            (base / "ensembles" / "3090.yaml").write_text("models: []")
            first = prov.config_snapshot("Speedy_Win", "3090")
            (base / "ensembles" / "3090.yaml").write_text("models: [changed]")
            second = prov.config_snapshot("Speedy_Win", "3090")
            self.assertNotEqual(first["instance_yaml_sha256"],
                                second["instance_yaml_sha256"])


if __name__ == "__main__":
    unittest.main()
