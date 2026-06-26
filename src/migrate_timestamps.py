"""
migrate_timestamps.py - Migration der Timestamp-Spalten in metrics_v4.db

Konvertiert alle gespeicherten Timestamps in Lokalzeit mit UTC-Offset,
z. B. '2026-06-13 01:46:56+02:00'.

Das Skript behandelt alle drei Eingabeformate:
  - Ohne Offset:    '2026-06-12 23:46:56'        -> als UTC interpretiert
  - UTC +00:00:     '2026-06-12 23:46:56+00:00'  -> in Zielzeit umgerechnet
  - Anderer Offset: '2026-06-12 23:46:56+01:00'  -> in Zielzeit umgerechnet

Das Skript ist idempotent: Eintraege, die bereits den Ziel-Offset tragen,
werden uebersprungen.

Verwendung:
    # Automatisch: Ziel-Offset = Zeitzone des aktuellen Systems
    python src/migrate_timestamps.py

    # Explizit: Ziel-Offset angeben (z. B. fuer CEST auf einem UTC-Server)
    python src/migrate_timestamps.py --target-offset +02:00

    # Andere DB-Datei, erst Vorschau, dann schreiben
    python src/migrate_timestamps.py --db data/metrics_v4.db --target-offset +02:00 --dry-run
    python src/migrate_timestamps.py --db data/metrics_v4.db --target-offset +02:00
"""

import argparse
import datetime
import re
import sqlite3
from pathlib import Path

TIMESTAMP_COLUMNS: dict[str, list[str]] = {
    "execution_runs": ["timestamp"],
    "serve_model_instances": ["loaded_at", "unloaded_at"],
    "metrics_serve": ["timestamp"],
    "metrics_lifecycle": ["timestamp"],
}

_WITH_OFFSET = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})([+-]\d{2}:\d{2})$")
_NO_OFFSET   = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})$")


def _system_offset_str() -> str:
    """Gibt den UTC-Offset des laufenden Systems als '+HH:MM' zurueck."""
    s = datetime.datetime.now().astimezone().strftime("%z")  # '+0200'
    return s[:3] + ":" + s[3:]                               # '+02:00'


def _parse_offset(offset: str) -> datetime.timedelta:
    """Parst '+HH:MM' oder '-HH:MM' in ein timedelta."""
    sign = 1 if offset[0] == "+" else -1
    h, m = int(offset[1:3]), int(offset[4:6])
    return datetime.timedelta(hours=h, minutes=m) * sign


def _validate_offset(offset: str) -> str:
    """Validiert und normalisiert einen Offset-String. Wirft ValueError bei ungueltigem Format."""
    m = re.match(r"^([+-])(\d{1,2}):(\d{2})$", offset.strip())
    if not m:
        raise ValueError(
            f"Ungueltiges Offset-Format: {offset!r}. Erwartet z. B. '+02:00' oder '-05:00'."
        )
    sign, h, mi = m.group(1), int(m.group(2)), int(m.group(3))
    if h > 14 or mi > 59:
        raise ValueError(f"Offset ausserhalb des gueltigen Bereichs: {offset!r}")
    return f"{sign}{h:02d}:{mi:02d}"


def _convert(value: str, target_offset: str) -> str | None:
    """
    Konvertiert einen Timestamp-String in Lokalzeit mit target_offset.
    Gibt None zurueck wenn keine Konvertierung noetig ist (bereits korrekt).
    """
    m = _WITH_OFFSET.match(value.strip())
    if m:
        dt_str, src_offset = m.group(1), m.group(2)
        if src_offset == target_offset:
            return None  # bereits korrekt, ueberspringen
        # Quellzeit -> UTC -> Zielzeit
        dt_utc = datetime.datetime.fromisoformat(dt_str) - _parse_offset(src_offset)
        dt_local = dt_utc + _parse_offset(target_offset)
        return dt_local.strftime("%Y-%m-%d %H:%M:%S") + target_offset

    m2 = _NO_OFFSET.match(value.strip())
    if m2:
        # Kein Offset: als UTC behandeln -> Zielzeit
        dt_utc = datetime.datetime.fromisoformat(m2.group(1))
        dt_local = dt_utc + _parse_offset(target_offset)
        return dt_local.strftime("%Y-%m-%d %H:%M:%S") + target_offset

    return None  # unbekanntes Format, ueberspringen


def migrate(db_path: Path, target_offset: str, dry_run: bool = False) -> None:
    if not db_path.exists():
        print(f"[FEHLER] Datenbank nicht gefunden: {db_path}")
        return

    print(f"Ziel-Offset: {target_offset}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    total_updated = 0

    try:
        for table, columns in TIMESTAMP_COLUMNS.items():
            pk_info = conn.execute(f"PRAGMA table_info({table})").fetchall()
            pk_cols = [row["name"] for row in pk_info if row["pk"] > 0]
            if not pk_cols:
                print(f"  [WARNUNG] Kein PK in '{table}', uebersprungen.")
                continue
            pk = pk_cols[0]
            col_names = [row["name"] for row in pk_info]

            for col in columns:
                if col not in col_names:
                    continue

                rows = conn.execute(
                    f"SELECT {pk}, {col} FROM {table} WHERE {col} IS NOT NULL"
                ).fetchall()

                to_update = []
                for row in rows:
                    new_val = _convert(row[col], target_offset)
                    if new_val is not None:
                        to_update.append((new_val, row[pk]))

                if not to_update:
                    print(f"  {table}.{col}: alle Eintraege bereits korrekt.")
                    continue

                print(f"  {table}.{col}: {len(to_update)} Eintraege -> {target_offset}")
                if dry_run:
                    for new_val, pk_val in to_update[:3]:
                        orig = next(r[col] for r in rows if r[pk] == pk_val)
                        print(f"    {orig!r}  ->  {new_val!r}")
                    if len(to_update) > 3:
                        print(f"    ... und {len(to_update) - 3} weitere")
                else:
                    conn.executemany(
                        f"UPDATE {table} SET {col} = ? WHERE {pk} = ?",
                        to_update,
                    )
                    total_updated += len(to_update)

        if not dry_run:
            conn.commit()
            print(f"\nAbgeschlossen. {total_updated} Timestamps konvertiert.")
        else:
            print("\n[DRY-RUN] Keine Aenderungen geschrieben.")

    finally:
        conn.close()


def main() -> None:
    system_offset = _system_offset_str()

    parser = argparse.ArgumentParser(
        description="Timestamp-Migration: konvertiert alle Timestamps in der DB auf Lokalzeit mit UTC-Offset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            f"  python src/migrate_timestamps.py\n"
            f"      # automatisch, Systemzeitzone = {system_offset}\n\n"
            "  python src/migrate_timestamps.py --target-offset +02:00\n"
            "      # explizit CEST, auch wenn System UTC laeuft\n\n"
            "  python src/migrate_timestamps.py --target-offset +02:00 --dry-run\n"
            "      # erst Vorschau\n\n"
            "  python src/migrate_timestamps.py --db C:/pfad/metrics_v4.db --target-offset +02:00\n"
            "      # andere DB, z. B. auf dem 3090-Rechner\n"
        ),
    )
    parser.add_argument(
        "--db",
        default="data/metrics_v4.db",
        help="Pfad zur SQLite-Datenbank (Standard: data/metrics_v4.db)",
    )
    parser.add_argument(
        "--target-offset",
        default=None,
        metavar="OFFSET",
        help=f"Ziel-UTC-Offset, z. B. +02:00 oder -05:00. Standard: Systemzeitzone ({system_offset})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen, was geaendert wuerde - nichts schreiben.",
    )
    args = parser.parse_args()

    raw_offset = args.target_offset if args.target_offset else system_offset
    try:
        target_offset = _validate_offset(raw_offset)
    except ValueError as e:
        parser.error(str(e))
        return

    db_path = Path(args.db)
    source = "Systemzeitzone" if not args.target_offset else "explizit angegeben"
    print(f"Timestamp-Migration: {db_path}")
    print(f"Ziel-Offset: {target_offset} ({source})")
    print(f"Modus: {'DRY-RUN (keine Aenderungen)' if args.dry_run else 'SCHREIBEN'}\n")

    migrate(db_path, target_offset, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

