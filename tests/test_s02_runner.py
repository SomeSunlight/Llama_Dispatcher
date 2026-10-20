"""Fast self-tests for the operator-facing S02 runner; no processes started."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from client_policy import load_client_security  # noqa: E402

spec = importlib.util.spec_from_file_location("s02_verify", ROOT / "scripts" / "s02_verify.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class OwnerRunnerTests(unittest.TestCase):
    def test_all_targets_are_explicitly_loopback_and_manual_by_default(self):
        self.assertEqual(set(runner.MACHINES), {
            "Laptop_Win", "Laptop_WSL", "Speedy_Win", "Speedy_WSL",
        })
        for config in runner.MACHINES.values():
            self.assertIsNone(config["start_command"])
            runner.endpoint(config["url"])
        for url in ("https://example.org:8080", "http://192.168.0.12:8001",
                    "http://127.0.0.1:8080/strata/v1"):
            with self.assertRaises(runner.CheckError):
                runner.endpoint(url)

    def test_private_fixture_is_valid_and_does_not_contain_bearer_tokens(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            keys = runner.auth_fixture(folder)
            doc = json.loads((folder / "clients.json").read_text(encoding="utf-8"))
            self.assertEqual([x["id"] for x in doc["clients"]], ["goose", "open-webui"])
            self.assertEqual([x["policy"] for x in doc["clients"]],
                             ["enforce", "default"])
            self.assertNotEqual(keys["goose"], keys["open-webui"])
            self.assertTrue(all(raw not in json.dumps(doc) for raw in keys.values()))
            security = load_client_security(str(folder / "clients.json"))
            for identity, token in keys.items():
                self.assertEqual(security.authenticate("Bearer " + token).client_id, identity)

    def test_refuses_unrelated_or_cross_instance_process_command(self):
        correct = ["uv", "run", "python", "src/dispatcher.py", "serve",
                   "--ensemble", "test", "--instance", "Laptop_Win"]
        runner.check_command(correct, "Laptop_Win")
        for command in (
            ["strata", "--data-dir", "local"],
            ["python", "src/dispatcher.py", "serve", "--ensemble", "test",
             "--instance", "Speedy_Win"],
            ["python", "src/dispatcher.py", "bench", "--ensemble", "test",
             "--instance", "Laptop_Win"],
        ):
            with self.assertRaises(runner.CheckError):
                runner.check_command(command, "Laptop_Win")


if __name__ == "__main__":
    unittest.main()
