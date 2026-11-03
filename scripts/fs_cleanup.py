"""Best-effort cleanup for S02's *owned, disposable* authentication fixture.

Do not use for database files, installed models, accepted profiles or any
unknown path. Never kill another process or suppress test failures.
"""
from __future__ import annotations

import shutil
import stat
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

DELAYS = (0.0, 0.05, 0.15, 0.35)


class UnsafeCleanupError(OSError):
    """A path contains a link, junction or non-directory entry."""


def _owned_directories(root: Path) -> list[Path]:
    """Reject links, junctions and uninspectable entries before recursion."""
    info = root.lstat()
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & flag:
        raise UnsafeCleanupError(f"not an ordinary private fixture directory: {root}")
    stack, folders = [root], []
    while stack:
        parent = stack.pop()
        folders.append(parent)
        for entry in parent.iterdir():
            attr = entry.lstat()
            if stat.S_ISLNK(attr.st_mode) or getattr(attr, "st_file_attributes", 0) & flag:
                raise UnsafeCleanupError(f"refusing linked/reparse fixture entry: {entry}")
            if stat.S_ISDIR(attr.st_mode):
                stack.append(entry)
    return folders


def _fileless(root: Path) -> bool:
    try:
        return all(all(item.is_dir() for item in folder.iterdir())
                   for folder in _owned_directories(root))
    except OSError:
        return False


def remove_private_fixture(root: Path, *, delays=DELAYS) -> bool:
    """Retry owned temporary cleanup; tolerate only recursively fileless bones.

    A persistent lock with files is *reported*, never disguised as success.
    The S02 test result itself must not be overwritten by cleanup failure.
    """
    if not root.exists() and not root.is_symlink():
        return True
    for index, delay in enumerate(delays):
        if index and delay:
            time.sleep(delay)
        try:
            _owned_directories(root)
            shutil.rmtree(root)
            return True
        except UnsafeCleanupError:
            raise
        except OSError:
            if not root.exists():
                return True
            if _fileless(root):
                for folder in sorted(_owned_directories(root), key=lambda p: len(p.parts),
                                     reverse=True):
                    try:
                        folder.rmdir()
                    except OSError:
                        pass
                return True
    return False


@contextmanager
def private_test_directory():
    root = Path(tempfile.mkdtemp(prefix="s02-private-"))
    try:
        yield root
    finally:
        # Only this function's newly created directory is ever eligible.
        try:
            removed_or_fileless = remove_private_fixture(root)
        except OSError as exc:
            removed_or_fileless = False
            print(f"S02 WARNING: refused unsafe temporary cleanup: {exc}", file=sys.stderr)
        if not removed_or_fileless:
            print(f"S02 WARNING: temporary test files remain locked at {root}; "
                  "remove them when Windows releases the handles.", file=sys.stderr)
