# Resilient filesystem cleanup — shared development method

Use this reference whenever a project creates and later removes generated, scratch, staging, or other tool-owned directories. Windows antivirus scanners, IDE indexers, search services and concurrent processes can temporarily hold handles that prevent directory deletion; similar races are possible elsewhere. **Do not require users to disable antivirus protection.**

## Contract

1. **Own the scope.** Operate only below a specifically identified tool-owned root. Never recursively delete an unknown directory merely because it looks old. Never follow symlinks, junctions, or other reparse points.
2. **Separate data from directory bookkeeping.** A missing authoritative file, invalid package manifest, or a directory with even one unexpected file is *not* an empty leftover. Preserve it and report an integrity/ownership error. An entirely **fileless** directory tree (including its nested empty directories) is different: it is safe to attempt to remove, but never pretend it was a valid package.
3. **Remove in dependency order.** Finish any verified data move/publication before cleanup. Remove known disposable files only after their transaction is committed. For empty directories, traverse deepest-first and use **nonrecursive** `rmdir` on each; this cannot delete a concurrently created file.
4. **Bounded retries.** Retry transient access/permission/sharing failures a few times with small increasing delays (e.g. 0, 50, 150 and 350 ms). Do not retry a nonempty directory as though it were a lock. Never wait indefinitely or force close another process's handle.
5. **Benign leftovers.** If a truly empty tool-owned directory stays locked, keep it, optionally warn once, and retry during the next normal mutating maintenance/build. Read-only `check` must not clean up.
6. **Resilience on read.** Directory enumeration and allocation must explicitly distinguish (a) valid immutable package, (b) recursively fileless orphan, and (c) nonempty invalid/corrupt package. Skip (b) for read-only inventory; reject (c). A blocked orphan may require a different unused storage token; do not overwrite it.
7. **Tests.** Exercise normal deletion, simulated lock then success, lock exhaustion, repeated cleanup, a newly created file during deletion, nonempty corrupt content, and symlink/junction safety. Protect authoritative data even on partial failure.

## Python reference pattern

Put the implementation in **one project helper**, then call it everywhere instead of repeating `except OSError: pass`. For Python-based ContextCanon the runnable implementation lives in `src/contextcanon/fs_cleanup.py` (repository root; implementation detail, not a Topic Resource). The minimal nonrecursive primitive is:

```python
from pathlib import Path
import errno
import time

def try_rmdir(path: Path) -> bool:
    for delay in (0, .05, .15, .35):
        time.sleep(delay)
        try:
            path.rmdir()  # never rmtree: does not remove any files
            return True
        except OSError as error:
            if error.errno in (errno.ENOTEMPTY, errno.EEXIST):
                return False
    return False  # benign only when this is known disposable directory state
```

Before using it, verify the root/descendants are not links or reparse points. Never use this primitive to excuse a failed removal of committed/accepted data.

## PowerShell reference pattern

```powershell
function Remove-EmptyOwnedDirectory {
    param([Parameter(Mandatory)][string]$Path)
    foreach ($delay in @(0, 50, 150, 350)) {
        if ($delay) { Start-Sleep -Milliseconds $delay }
        try {
            # [IO.Directory]::Delete(path, $false) is nonrecursive.
            [IO.Directory]::Delete($Path, $false)
            return $true
        }
        catch [IO.DirectoryNotFoundException] { return $true }
        catch [IO.IOException] {
            if (@([IO.Directory]::EnumerateFileSystemEntries($Path)).Count -gt 0) { return $false }
        }
        catch [UnauthorizedAccessException] { }
    }
    return $false
}
```

Scope verification (including reparse points), error classification and logging belong in the shared project wrapper. If an entire staging tree may be locked, **prefer creating a fresh unique owned stage and leaving the old one for later cleanup** over making installation depend on deleting the previous stage. Never recycle a partially deleted tree.
