import importlib
import os
import sqlite3
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Dynamically import module with hyphen in filename
sql_loader = importlib.import_module("sql-loader")
SQL_LOADER_PATH = os.path.join(PROJECT_ROOT, "sql-loader.py")


def _run(tmp_path, csv_text, table="t", db="x.db", **kwargs):
    """Run sql-loader.py end-to-end and return the resulting SQLite connection."""
    csv_path = tmp_path / "data.csv"
    csv_path.write_text(csv_text)
    db_path = tmp_path / db
    cmd = [sys.executable, SQL_LOADER_PATH, "--input", str(csv_path),
           "--db", str(db_path), "--table", table]
    for key, val in kwargs.items():
        cmd += [f"--{key.replace('_', '-')}", str(val)]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    assert result.returncode == 0, f"sql-loader failed:\n{result.stdout}\n{result.stderr}"
    return sqlite3.connect(str(db_path))


def test_sanitize_column():
    assert sql_loader.sanitize_column("Game Name") == "game_name"
    assert sql_loader.sanitize_column("MIX-%") == "mix_%"
    assert sql_loader.sanitize_column("a/b") == "a_b"
    assert sql_loader.sanitize_column("  Upper  ") == "upper"


def test_sanitize_columns_deduplicates():
    cols = sql_loader.sanitize_columns(["A B", "a-b", "a/b", "aB"])
    assert len(cols) == len(set(cols))


def test_build_upsert():
    sql = sql_loader.build_upsert("t", ["id", "val"], "id")
    assert sql.startswith('INSERT INTO "t" ("id", "val") VALUES (?, ?)')
    assert 'ON CONFLICT("id") DO UPDATE SET "val" = excluded."val"' in sql


def test_default_fails_on_existing(tmp_path):
    conn = _run(tmp_path, "id\n1\n")
    conn.close()
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id\n2\n")
    db_path = tmp_path / "x.db"
    result = subprocess.run(
        [sys.executable, SQL_LOADER_PATH, "--input", str(csv_path),
         "--db", str(db_path), "--table", "t"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    assert result.returncode == 1
    rows = sqlite3.connect(str(db_path)).execute("select count(*) from t").fetchone()[0]
    assert rows == 1


def test_keyed_upsert_is_idempotent(tmp_path):
    conn = _run(tmp_path, "id,val\n1,one\n2,two\n", key="id")
    assert conn.execute("select count(*) from t").fetchone()[0] == 2
    conn.close()

    conn = _run(tmp_path, "id,val\n1,ONE\n3,three\n", key="id")
    rows = sorted(conn.execute("select id,val from t").fetchall())
    conn.close()
    assert rows == [(1, "ONE"), (2, "two"), (3, "three")]


def test_replace_overwrites(tmp_path):
    conn = _run(tmp_path, "id\n1\n2\n3\n")
    conn.close()
    conn2 = _run(tmp_path, "id\n5\n6\n7\n", if_exists="replace")
    assert conn2.execute("select count(*) from t").fetchone()[0] == 3
    assert conn2.execute("select id from t where id=5").fetchone()[0] == 5
    conn2.close()


def test_append_adds_rows(tmp_path):
    conn = _run(tmp_path, "id\n1\n")
    conn.close()
    conn2 = _run(tmp_path, "id\n2\n3\n", if_exists="append")
    assert conn2.execute("select count(*) from t").fetchone()[0] == 3
    conn2.close()


def test_missing_key_column_errors(tmp_path):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id\n1\n")
    db_path = tmp_path / "x.db"
    result = subprocess.run(
        [sys.executable, SQL_LOADER_PATH, "--input", str(csv_path),
         "--db", str(db_path), "--table", "t", "--key", "nope"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr