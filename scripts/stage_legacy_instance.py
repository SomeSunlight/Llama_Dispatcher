#!/usr/bin/env python3
"""Stage one existing Dispatcher instance in a NEW Git checkout, without overwrites.

Copies authored instance.yaml/engines/profiles/ensembles and a SQLite online
backup of historical metrics.db. Never copies code checkout, WAL/SHM or
current S03 Stage metrics. No running process is started, stopped or adopted.
Dry run by default; --apply requires explicit operator action.
"""
from __future__ import annotations
from contextlib import closing
import argparse
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile


def verify_database(path: Path) -> int:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or linked historical SQLite database.")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Legacy metrics database failed SQLite integrity check.")
        return int(db.execute("PRAGMA user_version").fetchone()[0])


def backup_database(origin: Path, destination: Path) -> None:
    # SQLite's backup API includes committed WAL content and produces one
    # consistent database snapshot. Do not copy SQLite -wal/-shm directly.
    with closing(sqlite3.connect(origin.as_uri() + "?mode=ro", uri=True, timeout=15)) as source:
        with closing(sqlite3.connect(destination, timeout=15)) as target:
            source.backup(target, pages=1000, sleep=0.05)
    verify_database(destination)


def stage(source: Path, checkout: Path, dest_name: str, *, apply: bool) -> Path:
    if not dest_name or not all(c.isalnum() or c in "_-" for c in dest_name):
        raise ValueError("Invalid destination instance name.")
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Missing or linked source instance.")
    if not (checkout / ".git").exists() or not (checkout / "src" / "dispatcher.py").is_file():
        raise ValueError("Destination must be a Llama_Dispatcher Git checkout.")
    target = checkout / "instances" / dest_name
    if target.exists() or target.is_symlink():
        raise ValueError("Destination instance already exists; no overwrite.")
    if not (source / "instance.yaml").is_file() or (source / "instance.yaml").is_symlink():
        raise ValueError("Source instance.yaml missing or linked.")
    config_dirs = ("engines", "profiles", "ensembles")
    for name in config_dirs:
        folder = source / name
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError("Missing or linked instance config folder: " + name)
        for item in folder.rglob("*"):
            if item.is_symlink():
                raise ValueError("Linked instance configuration refused.")
    metrics = source / "data" / "metrics.db"
    version = verify_database(metrics)
    print("Historical instance:", source)
    print("New independent instance:", target)
    print("Historical metrics user_version:", version)
    print("Source and current S03 Stage SQLite are NEVER changed.")
    if not apply:
        print("[PREVIEW] Nothing copied. Use --apply to stage the new instance.")
        return target
    parent = target.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("Destination instances folder must already exist.")
    temp = Path(tempfile.mkdtemp(prefix=".stage-legacy-", dir=parent))
    complete = False
    try:
        # Preserve the INSTANCE REPOSITORY's branch and Git metadata when the
        # source is independently versioned (e.g. Speedy_Win). Never clone the
        # legacy Dispatcher CODE checkout over a new runtime checkout.
        if (source / ".git").exists():
            clean = subprocess.run(
                ["git", "-C", str(source), "status", "--porcelain"],
                capture_output=True, text=True, check=True,
            )
            if clean.stdout.strip():
                raise ValueError("Source instance Git repository has uncommitted changes; review them first.")
            subprocess.run(
                ["git", "clone", "--quiet", "--no-hardlinks", "--local",
                 str(source), str(temp)],
                check=True, capture_output=True, text=True,
            )
            previous_remote = subprocess.run(
                ["git", "-C", str(source), "remote", "get-url", "origin"],
                capture_output=True, text=True, check=False,
            )
            if previous_remote.returncode == 0 and previous_remote.stdout.strip():
                subprocess.run(
                    ["git", "-C", str(temp), "remote", "set-url", "origin",
                     previous_remote.stdout.strip()],
                    check=True, capture_output=True,
                )
        else:
            shutil.copy2(source / "instance.yaml", temp / "instance.yaml")
            for name in config_dirs:
                shutil.copytree(source / name, temp / name)
        (temp / "data").mkdir(exist_ok=True)
        if (temp / "data" / "metrics.db").exists():
            raise ValueError("Cloned instance unexpectedly contains a tracked metrics.db.")
        backup_database(metrics, temp / "data" / "metrics.db")
        if target.exists() or target.is_symlink():
            raise ValueError("Destination appeared while copying; aborting.")
        os.rename(temp, target)  # same filesystem, staged as one directory
        complete = True
    finally:
        if not complete:
            shutil.rmtree(temp, ignore_errors=True)
    print("[OK] Instance staged; original historical database preserved.")
    print("The program source code has NOT been copied or replaced.")
    print("If the source was an independent Git repo, its repository metadata was preserved.")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-instance", type=Path, required=True)
    parser.add_argument("--destination-checkout", type=Path, required=True)
    parser.add_argument("--destination-name", default="Speedy_Win")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    stage(args.source_instance.expanduser(), args.destination_checkout.expanduser(),
          args.destination_name, apply=args.apply)


if __name__ == "__main__":
    try:
        main()
    except (OSError, sqlite3.DatabaseError, ValueError) as error:
        sys.exit("[XX] Legacy instance staging failed: " + str(error))
