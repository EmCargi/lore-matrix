import importlib
import json
import os
import sqlite3
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

loader = importlib.import_module("manga_db_loader")



def _write_chunk(series_dir, page, entries):
    """Write a vision_chunk_<NN>.json with the given NarrativeLog entries."""
    series_dir.mkdir(parents=True, exist_ok=True)
    path = series_dir / f"vision_chunk_{page:02d}.json"
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def _entry(speaker="S", dialogue="d", scene="c"):
    return {"Speaker": speaker, "Dialogue": dialogue, "Scene Description": scene}


def test_schema_created_and_rows_loaded(tmp_path, monkeypatch):
    """Loading a series creates the DB with narrative + series_meta tables."""
    monkeypatch.setattr(loader, "MANGA_DATA_DIR", tmp_path)
    chunks = tmp_path / "s"
    _write_chunk(chunks, 1, [_entry("A", "hi", "ctx"), _entry("B", "yo", "ctx2")])
    _write_chunk(chunks, 2, [_entry("C", "wow", "ctx3")])

    loader.load_series("s", "Series S", artist="Artist", input_dir=chunks, embed=False)

    db = tmp_path / "s" / "data" / "s.db"
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"narrative", "series_meta"} <= tables
        rows = conn.execute(
            "SELECT page, entry_index, entry_id, speaker FROM narrative ORDER BY page, entry_index"
        ).fetchall()
    assert rows == [(1, 0, 1000, "A"), (1, 1, 1001, "B"), (2, 0, 2000, "C")]


def test_entry_id_derivation_no_cross_page_shift(tmp_path, monkeypatch):
    """Re-extracting a page with more/fewer entries never shifts later pages."""
    monkeypatch.setattr(loader, "MANGA_DATA_DIR", tmp_path)
    chunks = tmp_path / "s"
    _write_chunk(chunks, 4, [_entry("X")])          # page 4: 1 entry
    _write_chunk(chunks, 5, [_entry("Y"), _entry("Z")])  # page 5: 2 entries

    loader.load_series("s", "S", input_dir=chunks, embed=False)
    db = tmp_path / "s" / "data" / "s.db"
    with sqlite3.connect(db) as conn:
        first = conn.execute(
            "SELECT entry_id, speaker FROM narrative WHERE page=5 ORDER BY entry_index"
        ).fetchall()
    assert first == [(5000, "Y"), (5001, "Z")]

    # page 4 re-extracted with 3 entries — page 5 must be untouched
    _write_chunk(chunks, 4, [_entry("A"), _entry("B"), _entry("C")])
    loader.load_series("s", "S", input_dir=chunks, embed=False)
    with sqlite3.connect(db) as conn:
        second = conn.execute(
            "SELECT entry_id, speaker FROM narrative WHERE page=5 ORDER BY entry_index"
        ).fetchall()
        page4 = conn.execute(
            "SELECT entry_id FROM narrative WHERE page=4 ORDER BY entry_index"
        ).fetchall()
    assert second == [(5000, "Y"), (5001, "Z")]
    assert page4 == [(4000,), (4001,), (4002,)]


def test_idempotent_upsert_no_duplicates(tmp_path, monkeypatch):
    """Re-running the same load upserts, never duplicates."""
    monkeypatch.setattr(loader, "MANGA_DATA_DIR", tmp_path)
    chunks = tmp_path / "s"
    _write_chunk(chunks, 1, [_entry("A")])
    loader.load_series("s", "S", input_dir=chunks, embed=False)
    loader.load_series("s", "S", input_dir=chunks, embed=False)

    with sqlite3.connect(tmp_path / "s" / "data" / "s.db") as conn:
        assert conn.execute("SELECT count(*) FROM narrative").fetchone()[0] == 1
        meta = conn.execute(
            "SELECT page_count, entry_count FROM series_meta").fetchone()
    assert meta == (1, 1)


def test_invalid_chunk_skipped_not_fatal(tmp_path, monkeypatch):
    """A corrupt/empty chunk is skipped loudly; valid pages still load."""
    monkeypatch.setattr(loader, "MANGA_DATA_DIR", tmp_path)
    chunks = tmp_path / "s"
    _write_chunk(chunks, 1, [_entry("A")])
    (chunks / "vision_chunk_02.json").write_text("{not json", encoding="utf-8")

    result = loader.load_series("s", "S", input_dir=chunks, embed=False)
    with sqlite3.connect(tmp_path / "s" / "data" / "s.db") as conn:
        count = conn.execute("SELECT count(*) FROM narrative").fetchone()[0]
    assert result["pages"] == 2
    assert count == 1  # only the valid page loaded


def test_series_isolation(tmp_path, monkeypatch):
    """Two series land in separate DB files, no cross-contamination."""
    monkeypatch.setattr(loader, "MANGA_DATA_DIR", tmp_path)
    a = tmp_path / "a"
    b = tmp_path / "b"
    _write_chunk(a, 1, [_entry("A")])
    _write_chunk(b, 1, [_entry("B")])
    loader.load_series("a", "A", input_dir=a, embed=False)
    loader.load_series("b", "B", input_dir=b, embed=False)

    assert (tmp_path / "a" / "data" / "a.db").exists()
    assert (tmp_path / "b" / "data" / "b.db").exists()
    with sqlite3.connect(tmp_path / "a" / "data" / "a.db") as conn:
        speakers = [r[0] for r in conn.execute(
            "SELECT DISTINCT speaker FROM narrative")]
    assert speakers == ["A"]


def test_no_chunks_returns_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "MANGA_DATA_DIR", tmp_path)
    result = loader.load_series("ghost", "Ghost", input_dir=tmp_path / "nope", embed=False)
    assert result == {"pages": 0, "entries": 0}
