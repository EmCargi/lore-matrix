#!/usr/bin/env python3
"""
Lore Matrix - Generic SQL Loader Engine
Ingests structured datasets (CSV/XLSX), sanitizes column names for SQL compliance, and loads
them into a local SQLite database with a strategy-driven, non-destructive approach.

This is the DOMAIN-AGNOSTIC "anything -> SQLite" runner (menu option 4, `--input --db --table`).
It superseded the old domain-specific loader, keeping its data-integrity ideas -- safe table
strategy, optional idempotent UPSERT -- while staying fully generic (no domain mappings).

Flags:
  * --if-exists fail|replace|append   strategy when the target table already exists (default: fail)
  * --key COLUMN                       optional unique-key idempotent UPSERT
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

# Anchor BASE_DIR relative to this script's parent for robust pathlib resolution.
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from config.settings import BASE_DIR
except ImportError:  # pragma: no cover - config is project-specific
    pass


def resolve_path(path_str: str) -> Path:
    """Resolve a path relative to BASE_DIR if it is not already absolute."""
    p = Path(path_str)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


def sanitize_column(col) -> str:
    """Force a single header cell into lowercase, underscore-safe, SQL-compliant form."""
    return (
        str(col).strip().lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace(".", "")
    )


def sanitize_columns(columns) -> list:
    """Sanitize every column and guarantee uniqueness (avoid duplicate SQLite columns)."""
    result = []
    counts = {}
    for raw in columns:
        name = sanitize_column(raw)
        if name in counts:
            counts[name] += 1
            name = f"{name}_{counts[name]}"
        else:
            counts[name] = 0
        result.append(name)
    return result


def load_dataset(input_path: Path) -> pd.DataFrame:
    """Read a CSV/XLSX dataset and sanitize its column headers into SQL-compliant form."""
    if not input_path.exists():
        print(f"❌ Error: Input file does not exist at '{input_path}'", file=sys.stderr)
        sys.exit(1)

    ext = input_path.suffix.lower()
    try:
        if ext == ".csv":
            df = pd.read_csv(input_path)
        elif ext in [".xlsx", ".xls"]:
            df = pd.read_excel(input_path)
        else:
            print(f"❌ Error: Unsupported format signature '{ext}'", file=sys.stderr)
            sys.exit(1)

        df.columns = sanitize_columns(df.columns)
        return df
    except Exception as e:
        print(f"❌ Error: Failed to read dataset: {e}", file=sys.stderr)
        sys.exit(1)


def build_upsert(table: str, columns, key: str) -> str:
    """Build an idempotent INSERT ... ON CONFLICT(KEY) DO UPDATE statement."""
    quoted = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f'"{c}" = excluded."{c}"' for c in columns if c != key)
    if updates:
        conflict = f'ON CONFLICT("{key}") DO UPDATE SET {updates}'
    else:
        conflict = f'ON CONFLICT("{key}") DO NOTHING'
    return f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders}) {conflict}'


def main():
    parser = argparse.ArgumentParser(description="Generic SQL Loader: CSV or XLSX datasets into SQLite.")
    parser.add_argument("--input", required=True, help="Path to the input CSV or XLSX dataset")
    parser.add_argument("--db", required=True, help="Path to the target SQLite database file (.db)")
    parser.add_argument("--table", required=True, help="Name of the SQLite table to create or load into")
    parser.add_argument("--if-exists", choices=["fail", "replace", "append"], default="fail",
                        help="Behavior when the target table already exists (default: fail). Ignored when --key is set.")
    parser.add_argument("--key", default=None,
                        help="Column to treat as the unique key for idempotent UPSERT (ON CONFLICT DO UPDATE).")
    args = parser.parse_args()

    input_path = resolve_path(args.input)
    db_path = resolve_path(args.db)
    table = args.table.strip().lower().replace(" ", "_").replace("-", "_")

    # 1. Read and sanitize the dataset layout
    print(f"[*] Extracting dataset from: {input_path.name}")
    df = load_dataset(input_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Validate the optional key column exists in the dataset
    if args.key and args.key not in df.columns:
        print(f"❌ Error: Key column '{args.key}' not found in dataset columns: {list(df.columns)}",
              file=sys.stderr)
        sys.exit(1)

    # 3. Write into SQLite under the chosen strategy
    print(f"[*] Writing {len(df)} records into table '{table}'...")
    try:
        with sqlite3.connect(db_path) as conn:
            existed = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone() is not None

            if existed and args.if_exists == "fail" and not args.key:
                print(f"❌ Error: Table '{table}' already exists. Rerun with --if-exists append|replace "
                      f"(or --key for idempotent upsert) to proceed.", file=sys.stderr)
                sys.exit(1)

            columns = list(df.columns)

            if args.key:
                # Idempotent path: create once, then UPSERT for repeatable ingestion.
                if not existed:
                    df.to_sql(name=table, con=conn, if_exists="replace", index=False)
                conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "u_{table}_{args.key}" '
                             f'ON "{table}" ("{args.key}")')
                conn.executemany(build_upsert(table, columns, args.key), df[columns].values.tolist())
                status = f"UPSERT (key '{args.key}')"
            else:
                if args.if_exists == "replace":
                    df.to_sql(name=table, con=conn, if_exists="replace", index=False)
                    status = "replace"
                else:  # append
                    df.to_sql(name=table, con=conn, if_exists="append", index=False)
                    status = "append"
    except SystemExit:
        raise
    except Exception as e:
        print(f"❌ Error: Failed to load data into database: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Confirmation logging ledger
    print("\n" + "=" * 60)
    print("🚀 SQL Loader Ingestion Successful")
    print("=" * 60)
    print(f"📊 Rows Affected:  {len(df)}")
    print(f"🗂️  Target Table:    {table}")
    print(f"💾 Strategy:        {status}")
    print(f"💾 Database Path:   {db_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()