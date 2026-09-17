import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from runtime_paths import (  # noqa: E402
    MODEL_ROOT_TOKEN,
    RuntimePathError,
    expand_model_root,
    resolve_runtime_path_options,
    task_binary_name,
)


class RuntimePathTests(unittest.TestCase):
    def test_cli_values_are_removed_and_cli_model_root_wins(self):
        opts = resolve_runtime_path_options(
            ["serve", "--instance", "Laptop", "--model-root", "/mnt/c/models", "--bin-dir=/opt/llama/bin"],
            {"LLAMA_MODEL_ROOT": "/ignored"},
        )
        self.assertEqual(opts.argv, ["serve", "--instance", "Laptop"])
        self.assertEqual(opts.bin_dir, "/opt/llama/bin")
        self.assertEqual(opts.model_root, "/mnt/c/models")
        self.assertEqual(opts.model_root_source, "cli")

    def test_environment_is_only_a_fallback(self):
        opts = resolve_runtime_path_options(["bench", "--profile", "x"], {"LLAMA_MODEL_ROOT": "/models"})
        self.assertEqual(opts.model_root, "/models")
        self.assertEqual(opts.model_root_source, "environment")

    def test_posix_model_root_expansion(self):
        payload = {"common": {"m": f"{MODEL_ROOT_TOKEN}/gemma/model.gguf"}}
        expanded = expand_model_root(payload, "/mnt/c/AI_Models/LLM")
        self.assertEqual(expanded["common"]["m"], "/mnt/c/AI_Models/LLM/gemma/model.gguf")

    def test_windows_model_root_expansion(self):
        value = f"{MODEL_ROOT_TOKEN}/gemma/model.gguf"
        self.assertEqual(
            expand_model_root(value, r"C:\AI_Models\LLM"),
            r"C:\AI_Models\LLM\gemma\model.gguf",
        )

    def test_unresolved_placeholder_fails_clearly(self):
        with self.assertRaisesRegex(RuntimePathError, "--model-root"):
            expand_model_root(f"{MODEL_ROOT_TOKEN}/model.gguf", None)

    def test_task_binary_names_are_cross_platform(self):
        self.assertEqual(task_binary_name("bench", "posix"), "llama-bench")
        self.assertEqual(task_binary_name("eval", "posix"), "llama-perplexity")
        self.assertEqual(task_binary_name("bench", "nt"), "llama-bench.exe")
        self.assertEqual(task_binary_name("eval", "nt"), "llama-perplexity.exe")

    def test_duplicate_runtime_option_is_rejected(self):
        with self.assertRaisesRegex(RuntimePathError, "only once"):
            resolve_runtime_path_options(["serve", "--bin-dir", "/a", "--bin-dir", "/b"], {})


if __name__ == "__main__":
    unittest.main()
