#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
from pathlib import Path

# Path agnosticism setup
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.vector_vault import get_collection


def dual_commit_json_file(json_file_path, sqlite_db_path, collection_name="game_dialogue"):
    """
    Ingests a harvester output JSON and dual-commits records to SQLite and ChromaDB.
    """
    json_file_path = Path(json_file_path)
    if not json_file_path.exists():
        print(f"❌ Error: JSON file not found at: {json_file_path}")
        return False

    with open(json_file_path, encoding="utf-8") as f:
        data = json.load(f)

    # 1. Establish relational SQLite schema initialization
    try:
        with sqlite3.connect(sqlite_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS game_dialogue (
                    composite_key TEXT PRIMARY KEY,
                    file_id TEXT,
                    map_id TEXT,
                    event_id TEXT,
                    line_id TEXT,
                    name TEXT,
                    body TEXT,
                    icon_index INTEGER,
                    keywords TEXT
                );
            """)
    except Exception as e:
        print(f"❌ SQLite Initialization Error: {e}")
        return False

    # 2. Establish vector store collection connection
    try:
        collection = get_collection(name=collection_name)
    except Exception as ce:
        print(f"❌ ChromaDB Connection Error: {ce}")
        return False
    
    sqlite_inserts = []
    chroma_documents = []
    chroma_metadatas = []
    chroma_ids = []

    for composite_key, entry in data.items():
        # Parse fields
        file_id = entry["file_id"]
        map_id = entry["map_id"]
        event_id = entry["event_id"]
        line_id = entry["line_id"]
        name = entry["name"]
        body = entry["body"]
        icon_index = entry["icon_index"]
        keywords = entry["keywords"]

        # Relational staging list (keywords saved as JSON array string)
        sqlite_inserts.append((
            composite_key, file_id, map_id, event_id, line_id, name, body, icon_index, json.dumps(keywords)
        ))

        # Vector vault payload staging
        chroma_ids.append(composite_key)
        chroma_documents.append(body)
        chroma_metadatas.append({
            "composite_key": composite_key,
            "file_id": file_id,
            "map_id": map_id,
            "event_id": event_id,
            "line_id": line_id,
            "name": name,
            "icon_index": icon_index if icon_index is not None else -1,
            "keywords": ",".join(keywords) # Simple types required in ChromaDB metadata
        })

    # Execute SQLite Upserts in a single transactional batch via Context Manager
    sqlite_success = False
    try:
        with sqlite3.connect(sqlite_db_path) as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO game_dialogue 
                (composite_key, file_id, map_id, event_id, line_id, name, body, icon_index, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, sqlite_inserts)
            print(f"✅ SQLite: Staged and UPSERT-ed {len(sqlite_inserts)} entries successfully.")
            sqlite_success = True
    except Exception as se:
        print(f"❌ SQLite Error during batch: {se}")

    # Execute ChromaDB Upserts
    chroma_success = False
    try:
        collection.upsert(
            documents=chroma_documents,
            metadatas=chroma_metadatas,
            ids=chroma_ids
        )
        print(f"✅ ChromaDB: Staged and UPSERT-ed {len(chroma_ids)} vector documents successfully.")
        chroma_success = True
    except Exception as ce:
        print(f"❌ ChromaDB Error during batch: {ce}")

    return sqlite_success and chroma_success

def main():
    parser = argparse.ArgumentParser(description="Dual Commit JSON records to SQLite and ChromaDB Vector Store")
    parser.add_argument("json_file", type=str, help="Path to the JSON file to ingest")
    parser.add_argument("--db", type=str, default="game_vault.db", help="Target SQLite database file path")
    args = parser.parse_args()

    # Resolve database path relative to project root
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / args.db

    success = dual_commit_json_file(args.json_file, db_path)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
