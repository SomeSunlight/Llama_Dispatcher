import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from engine_environment import (  # noqa: E402
    EngineEnvironmentError,
    applied_process_environment,
    engine_name_from_config,
    load_engine_environment,
)


class EngineEnvironmentTests(unittest.TestCase):
    def test_engine_name_is_read_from_defaults(self):
        self.assertEqual(engine_name_from_config({"defaults": {"engine": "vulkan"}}), "vulkan")
        self.assertIsNone(engine_name_from_config({"defaults": {}}))

    def test_instance_engine_environment_wins_over_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "instance"
            templates = root / "templates"
            instance.mkdir()
            templates.mkdir()
            (templates / "vulkan.yaml").write_text(
                'environment:\n  GGML_VK_VISIBLE_DEVICES: "9"\n', encoding="utf-8"
            )
            (instance / "vulkan.yaml").write_text(
                'environment:\n  GGML_VK_VISIBLE_DEVICES: "0"\n', encoding="utf-8"
            )
            self.assertEqual(
                load_engine_environment("vulkan", instance, templates),
                {"GGML_VK_VISIBLE_DEVICES": "0"},
            )

    def test_scalar_values_are_normalized_to_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "instance"
            templates = root / "templates"
            instance.mkdir()
            templates.mkdir()
            (instance / "sycl.yaml").write_text(
                "environment:\n  ONEAPI_DEVICE_SELECTOR: level_zero:0\n  TEST_FLAG: true\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_engine_environment("sycl", instance, templates),
                {"ONEAPI_DEVICE_SELECTOR": "level_zero:0", "TEST_FLAG": "true"},
            )

    def test_invalid_environment_shape_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "instance"
            templates = root / "templates"
            instance.mkdir()
            templates.mkdir()
            (instance / "vulkan.yaml").write_text("environment: [bad]\n", encoding="utf-8")
            with self.assertRaisesRegex(EngineEnvironmentError, "must be a mapping"):
                load_engine_environment("vulkan", instance, templates)

    def test_process_environment_is_restored(self):
        key = "DISPATCHER_TEST_ENGINE_ENV"
        os.environ.pop(key, None)
        with applied_process_environment({key: "inside"}):
            self.assertEqual(os.environ[key], "inside")
        self.assertNotIn(key, os.environ)


if __name__ == "__main__":
    unittest.main()
