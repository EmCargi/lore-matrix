import json
import os
import sqlite3
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import manga_db_edit
import manga_db_loader


def _seed_series(tmp_path, monkeypatch, series="s"):
    """Build a tiny series with page 1 (2 entries) and page 2 (1 entry), loaded into a tmp DB."""
    monkeypatch.setattr(manga_db_loader, "MANGA_DATA_DIR", tmp_path)
    chunks = tmp_path / "s"
    chunks.mkdir(parents=True, exist_ok=True)
    (chunks / "vision_chunk_01.json").write_text(json.dumps({"entries": [
        {"Speaker": "A", "Dialogue": "hello world", "Scene Description": "c1"},
        {"Speaker": "B", "Dialogue": "goodbye", "Scene Description": "c2"},
    ]}), encoding="utf-8")
    (chunks / "vision_chunk_02.json").write_text(json.dumps({"entries": [
        {"Speaker": "C", "Dialogue": "hi", "Scene Description": "c3"},
    ]}), encoding="utf-8")
    manga_db_loader.load_series("s", "S", input_dir=chunks, embed=False)
    return tmp_path / "s" / "data" / "s.db"


def _dialogue(conn, page, entry):
    return conn.execute(
        "SELECT speaker, dialogue, scene_description FROM narrative WHERE series_id='s' AND page=? AND entry_index=?",
        (page, entry),
    ).fetchone()


class TestEditApply:
    def test_edit_updates_only_override_fields(self, tmp_path, monkeypatch):
        db = _seed_series(tmp_path, monkeypatch)
        manga_db_edit.cmd_edit(type("A", (), {"series": "s", "page": 1, "entry": 0, "speaker": None, "dialogue": "fixed", "scene": None})())
        result = manga_db_loader.apply_corrections("s", db, embed=False)
        assert result == {"updated": 1, "deleted": 0}
        with sqlite3.connect(db) as conn:
            sp, dlg, sc = _dialogue(conn, 1, 0)
        assert dlg == "fixed"          # override applied
        assert sp == "A"               # untouched (NULL override)
        assert sc == "c1"              # untouched (NULL override)

    def test_corrections_survive_reload(self, tmp_path, monkeypatch):
        db = _seed_series(tmp_path, monkeypatch)
        manga_db_edit.cmd_edit(type("A", (), {"series": "s", "page": 2, "entry": 0, "speaker": None, "dialogue": "kept", "scene": None})())
        manga_db_loader.apply_corrections("s", db, embed=False)

        # re-load the canonical chunks — the correction must still win
        chunks = tmp_path / "s"
        manga_db_loader.load_series("s", "S", input_dir=chunks, embed=False)
        with sqlite3.connect(db) as conn:
            sp, dlg, sc = _dialogue(conn, 2, 0)
        assert dlg == "kept"

    def test_delete_tombstones_row(self, tmp_path, monkeypatch):
        db = _seed_series(tmp_path, monkeypatch)
        manga_db_edit.cmd_delete(type("A", (), {"series": "s", "page": 1, "entry": 1})())
        result = manga_db_loader.apply_corrections("s", db, embed=False)
        assert result == {"updated": 0, "deleted": 1}
        with sqlite3.connect(db) as conn:
            rows = conn.execute("SELECT * FROM narrative WHERE series_id='s' AND page=1").fetchall()
        assert len(rows) == 1  # entry 0 remains, entry 1 gone

    def test_edit_clears_pending_tombstone(self, tmp_path, monkeypatch):
        db = _seed_series(tmp_path, monkeypatch)
        # record a tombstone but DON'T apply — the narrative row still exists
        manga_db_edit.cmd_delete(type("A", (), {"series": "s", "page": 1, "entry": 1})())
        # re-enable by editing the same key — INSERT OR REPLACE resets is_deleted to 0
        manga_db_edit.cmd_edit(type("A", (), {"series": "s", "page": 1, "entry": 1, "speaker": None, "dialogue": "back", "scene": None})())
        result = manga_db_loader.apply_corrections("s", db, embed=False)
        assert result == {"updated": 1, "deleted": 0}
        with sqlite3.connect(db) as conn:
            sp, dlg, sc = _dialogue(conn, 1, 1)
        assert dlg == "back"

    def test_orphan_override_refused(self, tmp_path, monkeypatch):
        db = _seed_series(tmp_path, monkeypatch)
        rc = manga_db_edit.cmd_edit(type("A", (), {"series": "s", "page": 9, "entry": 9, "speaker": None, "dialogue": "x", "scene": None})())
        assert rc == 1  # refused — no narrative row at P.9 E.9
        with sqlite3.connect(db) as conn:
            count = conn.execute("SELECT count(*) FROM corrections").fetchone()[0]
        assert count == 0


class TestChromaIngestIds:
    def test_chroma_id_contract(self):
        # the canonical id format — must never drift (loader + edit share it)
        assert manga_db_loader.chroma_id("mingyun-comic", 7, 0) == "mingyun-comic-p7-e0"