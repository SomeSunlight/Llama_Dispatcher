"""S00: characterization of the accepted llama.cpp configuration compiler.

All paths and model names are synthetic. No llama.cpp executable is launched.
"""
import hashlib
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import dispatcher  # noqa: E402
import dispatcher_core as core  # noqa: E402


class CompilerCharacterization(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profiles = self.root / "profiles"
        self.ensembles = self.root / "ensembles"
        self.engines = self.root / "engines"
        self.defaults = self.root / "defaults"
        self.data = self.root / "data"
        for folder in (self.profiles, self.ensembles, self.engines,
                       self.defaults, self.data, self.defaults / "engine-templates"):
            folder.mkdir(parents=True, exist_ok=True)

        self.write(self.defaults / "tiny.yaml", {
            "common": {
                "model": "$" + "{LLAMA_MODEL_ROOT}/tiny.gguf",
                "sampling": {"temperature": 0.95, "top_p": 0.91},
            },
            "serve": {"ctx-size": 4096},
        })
        self.write(self.engines / "cuda.yaml", {
            "bin_dir": "/engine/fallback",
            "common": {"sampling": {"temperature": 0.88}},
            "environment": {"CUDA_VISIBLE_DEVICES": "0"},
        })
        self.write(self.profiles / "work.yaml", {
            "defaults": {"model": "tiny", "engine": "cuda"},
            "common": {"sampling": {"temperature": 0.8}},
            "serve": {"sampling": {"top_k": 33}, "flash_attn": True},
        })
        self.write(self.ensembles / "test.yaml", {
            "defaults": {"engine": "cuda"},
            "engine": {"port": 8181, "models-max": 2},
            "model_defaults": {"threads": 2},
            "models": [
                {"profile": "work", "alias": "base", "sampling": {"temperature": 0.35}},
                {"profile": "work", "alias": "agent", "target": "base",
                 "sampling": {"temperature": 0.2},
                 "chat_template_kwargs": {"enable_thinking": False}},
            ],
        })
        stack = ExitStack()
        self.addCleanup(stack.close)
        for name, value in {
            "PROFILES_DIR": self.profiles,
            "ENSEMBLES_DIR": self.ensembles,
            "DEFAULTS_DIR": self.defaults,
            "DATA_DIR": self.data,
        }.items():
            stack.enter_context(patch.object(core, name, value))
        self.orc = object.__new__(core.LlamaOrchestrator)

    @staticmethod
    def write(path, data):
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def test_profile_default_cascade_and_ensemble_override(self):
        loaded = self.orc.load_profile("work")
        self.assertEqual(loaded["common"]["sampling"]["temperature"], 0.8)
        self.assertEqual(loaded["common"]["sampling"]["top_p"], 0.91)
        self.assertEqual(loaded["bin_dir"], "/engine/fallback")
        self.assertNotIn("defaults", loaded)
        params = self.orc._model_section_params(loaded, {"sampling": {"temperature": 0.35}})
        self.assertEqual(params["temperature"], 0.35)
        self.assertEqual(params["top-p"], 0.91)
        self.assertEqual(params["top-k"], 33)
        self.assertEqual(params["ctx-size"], 4096)
        self.assertIs(params["load-on-startup"], False)
        self.assertNotIn("bin-dir", params)
        self.assertNotIn("environment", params)

    def test_compile_ensemble_ini_and_proxy_only_alias(self):
        binary, compiled, args = self.orc.compile_serve_ensemble("test", {})
        exe = "llama-server.exe" if os.name == "nt" else "llama-server"
        self.assertEqual(binary, str(Path("/engine/fallback") / exe))
        self.assertEqual(list(compiled["models"]), ["base"])
        self.assertEqual(compiled["alias_targets"], {"agent": "base"})
        self.assertEqual(compiled["proxy_profiles"], {"base": "work", "agent": "work"})
        self.assertEqual(compiled["proxy_sampling"]["base"]["temperature"], 0.35)
        self.assertEqual(compiled["proxy_sampling"]["agent"]["temperature"], 0.2)
        self.assertEqual(compiled["proxy_sampling"]["agent"]["chat_template_kwargs"],
                         {"enable_thinking": False})
        ini = Path(compiled["preset_path"]).read_text(encoding="utf-8")
        self.assertIn("[*]\nthreads = 2", ini)
        self.assertIn("[base]\n", ini)
        self.assertNotIn("[agent]", ini)
        self.assertNotIn("chat-template-kwargs", ini)
        self.assertIn("load-on-startup = false", ini)
        self.assertIn("--models-preset", args)
        self.assertIn("--models-max", args)
        self.assertNotIn("--bin-dir", args)
        self.assertEqual(compiled["preset_sha256"],
                         hashlib.sha256(ini.encode("utf-8")).hexdigest())

    def test_invalid_proxy_target_fails_before_start(self):
        self.write(self.ensembles / "bad.yaml", {
            "models": [{"profile": "work", "alias": "agent", "target": "missing"}],
        })
        with self.assertRaisesRegex(ValueError, "not a .real. model|no real models"):
            self.orc.compile_serve_ensemble("bad", {})

    def test_runtime_launcher_overrides_binary_and_expands_model_root(self):
        # The launcher monkeypatches class methods process-wide. Restore *all* of them
        # after this test so the characterization suite does not change other tests.
        methods = ("load_yaml", "load_profile", "_resolve_server_binary",
                   "compile_task_profile", "run_profile_server_loop",
                   "run_server_loop", "run_bench", "run_eval")
        original_methods = {name: getattr(core.LlamaOrchestrator, name) for name in methods}
        original_parse = core.parse_cli_overrides
        original_canonicalize = core.canonicalize_params
        runtime_bin = self.root / "runtime-bin"
        model_root = self.root / "models"
        try:
            dispatcher.install_runtime_overrides(str(runtime_bin), str(model_root))
            binary, compiled, args = self.orc.compile_serve_ensemble("test", {})
            exe = "llama-server.exe" if os.name == "nt" else "llama-server"
            self.assertEqual(binary, str(runtime_bin / exe))
            self.assertEqual(compiled["models"]["base"]["model"], str(model_root / "tiny.gguf"))
            self.assertNotIn("--bin-dir", args)

            direct_binary, direct, direct_args = self.orc.compile_serve_profile("work", {})
            self.assertEqual(direct_binary, str(runtime_bin / exe))
            self.assertTrue(direct["single_profile"])
            self.assertNotIn("--models-preset", direct_args)
            self.assertIn(str(model_root / "tiny.gguf"), direct_args)
            self.assertNotIn("--environment", direct_args)
        finally:
            for name, method in original_methods.items():
                setattr(core.LlamaOrchestrator, name, method)
            core.parse_cli_overrides = original_parse
            core.canonicalize_params = original_canonicalize


if __name__ == "__main__":
    unittest.main()
