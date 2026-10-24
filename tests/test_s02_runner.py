"""Fast self-tests for the operator-facing S02 runner; no processes started."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from client_policy import load_client_security  # noqa: E402

spec = importlib.util.spec_from_file_location("s02_verify", ROOT / "scripts" / "s02_verify.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class OwnerRunnerTests(unittest.TestCase):
    def test_one_runner_accepts_explicit_local_instance_without_machine_table(self):
        self.assertEqual(runner.endpoint(runner.DEFAULT_URL), ("127.0.0.1", 8001))
        for url in ("https://example.org:8080", "http://192.168.0.12:8001",
                    "http://127.0.0.1:8080/strata/v1"):
            with self.assertRaises(runner.CheckError):
                runner.endpoint(url)
        with self.assertRaises(runner.CheckError):
            runner.launch_file("../outside")

    def test_capture_and_reload_verified_local_start_without_process_control(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            argv = [sys.executable, str(root / "src" / "dispatcher.py"),
                    "serve", "--ensemble", "test", "--instance", "Laptop_Win"]
            observation = {"capture": "procfs_python_argv", "argv": argv}
            with (patch.object(runner, "ROOT", root),
                  patch.object(runner, "is_listening", return_value=True),
                  patch.object(runner, "find_launch", return_value=observation)):
                runner.save_start("Laptop_Win", runner.DEFAULT_URL)
                private_file = runner.launch_file("Laptop_Win")
                self.assertTrue(private_file.is_file())
                self.assertEqual(
                    runner.load_start("Laptop_Win", runner.DEFAULT_URL), argv,
                )
                with self.assertRaises(runner.CheckError):
                    runner.load_start("Laptop_WSL", runner.DEFAULT_URL)
                with self.assertRaises(runner.CheckError):
                    runner.load_start("Laptop_Win", "http://127.0.0.1:8100")

    def test_dispatcher_logs_are_unique_persistent_and_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(runner, "ROOT", Path(temp)):
                one = runner.dispatcher_log_path("Laptop_Win")
                self.assertEqual(one.parent, Path(temp) / "reports")
                self.assertFalse(one.exists())
                self.assertEqual(one.parent.name, "reports")
                with self.assertRaises(runner.CheckError):
                    runner.dispatcher_log_path("../other")
                one.write_text(
                    "early log line\n" * 35
                    + "Authorization: Bearer private-test-token\n"
                    + "Error: local model failed to load\n",
                    encoding="utf-8",
                )
                excerpt = runner.log_tail(one, max_lines=3)
                self.assertIn("model failed to load", excerpt)
                self.assertIn("<redacted>", excerpt)
                self.assertNotIn("private-test-token", excerpt)
                self.assertNotIn("early log line", excerpt)
                # A missing file gives a human-readable reason, not an exception.
                self.assertIn("missing", runner.log_tail(one.with_name("missing.log")))

    def test_empty_log_describes_exited_without_output(self):
        with tempfile.TemporaryDirectory() as temp:
            empty = Path(temp) / "empty.log"
            empty.write_text("", encoding="utf-8")
            self.assertIn("no output", runner.log_tail(empty))

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
        correct = [sys.executable, "src/dispatcher.py", "serve",
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
