"""S00 start-provenance baseline has no network, engine or real process dependency."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def test_windows_duplicate_python_launchers_choose_only_tcp_owner(self):
        # uv/Python redirectors may expose two otherwise identical commands.
        # Neither process may be killed, and selection may not use list order.
        candidate = lambda pid: {
            "pid": pid,
            "command": r"python.exe src\dispatcher.py serve --ensemble 3090 --instance Speedy_Win",
            "capture": "win32_process_commandline",
            "ensemble": "3090",
        }
        rows = [candidate(101), candidate(202)]
        with patch.object(prov, "_windows_listener_pids", return_value={202}) as lookup:
            selected = prov._select_windows_candidate(rows, 8001)
        self.assertEqual(selected["pid"], 202)
        self.assertEqual(selected["capture"], "win32_tcp_listener_process")
        self.assertEqual(rows[0]["capture"], "win32_process_commandline")
        lookup.assert_called_once_with(8001)

    def test_windows_ambiguous_listener_still_fails_without_killing(self):
        rows = [{"pid": 101}, {"pid": 202}]
        for owners in ({}, {999}, {101, 202}):
            with self.subTest(owners=owners), \
                 patch.object(prov, "_windows_listener_pids", return_value=owners):
                with self.assertRaisesRegex(prov.ProvenanceError, "could not uniquely match"):
                    prov._select_windows_candidate(rows, 8001)

    def test_windows_tcp_listener_parser_handles_one_or_several_owners(self):
        for stdout, expected in (
            ("[202]", {202}),
            ("202", {202}),
            ("[101,202]", {101, 202}),
            ("[]", set()),
            ("", set()),
        ):
            with self.subTest(stdout=stdout), \
                 patch.object(prov.subprocess, "run",
                              return_value=SimpleNamespace(returncode=0, stdout=stdout)) as run:
                self.assertEqual(prov._windows_listener_pids(8001), expected)
                ps = run.call_args.args[0][-1]
                self.assertIn("Get-NetTCPConnection -State Listen -LocalPort 8001", ps)

    def test_windows_duplicate_python_can_use_explicit_unverified_fallback(self):
        observed = [
            {"pid": 101, "command": "python src/dispatcher.py serve --ensemble 3090 --instance Speedy_Win",
             "ensemble": "3090"},
            {"pid": 202, "command": "python src/dispatcher.py serve --ensemble 3090 --instance Speedy_Win",
             "ensemble": "3090"},
        ]
        declared = r"uv run src/dispatcher.py serve --ensemble 3090 --instance Speedy_Win --model-root c:\AI_Models\LLM\GGUF_Raw"
        with patch.object(prov.os, "name", "nt"), \
             patch.object(prov, "_windows_candidates", return_value=observed), \
             patch.object(prov, "_windows_listener_pids", return_value=set()):
            with self.assertRaisesRegex(prov.ProvenanceError, "could not uniquely match"):
                prov.find_launch("Speedy_Win", proxy_port=8001)
            fallback = prov.find_launch("Speedy_Win", declared, proxy_port=8001)
        self.assertEqual(fallback["capture"], "user_declared_unverified")
        self.assertEqual(fallback["command"], declared)

    def test_provenance_receives_proxy_port_and_passes_it_through(self):
        launch = {"command": "python src/dispatcher.py serve --ensemble 3090 --instance Speedy_Win",
                  "capture": "win32_tcp_listener_process", "ensemble": "3090"}
        snap = {"core_commit": "sha-core", "instance_commit": "sha-instance",
                "instance_yaml_sha256": "sha-yaml", "yaml_count": 3}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(prov, "find_launch", return_value=launch) as find, \
             patch.object(prov, "config_snapshot", return_value=snap):
            self.assertEqual(prov.pin_startup("Speedy_Win", Path(tmp), None,
                                              proxy_port=8001)["status"], "PASS")
        find.assert_called_once_with("Speedy_Win", None, proxy_port=8001)

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
