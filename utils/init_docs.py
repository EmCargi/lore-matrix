#!/usr/bin/env python3
import shutil
from pathlib import Path


def main():
    # 1. Path Enforcement
    # Path(__file__).resolve().parents[1] resolves to the repo root (BASE_DIR)
    BASE_DIR = Path(__file__).resolve().parents[1]
    
    # Define directories to create
    directories = [
        BASE_DIR / "docs" / "architecture",
        BASE_DIR / "docs" / "modules",
        BASE_DIR / "docs" / "journal",
        BASE_DIR / "docs" / "templates"
    ]
    
    print("============================================================")
    print("📂 Initializing Documentation Directories")
    print("============================================================")
    
    # 2. Directory Grid Execution
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"✅ Initialized: {directory.absolute()}")
        
    # 3. Initial Asset Extraction
    
    # Asset A: system-details.md check and migration
    system_details_src = BASE_DIR / "system-details.md"
    system_details_dest = BASE_DIR / "docs" / "architecture" / "system-details.md"
    
    if system_details_src.exists():
        try:
            shutil.copy2(system_details_src, system_details_dest)
            print(f"📝 Copied system-details.md to {system_details_dest.absolute()}")
        except Exception as e:
            print(f"⚠️ Warning: Failed to copy system-details.md: {e}")
    else:
        print("ℹ️ No system-details.md found in repository root to migrate.")
        
    # Asset B: Generate 2026-06-28_sql-pivot.md journal entry
    journal_path = BASE_DIR / "docs" / "journal" / "2026-06-28_sql-pivot.md"
    
    journal_content = """# Journal Entry: 2026-06-28 - SQLite Pivot

## Context & Overview
Historically, dataset hosting and querying configurations targeted cloud-hosted analytical solutions such as Google Cloud BigQuery. While BigQuery provides immense scalability for enterprise datasets, our local, modular development workflows call for a simpler, zero-cost, fully offline storage medium.

To align with the project design principles, we have transitioned from BigQuery to a local, offline SQLite environment.

## Key Motivations for the Pivot
1. **Offline Autonomy**: Eliminates external network dependencies, permitting local ingestion and querying without active internet or Google Cloud credentials.
2. **Simplified Development Setup**: SQLite is built directly into Python (`sqlite3`), removing the need for external service client installations, IAM configurations, and environment keys.
3. **Zero Cost and High Performance**: Running queries locally on SQLite eliminates cloud computing costs, data ingress/egress charges, and network roundtrip latency.
4. **Seamless Pandas Integration**: Pandas supports native, high-performance serialization directly to SQLite via `df.to_sql()` and reading via `pd.read_sql()`.

## Implementation Strategy
- A modular loader script (`sql-loader.py`) handles CSV and XLSX dataset ingestion dynamically.
- Datasets are automatically cleaned and loaded into the database file using pandas dataframes, resolving absolute paths relative to `BASE_DIR`.
- Tables are created or overwritten cleanly on-demand (`if_exists='replace'`), serving as a fast cache for local data processing, visualizer runs, and lorebook compiling pipelines.
"""
    
    try:
        journal_path.write_text(journal_content, encoding="utf-8")
        print(f"📝 Generated journal entry at: {journal_path.absolute()}")
    except Exception as e:
        print(f"❌ Error: Failed to write journal entry: {e}")
        
    print("============================================================\n")

if __name__ == '__main__':
    main()
