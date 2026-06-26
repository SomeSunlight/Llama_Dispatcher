#!/usr/bin/env python
"""
migrate_machines.py  –  Migration zur instanz-basierten Verzeichnisstruktur

Erstellt instances/Laptop/ und instances/Speedy/ mit:
  - instance.yaml     (UUID + Nickname, wird von dispatcher.py gelesen)
  - profiles/         (Thinkpad_* → Laptop,  3090_* → Speedy)
  - ensembles/        (thinkpad.yaml → Laptop,  3090.yaml → Speedy)
  - engines/          (maschinenspezifische bin_dir-Konfigurationen)
  - data/metrics.db   (aus data/metrics_v4.db, mit machine_id-Spalte)

Originaldateien werden NICHT gelöscht. Nach Prüfung bitte manuell aufräumen
oder per Git zurückrollen.

Verwendung:
  # Trockenlauf – zeigt, was geschehen würde:
  python migrate_machines.py --current-instance Laptop --dry-run

  # Migration: aktuelle DB geht an Laptop (Thinkpad)
  python migrate_machines.py --current-instance Laptop

  # Migration: aktuelle DB geht an Speedy (3090)
  python migrate_machines.py --current-instance Speedy

Konkreter Vorschlag:
  # Auf dem Thinkpad (du bist dort, die DB gehört dort hin):
  python migrate_machines.py --current-instance Laptop

  # Auf dem Speedy-Rechner später:
  python migrate_machines.py --current-instance Speedy

  # Danach Dispatcher mit Instanz starten:
  uv run src/dispatcher.py serve --ensemble thinkpad --instance Laptop
"""


import argparse
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent

# ── Maschinendefinitionen ──────────────────────────────────────────────────────
# Erweiterbar: weitere Instanzen hier eintragen.
INSTANCES: dict[str, dict[str, Any]] = {
    "Laptop": {
        "profile_prefixes": ["Thinkpad_"],
        "ensemble_names":   ["thinkpad"],
        # Engine-Konfigurationen: name → bin_dir
        # Passe diese Pfade an, wenn sich die llama.cpp-Installation ändert.
        "engines": {
            "vulkan": r"c:\llama.cpp\server\server_06_vulcan",  # Vulkan-Build (RTX 500 + iGPU)
            "sycl":   r"c:\llama.cpp\server\server_07_SYCL",   # SYCL/Intel-Build
        },
    },
    "Speedy": {
        "profile_prefixes": ["3090_"],
        "ensemble_names":   ["3090"],
        # Engine-Konfigurationen
        "engines": {
            "cuda": r"c:\llama-cpp\server\server_05",  # CUDA-Build (RTX 3090)
        },
    },
}

SRC_PROFILES_DIR  = PROJECT_ROOT / "profiles"
SRC_ENSEMBLES_DIR = PROJECT_ROOT / "ensembles"
SRC_DB_PATH       = PROJECT_ROOT / "data" / "metrics_v4.db"
INIT_SQL_PATH     = PROJECT_ROOT / "src" / "init_db.sql"
INSTANCES_DIR     = PROJECT_ROOT / "instances"


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _load_or_create_instance_yaml(instance_dir: Path, nickname: str, dry_run: bool) -> str:
    """
    Liest machine_guid aus bestehender instance.yaml oder generiert neue UUID4.
    Idempotent: wird das Skript zweimal ausgeführt, bleibt die UUID stabil.
    """
    config_file = instance_dir / "instance.yaml"
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        guid = data.get("machine_guid") or str(uuid.uuid4())
        print(f"  [OK]     instance.yaml existiert → GUID={guid}")
        return guid

    guid = str(uuid.uuid4())
    config = {"nickname": nickname, "machine_guid": guid}
    print(f"  [CREATE] instance.yaml  nickname={nickname}  machine_guid={guid}")
    if not dry_run:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return guid


def _create_subdirs(instance_dir: Path, dry_run: bool):
    for sub in ("data", "profiles", "ensembles", "engines"):
        d = instance_dir / sub
        if d.exists():
            print(f"  [OK]     {d.relative_to(PROJECT_ROOT)}/ existiert")
        else:
            print(f"  [CREATE] {d.relative_to(PROJECT_ROOT)}/")
            if not dry_run:
                d.mkdir(parents=True, exist_ok=True)


def _create_engines(instance_dir: Path, engines: dict[str, str], dry_run: bool):
    """
    Erstellt Engine-YAML-Dateien in instances/<name>/engines/.
    Format: { bin_dir: "<pfad>" }  – maschinenspezifisch, nie ins Haupt-Repo.
    """
    engines_dir = instance_dir / "engines"
    for engine_name, bin_dir in engines.items():
        dest = engines_dir / f"{engine_name}.yaml"
        if dest.exists():
            print(f"  [SKIP]   engines/{engine_name}.yaml (existiert bereits)")
        else:
            print(f"  [CREATE] engines/{engine_name}.yaml  bin_dir={bin_dir}")
            if not dry_run:
                engines_dir.mkdir(parents=True, exist_ok=True)
                content = (
                    f"# engines/{engine_name}.yaml\n"
                    f"# Maschinenspezifisch – passe bin_dir nach jedem llama.cpp-Update an.\n"
                    f"# Zum Konzept siehe defaults/engine-templates/README.md\n"
                    f"bin_dir: \"{bin_dir}\"\n"
                )
                dest.write_text(content, encoding="utf-8")


def _copy_profiles(instance_dir: Path, prefixes: list[str], dry_run: bool) -> list[str]:
    """
    Kopiert Profile mit passendem Namenspräfix in die Instanz.
    Gibt Liste der Profile zurück, die zu KEINER Instanz passen.
    """
    dest = instance_dir / "profiles"
    copied = 0
    for src in sorted(SRC_PROFILES_DIR.glob("*.yaml")):
        if not any(src.name.startswith(p) for p in prefixes):
            continue
        target = dest / src.name
        if target.exists():
            print(f"  [SKIP]   profiles/{src.name} (existiert bereits)")
        else:
            print(f"  [COPY]   profiles/{src.name}")
            if not dry_run:
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        copied += 1
    print(f"           → {copied} Profile {'würden kopiert' if dry_run else 'kopiert'}")

    # Alle Profile die zu keiner Instanz passen
    all_prefixes = [p for inst in INSTANCES.values() for p in inst["profile_prefixes"]]
    return [
        src.name
        for src in SRC_PROFILES_DIR.glob("*.yaml")
        if not any(src.name.startswith(p) for p in all_prefixes)
    ]


def _copy_ensembles(instance_dir: Path, ensemble_names: list[str], dry_run: bool):
    dest = instance_dir / "ensembles"
    copied = 0
    for name in ensemble_names:
        src = SRC_ENSEMBLES_DIR / f"{name}.yaml"
        if not src.exists():
            print(f"  [WARN]   ensembles/{name}.yaml nicht gefunden – übersprungen")
            continue
        target = dest / src.name
        if target.exists():
            print(f"  [SKIP]   ensembles/{src.name} (existiert bereits)")
        else:
            print(f"  [COPY]   ensembles/{src.name}")
            if not dry_run:
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        copied += 1
    print(f"           → {copied} Ensembles {'würden kopiert' if dry_run else 'kopiert'}")


def _migrate_db(instance_dir: Path, machine_guid: str, is_current: bool, dry_run: bool):
    """
    Kopiert die bestehende DB in die Instanz, fügt machine_id-Spalte hinzu
    und setzt sie auf die UUID der Instanz.
    Für die 'nicht-aktuelle' Instanz wird eine leere DB mit korrektem Schema erstellt.
    """
    dest_db = instance_dir / "data" / "metrics.db"

    if dest_db.exists():
        print(f"  [SKIP]   {dest_db.relative_to(PROJECT_ROOT)} existiert bereits")
        return

    if is_current and SRC_DB_PATH.exists():
        print(f"  [COPY]   {SRC_DB_PATH.relative_to(PROJECT_ROOT)}")
        print(f"       →   {dest_db.relative_to(PROJECT_ROOT)}")
        if not dry_run:
            dest_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SRC_DB_PATH, dest_db)
    else:
        if is_current:
            print(f"  [WARN]   Quelldatenbank {SRC_DB_PATH} nicht gefunden – leere DB wird erstellt")
        else:
            print(f"  [CREATE] Leeres Schema: {dest_db.relative_to(PROJECT_ROOT)}")
        if not dry_run:
            dest_db.parent.mkdir(parents=True, exist_ok=True)
            if INIT_SQL_PATH.exists():
                conn = sqlite3.connect(str(dest_db))
                with open(INIT_SQL_PATH, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
                # machine_id Spalte sicherstellen
                cols = [row[1] for row in conn.execute("PRAGMA table_info(execution_runs)")]
                if "machine_id" not in cols:
                    conn.execute(
                        "ALTER TABLE execution_runs ADD COLUMN machine_id TEXT NOT NULL DEFAULT 'unknown'"
                    )
                conn.close()
        return

    if dry_run:
        print(f"  [DRY]    machine_id-Spalte würde gesetzt auf {machine_guid[:8]}...")
        return

    # machine_id Spalte hinzufügen (falls DB noch v4-Schema hat)
    conn = sqlite3.connect(str(dest_db))
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(execution_runs)")]
        if "machine_id" not in cols:
            conn.execute(
                "ALTER TABLE execution_runs ADD COLUMN machine_id TEXT NOT NULL DEFAULT 'unknown'"
            )
            print(f"  [ALTER]  machine_id-Spalte zu execution_runs hinzugefügt")
        else:
            print(f"  [OK]     machine_id-Spalte bereits vorhanden")

        # Bestehende Zeilen mit der Instanz-GUID versehen
        cur = conn.execute(
            "UPDATE execution_runs SET machine_id = ? WHERE machine_id = 'unknown'",
            (machine_guid,),
        )
        print(f"  [UPDATE] {cur.rowcount} Zeilen in execution_runs mit machine_id={machine_guid[:8]}... versehen")
        conn.commit()
    finally:
        conn.close()


def _update_gitignore(dry_run: bool):
    """Fügt instances/ zum .gitignore hinzu, falls noch nicht vorhanden."""
    gitignore = PROJECT_ROOT / ".gitignore"
    marker = "# --- Instance data (machine-specific, managed as separate private repo) ---"
    entry  = "instances/"

    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if entry in content:
            print(f"  [OK]     .gitignore enthält bereits '{entry}'")
            return
        addition = f"\n{marker}\n{entry}\n"
        print(f"  [APPEND] .gitignore ← {entry}")
        if not dry_run:
            gitignore.write_text(content + addition, encoding="utf-8")
    else:
        print(f"  [CREATE] .gitignore mit {entry}")
        if not dry_run:
            gitignore.write_text(f"{marker}\n{entry}\n", encoding="utf-8")


# ── Haupt-Migrationsfunktion ───────────────────────────────────────────────────

def migrate(current_instance: str, dry_run: bool) -> None:
    sep = "=" * 60
    mode = "DRY-RUN (keine Änderungen)" if dry_run else "SCHREIBEN"
    print(f"{sep}")
    print(f"  Instanz-Migration  |  Modus: {mode}")
    print(f"  Aktuelle DB-Instanz: {current_instance}")
    print(f"{sep}")

    all_unknown: list[str] = []

    for nickname, spec in INSTANCES.items():
        is_current = (nickname == current_instance)
        instance_dir = INSTANCES_DIR / nickname
        tag = " ← aktuelle DB" if is_current else " (neue, leere DB)"

        print(f"\n{'─'*60}")
        print(f"  Instanz: {nickname}{tag}")
        print(f"{'─'*60}")

        print("\n  Verzeichnisse:")
        _create_subdirs(instance_dir, dry_run)

        print("\n  instance.yaml:")
        machine_guid = _load_or_create_instance_yaml(instance_dir, nickname, dry_run)

        print(f"\n  Profile  (Präfixe: {spec['profile_prefixes']}):")
        unknown = _copy_profiles(instance_dir, spec["profile_prefixes"], dry_run)
        all_unknown.extend(unknown)

        print("\n  Ensembles:")
        _copy_ensembles(instance_dir, spec["ensemble_names"], dry_run)

        print("\n  Engines:")
        _create_engines(instance_dir, spec.get("engines", {}), dry_run)

        print("\n  Datenbank:")
        _migrate_db(instance_dir, machine_guid, is_current, dry_run)

    print(f"\n{'─'*60}")
    print("  .gitignore:")
    _update_gitignore(dry_run)

    # Abschlussbericht
    print(f"\n{sep}")
    print("Migration abgeschlossen." if not dry_run else "Dry-Run abgeschlossen – nichts wurde geändert.")

    # Deduplizierte unbekannte Profile
    seen: set[str] = set()
    unique_unknown = [x for x in all_unknown if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]
    if unique_unknown:
        print(f"\n[HINWEIS] Folgende Profile passen zu keiner Instanz und wurden NICHT kopiert:")
        for name in unique_unknown:
            print(f"  - {name}")
        print("  → Manuell in instances/<name>/profiles/ kopieren falls benötigt.")

    print(f"\nNächste Schritte:")
    print(f"  1. Dispatcher mit Instanz starten:")
    print(f"       uv run src/dispatcher.py serve --ensemble <name> --instance {current_instance}")
    print(f"  2. Instanz als eigenes privates Git-Repo sichern (optional):")
    print(f"       cd instances/{current_instance}")
    print(f"       git init && git add . && git commit -m 'Initial instance setup'")
    print(f"       git remote add origin <private-github-url> && git push -u origin main")
    print(f"  3. Originaldateien aufräumen, sobald alles geprüft ist:")
    print(f"       profiles/Thinkpad_*.yaml  profiles/3090_*.yaml")
    print(f"       ensembles/thinkpad.yaml   ensembles/3090.yaml")
    print(f"       data/metrics_v4.db")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Instanz-Migration: sortiert Profile/Ensembles/DB in instances/-Unterordner.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  python migrate_machines.py --current-instance Laptop --dry-run\n"
            "  python migrate_machines.py --current-instance Laptop\n"
            "  python migrate_machines.py --current-instance Speedy\n"
        ),
    )
    parser.add_argument(
        "--current-instance",
        choices=list(INSTANCES.keys()),
        required=True,
        help="Welche Instanz bekommt die aktuelle data/metrics_v4.db zugewiesen?",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen was geschehen würde – nichts schreiben.",
    )
    args = parser.parse_args()
    migrate(args.current_instance, args.dry_run)


if __name__ == "__main__":
    main()


