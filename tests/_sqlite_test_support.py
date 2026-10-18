"""Test-only helper: collect SQLite cursors/connections before Windows temp cleanup.

The production MetricsDatabase uses sqlite3 Connection context managers, whose
__exit__ commits/rolls back but does NOT close the connection. Some SQLite
connection/cursor cycles are reclaimed only by GC; Windows refuses to unlink
an open metrics.db. Do not silently change production behavior in S00.
"""
from contextlib import contextmanager
import gc
import tempfile


@contextmanager
def sqlite_temp_directory():
    with tempfile.TemporaryDirectory() as folder:
        try:
            yield folder
        finally:
            gc.collect()
