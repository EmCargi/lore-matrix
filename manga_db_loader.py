#!/usr/bin/env python3
"""manga_db_loader.py — Persist confirmed NarrativeLog chunks into a per-series
SQLite DB (Chronos disc pattern) + dual-commit a `manga_vault` Chroma collection.

Per-series DB layout (the "disc"): manga-data/<series_id>/data/<series_id>.db
Schema (counter-plan-approved):
  narrative   — PK (series_id, page, entry_index); entry_id = page*1000 + entry_index (derived)
  series_meta — series label + provenance (artist, counts, last_ingested)
Dual-commit: rows also upsert into a `manga_vault` Chroma collection using
nomic-embed-text via Ollama (workspace fallback chain footprint). Chroma commit
is best-effort — a vector failure never aborts the SQLite write.

Run:
    venv/bin/python manga_db_loader.py --series mingyun-comic \
        --display-name "Mingyun Comic" --artist "Mingyun"
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

# Path agnosticism bootstrap
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import MANGA_DATA_DIR, OUTPUT_CHUNKS_DIR  # noqa: E402
from core.utils import NarrativeLog  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS narrative (
    series_id         TEXT NOT NULL,
    page              INTEGER NOT NULL,
    entry_index       INTEGER NOT NULL,
    entry_id          INTEGER NOT NULL,
    speaker           TEXT NOT NULL,
    dialogue          TEXT NOT NULL DEFAULT '',
    scene_description TEXT NOT NULL DEFAULT '',
    source_file       TEXT NOT NULL,
    ingested_at       TEXT NOT NULL,
    PRIMARY KEY (series_id, page, entry_index)
);
CREATE TABLE IF NOT EXISTS series_meta (
    series_id     TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    artist        TEXT NOT NULL DEFAULT '',
    page_count    INTEGER NOT NULL DEFAULT 0,
    entry_count   INTEGER NOT NULL DEFAULT 0,
    last_ingested TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
    series_id         TEXT NOT NULL,
    page              INTEGER NOT NULL,
    entry_index       INTEGER NOT NULL,
    speaker           TEXT,
    dialogue          TEXT,
    scene_description TEXT,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    updated_at        TEXT NOT NULL,
    PRIMARY KEY (series_id, page, entry_index)
);
"""


def page_from_stem(stem: str, fallback_index: int) -> int:
    """Extract the page integer from a chunk filename stem (`01` -> 1)."""
    m = re.search(r"(\d+)", stem)
    return int(m.group(1)) if m else fallback_index


def resolve_db_path(series_id: str) -> Path:
    db_dir = MANGA_DATA_DIR / series_id / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / f"{series_id}.db"


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def chroma_id(series_id: str, page: int, entry_index: int) -> str:
    """Canonical Chroma vector id — the single construction point so ingest,
    re-embed, and delete can never drift."""
    return f"{series_id}-p{page}-e{entry_index}"


def _open_chroma():
    """Open the manga_vault collection (nomic-embed-text via Ollama)."""
    import os

    from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

    from src.storage.vector_vault import get_collection

    ef = OllamaEmbeddingFunction(
        url=os.environ.get("OLLAMA_PRIMARY_URL", "http://100.73.250.56:11434"),
        model_name="nomic-embed-text",
    )
    return get_collection(name="manga_vault", embedding_function=ef)


def apply_corrections(series_id: str, db_path: Path | None = None, embed: bool = True) -> dict:
    """Apply the durable `corrections` table over `narrative` and re-sync Chroma.

    NULL override columns are left untouched; `is_deleted=1` tombstones the row
    (DELETE from narrative + `collection.delete`). SQLite commits first; the
    vector sync is best-effort with a loud audit notice on failure. Auto-run by
    the loader after every upsert; standalone via manga_db_edit.py `apply`.
    Returns {"updated", "deleted"}.
    """
    db_path = db_path or resolve_db_path(series_id)
    now = datetime.now(UTC).isoformat()
    if not db_path.exists():
        return {"updated": 0, "deleted": 0}

    upsert_docs, upsert_metas, upsert_ids = [], [], []
    delete_ids = []
    updated = deleted = 0

    with sqlite3.connect(db_path) as conn:
        _init_db(conn)
        corrections = conn.execute(
            "SELECT page, entry_index, speaker, dialogue, scene_description, is_deleted "
            "FROM corrections WHERE series_id = ? ORDER BY page, entry_index",
            (series_id,),
        ).fetchall()
        if not corrections:
            return {"updated": 0, "deleted": 0}

        for page, entry_index, speaker, dialogue, scene, is_deleted in corrections:
            key = (series_id, page, entry_index)
            if is_deleted:
                conn.execute(
                    "DELETE FROM narrative WHERE series_id=? AND page=? AND entry_index=?",
                    key,
                )
                delete_ids.append(chroma_id(series_id, page, entry_index))
                deleted += 1
            else:
                conn.execute(
                    "UPDATE narrative SET speaker=COALESCE(?, speaker), "
                    "dialogue=COALESCE(?, dialogue), "
                    "scene_description=COALESCE(?, scene_description) "
                    "WHERE series_id=? AND page=? AND entry_index=?",
                    (speaker, dialogue, scene, *key),
                )
                row = conn.execute(
                    "SELECT speaker, dialogue, scene_description, source_file FROM narrative "
                    "WHERE series_id=? AND page=? AND entry_index=?",
                    key,
                ).fetchone()
                if row:
                    dialogue_txt = row[1] or ""
                    upsert_docs.append(dialogue_txt if dialogue_txt else (row[2] or ""))
                    upsert_metas.append({
                        "series_id": series_id,
                        "page": page,
                        "speaker": row[0],
                        "source_file": row[3],
                    })
                    upsert_ids.append(chroma_id(series_id, page, entry_index))
                    updated += 1

        if updated or deleted:
            conn.execute(
                "UPDATE series_meta SET last_ingested=? WHERE series_id=?",
                (now, series_id),
            )

    if updated or deleted:
        print(f"  ✏️ Corrections applied: {updated} updated, {deleted} tombstoned.")
        if embed:
            try:
                collection = _open_chroma()
                if upsert_ids:
                    collection.upsert(
                        documents=upsert_docs, metadatas=upsert_metas, ids=upsert_ids,
                    )
                    print(f"  ✅ ChromaDB: re-embedded {len(upsert_ids)} corrected vectors")
                if delete_ids:
                    collection.delete(ids=delete_ids)
                    print(f"  ✅ ChromaDB: deleted {len(delete_ids)} tombstoned vectors")
            except Exception as e:  # noqa: BLE001 - vector sync is best-effort
                print(f"  ⚠️  ChromaDB correction sync failed (SQLite apply stands): {e}")

    return {"updated": updated, "deleted": deleted}


def _iter_chunks(series_id: str, input_dir: Path | None):
    """Yield (page, path) for every vision_chunk_*.json, sorted by page."""
    scan_dir = input_dir or (OUTPUT_CHUNKS_DIR / series_id)
    if not scan_dir.is_dir():
        return []
    files = sorted(scan_dir.glob("vision_chunk_*.json"))
    fallback = 0
    out = []
    for p in files:
        page = page_from_stem(p.stem, fallback)
        fallback += 1
        out.append((page, p))
    out.sort(key=lambda t: t[0])
    return out


def load_series(series_id: str, display_name: str, artist: str = "",
                input_dir: Path | None = None, embed: bool = True) -> dict:
    """Validate every chunk, upsert narrative rows, refresh series_meta, and
    best-effort dual-commit to the manga_vault Chroma collection."""
    now = datetime.now(UTC).isoformat()
    chunks = _iter_chunks(series_id, input_dir)
    if not chunks:
        print(f"📭 No vision_chunk_*.json found for `{series_id}`. Nothing loaded.")
        return {"pages": 0, "entries": 0}

    db_path = resolve_db_path(series_id)
    narrative_rows = []
    chroma_docs = []
    chroma_metas = []
    chroma_ids = []
    total_entries = 0

    print(f"🎬 Loading `{series_id}` ({len(chunks)} pages) into {db_path}")

    for page, chunk_path in chunks:
        try:
            raw = chunk_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            validated = NarrativeLog.model_validate_json(json.dumps(payload))
        except Exception as e:  # noqa: BLE001 - a corrupt chunk must not kill the load
            print(f"  ❌ Skipping {chunk_path.name}: {e}")
            continue

        entries = validated.entries
        for idx, entry in enumerate(entries):
            entry_id = page * 1000 + idx
            dialogue = entry.Dialogue or ""
            narrative_rows.append((
                series_id, page, idx, entry_id,
                entry.Speaker, dialogue, entry.Scene_Description,
                chunk_path.name, now,
            ))
            if embed:
                chroma_docs.append(dialogue if dialogue else entry.Scene_Description)
                chroma_metas.append({
                    "series_id": series_id,
                    "page": page,
                    "speaker": entry.Speaker,
                    "source_file": chunk_path.name,
                })
                chroma_ids.append(chroma_id(series_id, page, idx))
        total_entries += len(entries)
        print(f"  ✅ {chunk_path.name}: {len(entries)} entries (page {page})")

    if not narrative_rows:
        print("  ⚠️ No valid entries recovered — nothing written.")
        return {"pages": 0, "entries": 0}

    # 1. SQLite — single transactional batch (idempotent upsert)
    with sqlite3.connect(db_path) as conn:
        _init_db(conn)
        conn.executemany(
            """INSERT OR REPLACE INTO narrative
               (series_id, page, entry_index, entry_id, speaker, dialogue,
                scene_description, source_file, ingested_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            narrative_rows,
        )
        conn.execute(
            """INSERT OR REPLACE INTO series_meta
               (series_id, display_name, artist, page_count, entry_count, last_ingested)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (series_id, display_name, artist, len(chunks), total_entries, now),
        )
    print(f"  ✅ SQLite: upserted {len(narrative_rows)} rows → narrative, "
          f"{len(chunks)} pages → series_meta")

    # 2. ChromaDB — best-effort dual-commit (never blocks the SQLite write)
    if embed:
        try:
            collection = _open_chroma()
            collection.upsert(
                documents=chroma_docs, metadatas=chroma_metas, ids=chroma_ids,
            )
            print(f"  ✅ ChromaDB: upserted {len(chroma_ids)} vectors → manga_vault")
        except Exception as e:  # noqa: BLE001 - vector failure is non-fatal
            print(f"  ⚠️  ChromaDB dual-commit failed (SQLite write stands): {e}")

    # 3. Corrections replay — durable human fixes always win over fresh data.
    apply_corrections(series_id, db_path, embed=embed)

    return {"pages": len(chunks), "entries": total_entries}


def main():
    parser = argparse.ArgumentParser(description="Load NarrativeLog manga chunks into a per-series SQLite DB + Chroma vault")
    parser.add_argument("--series", required=True, help="Series id (slug). e.g. mingyun-comic")
    parser.add_argument("--display-name", default=None, help="Human display name (default: the series id)")
    parser.add_argument("--artist", default="", help="Mangaka/artist provenance for series_meta (optional)")
    parser.add_argument("--input", type=Path, default=None, help="Override chunk dir (default: output/json_staging/<series_id>)")
    parser.add_argument("--no-embed", action="store_true", help="Skip the ChromaDB dual-commit")
    args = parser.parse_args()

    result = load_series(
        args.series,
        args.display_name or args.series,
        artist=args.artist,
        input_dir=args.input,
        embed=not args.no_embed,
    )
    print(f"\n🎉 Load complete: {result['pages']} pages, {result['entries']} entries.")


if __name__ == "__main__":
    main()