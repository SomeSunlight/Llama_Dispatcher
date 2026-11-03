"""Cleanup regressions without live processes, models, or services."""
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts.fs_cleanup import private_test_directory, remove_private_fixture


class CleanupTests(unittest.TestCase):
    def test_transient_lock_recovers(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "owned"
            folder.mkdir()
            (folder / "clients.json").write_text("{}", encoding="utf-8")
            actual = shutil.rmtree
            calls = []

            def flaky(path):
                calls.append(path)
                if len(calls) == 1:
                    raise PermissionError("scanner lock")
                return actual(path)

            with patch("scripts.fs_cleanup.shutil.rmtree", side_effect=flaky):
                self.assertTrue(remove_private_fixture(folder, delays=(0, 0)))
            self.assertEqual(2, len(calls))

    def test_fileless_locked_skeleton_is_benign(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "owned"
            (folder / "nested" / "refs").mkdir(parents=True)
            with patch("scripts.fs_cleanup.shutil.rmtree", side_effect=PermissionError("locked")):
                with patch("scripts.fs_cleanup.Path.rmdir", side_effect=PermissionError("locked")):
                    self.assertTrue(remove_private_fixture(folder, delays=(0,)))
            self.assertTrue(folder.exists())

    def test_persistent_lock_warns_without_masking_result(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "s02-private-test"
            folder.mkdir()
            with patch("scripts.fs_cleanup.tempfile.mkdtemp", return_value=str(folder)):
                with patch("scripts.fs_cleanup.shutil.rmtree", side_effect=PermissionError("locked")):
                    output = io.StringIO()
                    with redirect_stderr(output):
                        with private_test_directory() as owned:
                            (owned / "clients.json").write_text("{}", encoding="utf-8")
            self.assertIn("remain locked", output.getvalue())
            self.assertTrue((folder / "clients.json").is_file())

    def test_link_safety(self):
        with tempfile.TemporaryDirectory() as temp:
            external = Path(temp) / "external"
            external.mkdir()
            (external / "keep").write_text("safe", encoding="utf-8")
            owned = Path(temp) / "owned"
            owned.mkdir()
            try:
                (owned / "link").symlink_to(external, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks not permitted on this machine")
            with self.assertRaises(OSError):
                remove_private_fixture(owned, delays=(0,))
            self.assertTrue((external / "keep").exists())
