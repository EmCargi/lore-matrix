#!/usr/bin/env python3
"""manga_db_edit.py — Read and correct the manga narrative DB (HITL fix layer).

The narrative DB is the source of truth for everything downstream (persona-etl
cards). This CLI is the human correction point: list what EasyOCR/Stheno wrote,
record durable overrides in the `corrections` table, tombstone ghost rows, and
materialize them with `apply`. Fixes survive re-extraction because the loader
re-applies corrections after every upsert.

Commands:
    list          query narrative (+ corrections diff) with optional filters
    edit          record an override (NULL = leave the field untouched)
    delete        tombstone a row (is_deleted=1)
    apply         materialize corrections into narrative + re-sync Chroma
    corrections   show pending overrides

Run (from lore-matrix/):
    venv/bin/python manga_db_edit.py --series mingyun-comic list --grep cit4
    venv/bin/python manga_db_edit.py --series mingyun-comic edit --page 7 --entry 0 \
        --dialogue "Leave the city gate in that state..."
    venv/bin/python manga_db_edit.py --series mingyun-comic apply
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Path agnosticism bootstrap
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from manga_db_loader import _init_db, apply_corrections, resolve_db_path  # noqa: E402

_now = lambda: datetime.now(timezone.utc).isoformat()


def _conn(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _init_db(conn)  # ensure corrections table exists even on pre-corrections DBs
    return conn


def cmd_list(args) -> int:
    db = resolve_db_path(args.series)
    if not db.exists():
        print(f"❌ No DB for `{args.series}`: {db}")
        return 1

    q = """SELECT n.page, n.entry_index, n.speaker, n.dialogue, n.scene_description,
                  c.speaker AS c_speaker, c.dialogue AS c_dialogue,
                  c.scene_description AS c_scene, c.is_deleted
           FROM narrative n
           LEFT JOIN corrections c ON n.series_id = c.series_id
                 AND n.page = c.page AND n.entry_index = c.entry_index
           WHERE n.series_id = ?"""
    params: list = [args.series]
    if args.page is not None:
        q += " AND n.page = ?"; params.append(args.page)
    if args.speaker:
        q += " AND n.speaker = ? COLLATE NOCASE"; params.append(args.speaker)
    if args.grep:
        q += " AND (n.dialogue LIKE ? OR n.scene_description LIKE ? OR n.speaker LIKE ?)"
        like = f"%{args.grep}%"
        params += [like, like, like]
    q += " ORDER BY n.page, n.entry_index"

    with _conn(db) as conn:
        rows = conn.execute(q, params).fetchall()

    if not rows:
        print(f"📭 No rows found for `{args.series}`.")
        return 0

    for r in rows:
        has_corr = r["c_dialogue"] is not None or r["c_speaker"] is not None or r["c_scene"] is not None
        if r["is_deleted"]:
            marker = " [TOMBSTONED]"
        elif has_corr:
            marker = " [CORRECTED]"
        else:
            marker = ""
        print(f"[P.{r['page']:02d} E.{r['entry_index']:02d}] {r['speaker']}{marker}")
        print(f"  DIALOGUE: {r['dialogue']}")
        print(f"  SCENE:    {r['scene_description']}")
        if marker == " [CORRECTED]":
            # Diff of unapplied overrides (before `apply` the original still differs)
            if r["c_dialogue"] is not None and r["c_dialogue"] != r["dialogue"]:
                print(f"    ORIGINAL:  {r['dialogue']}")
                print(f"    OVERRIDE:  {r['c_dialogue']}")
            if r["c_speaker"] is not None and r["c_speaker"] != r["speaker"]:
                print(f"    speaker:   {r['speaker']} -> {r['c_speaker']}")
    return 0


def _require_row(conn, series_id: str, page: int, entry: int) -> bool:
    """Refuse to write corrections for keys that don't exist in narrative."""
    exists = conn.execute(
        "SELECT 1 FROM narrative WHERE series_id=? AND page=? AND entry_index=?",
        (series_id, page, entry),
    ).fetchone()
    if not exists:
        print(f"❌ No narrative row at {series_id} P.{page} E.{entry} — refusing an orphan override.")
        return False
    return True


def cmd_edit(args) -> int:
    if not (args.speaker or args.dialogue or args.scene):
        print("❌ Nothing to override — pass at least one of --speaker/--dialogue/--scene.")
        return 1
    db = resolve_db_path(args.series)
    if not db.exists():
        print(f"❌ No DB for `{args.series}`: {db}")
        return 1

    with _conn(db) as conn:
        if not _require_row(conn, args.series, args.page, args.entry):
            return 1
        conn.execute(
            """INSERT OR REPLACE INTO corrections
               (series_id, page, entry_index, speaker, dialogue, scene_description, is_deleted, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
            (args.series, args.page, args.entry, args.speaker, args.dialogue, args.scene, _now()),
        )
    print(f"✏️ Correction recorded for P.{args.page} E.{args.entry} (run `apply` to materialize).")
    return 0


def cmd_delete(args) -> int:
    db = resolve_db_path(args.series)
    if not db.exists():
        print(f"❌ No DB for `{args.series}`: {db}")
        return 1

    with _conn(db) as conn:
        if not _require_row(conn, args.series, args.page, args.entry):
            return 1
        conn.execute(
            """INSERT OR REPLACE INTO corrections
               (series_id, page, entry_index, speaker, dialogue, scene_description, is_deleted, updated_at)
               VALUES (?, ?, ?, NULL, NULL, NULL, 1, ?)""",
            (args.series, args.page, args.entry, _now()),
        )
    print(f"🗑️ Tombstone recorded for P.{args.page} E.{args.entry} (run `apply` to remove the row).")
    return 0


def cmd_apply(args) -> int:
    result = apply_corrections(args.series, embed=not args.no_embed)
    print(f"\n🎉 Apply complete: {result['updated']} updated, {result['deleted']} deleted.")
    return 0


def cmd_corrections(args) -> int:
    db = resolve_db_path(args.series)
    if not db.exists():
        print(f"❌ No DB for `{args.series}`: {db}")
        return 1

    with _conn(db) as conn:
        rows = conn.execute(
            """SELECT page, entry_index, speaker, dialogue, scene_description, is_deleted, updated_at
               FROM corrections WHERE series_id = ? ORDER BY page, entry_index""",
            (args.series,),
        ).fetchall()

    if not rows:
        print(f"📭 No corrections on file for `{args.series}`.")
        return 0

    for r in rows:
        status = "TOMBSTONED" if r["is_deleted"] else "PENDING"
        print(f"[P.{r['page']:02d} E.{r['entry_index']:02d}] {status} (updated {r['updated_at']})")
        if r["dialogue"] is not None:
            print(f"    dialogue -> {r['dialogue']}")
        if r["speaker"] is not None:
            print(f"    speaker  -> {r['speaker']}")
        if r["scene_description"] is not None:
            print(f"    scene    -> {r['scene_description']}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Read and correct the manga narrative DB (HITL fix layer)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="query narrative rows (+ corrections diff)")
    p_list.add_argument("--series", required=True)
    p_list.add_argument("--page", type=int, default=None)
    p_list.add_argument("--speaker", default=None)
    p_list.add_argument("--grep", default=None, help="LIKE filter across dialogue/scene/speaker")
    p_list.set_defaults(fn=cmd_list)

    p_edit = sub.add_parser("edit", help="record an override (NULL = leave untouched)")
    p_edit.add_argument("--series", required=True)
    p_edit.add_argument("--page", type=int, required=True)
    p_edit.add_argument("--entry", type=int, required=True)
    p_edit.add_argument("--speaker", default=None)
    p_edit.add_argument("--dialogue", default=None)
    p_edit.add_argument("--scene", default=None)
    p_edit.set_defaults(fn=cmd_edit)

    p_del = sub.add_parser("delete", help="tombstone a row (is_deleted=1)")
    p_del.add_argument("--series", required=True)
    p_del.add_argument("--page", type=int, required=True)
    p_del.add_argument("--entry", type=int, required=True)
    p_del.set_defaults(fn=cmd_delete)

    p_apply = sub.add_parser("apply", help="materialize corrections into narrative + re-sync Chroma")
    p_apply.add_argument("--series", required=True)
    p_apply.add_argument("--no-embed", action="store_true", help="skip the ChromaDB re-sync")
    p_apply.set_defaults(fn=cmd_apply)

    p_corr = sub.add_parser("corrections", help="show pending overrides")
    p_corr.add_argument("--series", required=True)
    p_corr.set_defaults(fn=cmd_corrections)

    args = parser.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()