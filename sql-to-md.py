#!/usr/bin/env python3
"""
Lore Matrix - Relational-to-Obsidian Markdown Exporter
Queries local SQLite database tables/queries and exports them as YAML-frontmatter-equipped
Markdown tables directly into an authorized Obsidian vault subdirectory.
"""

import glob
import json
import os
import sqlite3
import sys
from datetime import datetime

import pandas as pd


# Load Vault Root configuration
def load_vault_root():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check for environment variable override
    env_root = os.environ.get("VAULT_ROOT")
    if env_root:
        return os.path.abspath(env_root)
        
    config_path = os.path.join(script_dir, "config.json")
    default_root = os.path.abspath(os.path.join(script_dir, "vault"))
    
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding='utf-8') as f:
                config = json.load(f)
                val = config.get("VAULT_ROOT", default_root)
                # Resolve relative paths dynamically relative to the script directory
                if not os.path.isabs(val):
                    val = os.path.abspath(os.path.join(script_dir, val))
                return val
        except Exception as e:
            print(f"⚠️ Warning: Failed to parse config.json ({e}). Using default vault root.")
    return default_root

VAULT_ROOT = load_vault_root()

def validate_vault_path(target_path, vault_root):
    """
    CRITICAL SECURITY CHECK: Verifies that the resolved absolute path of the target
    is nested within the authorized Vault Root folder.
    """
    abs_vault_root = os.path.abspath(vault_root)
    abs_target_path = os.path.abspath(target_path)
    
    # Ensure prefix ends with a separator to avoid matching sibling folders
    prefix = abs_vault_root if abs_vault_root.endswith(os.sep) else abs_vault_root + os.sep
    
    if not abs_target_path.startswith(prefix):
        raise PermissionError(
            f"Security Exception: Target destination '{abs_target_path}' lies outside "
            f"the authorized Obsidian Vault Root directory '{abs_vault_root}'."
        )

def scan_workspace_databases(workspace_dir):
    """
    Finds SQLite databases in the workspace and databases/ directory.
    """
    db_patterns = [
        os.path.join(workspace_dir, "*.db"),
        os.path.join(workspace_dir, "*.sqlite"),
        os.path.join(workspace_dir, "databases", "*.db"),
        os.path.join(workspace_dir, "databases", "*.sqlite")
    ]
    found_files = []
    for pattern in db_patterns:
        found_files.extend(glob.glob(pattern))
    return sorted(list(set(os.path.abspath(p) for p in found_files)))

def inspect_database_tables(db_path):
    """
    Returns table names inside the selected SQLite database.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"❌ Error inspecting database: {e}")
        return []

def df_to_markdown(df):
    """
    Custom GitHub-flavored Markdown table generator.
    Avoids requiring the external 'tabulate' library.
    """
    headers = [str(col) for col in df.columns]
    widths = [len(h) for h in headers]
    
    rows_str = []
    for _, row in df.iterrows():
        row_str = [str(val).replace('\n', ' ').strip() for val in row]
        rows_str.append(row_str)
        for i, val in enumerate(row_str):
            widths[i] = max(widths[i], len(val))
            
    header_line = "| " + " | ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers)) + " |"
    divider_line = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
    
    formatted_rows = []
    for row in rows_str:
        formatted_rows.append("| " + " | ".join(f"{val:<{widths[i]}}" for i, val in enumerate(row)) + " |")
        
    return "\n".join([header_line, divider_line] + formatted_rows)

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("================================================================================")
    print("  Lore Matrix - Relational-to-Obsidian Markdown Exporter")
    print("================================================================================")
    print(f"Authorized Vault Root: {VAULT_ROOT}\n")
    
    # 1. Scan and Select Database
    db_files = scan_workspace_databases(script_dir)
    if not db_files:
        print("❌ Error: No SQLite database files found in active workspace.")
        return
        
    print("📂 Available SQLite Databases:")
    for idx, db_path in enumerate(db_files, start=1):
        print(f"[{idx}] {os.path.basename(db_path)}")
        
    while True:
        try:
            db_choice_str = input(f"Select a database (1-{len(db_files)}): ").strip()
            db_choice = int(db_choice_str)
            if 1 <= db_choice <= len(db_files):
                selected_db = db_files[db_choice - 1]
                break
            else:
                print(f"Error: Select between 1 and {len(db_files)}.")
        except ValueError:
            print("Error: Invalid numeric input.")

    db_name = os.path.basename(selected_db)
    
    # 2. Select Table
    tables = inspect_database_tables(selected_db)
    if not tables:
        print(f"❌ Error: Database '{db_name}' contains no tables.")
        return
        
    print("\n📂 Available Tables:")
    for idx, table in enumerate(tables, start=1):
        print(f"[{idx}] {table}")
        
    while True:
        try:
            table_choice_str = input(f"Select a table (1-{len(tables)}): ").strip()
            table_choice = int(table_choice_str)
            if 1 <= table_choice <= len(tables):
                selected_table = tables[table_choice - 1]
                break
            else:
                print(f"Error: Select between 1 and {len(tables)}.")
        except ValueError:
            print("Error: Invalid numeric input.")

    # 3. Query Type selection
    print("\n📊 Query Method Selection:")
    print("  [A] Full Table Export (SELECT * FROM [table])")
    print("  [B] Custom SQL Query")
    
    while True:
        method = input("Enter choice (A/B): ").strip().upper()
        if method in ['A', 'B']:
            break
        print("Error: Invalid choice. Enter A or B.")
        
    query = ""
    export_title = ""
    
    if method == 'A':
        query = f"SELECT * FROM {selected_table}"
        export_title = f"Full Table Export: {selected_table}"
    else:
        print("\n✍️ Type your custom SQL query (e.g. SELECT name, speaker FROM dialogue_results WHERE name IS NOT NULL):")
        query = input("SQL > ").strip()
        export_title = f"Custom SQL Query: {query}"
        
    # Execute query using Pandas read_sql_query
    print("\n🚀 Executing SQLite Query...")
    try:
        with sqlite3.connect(selected_db) as conn:
            df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"❌ Query execution failed: {e}")
        return
        
    if df.empty:
        print("⚠️ Warning: Query returned 0 records. Export cancelled.")
        return
        
    print(f"✅ Loaded {len(df)} records from query.")
    
    # 4. Prompt Vault Output Path
    vault_subfolder = input("\nEnter target Vault sub-folder path (e.g., Dialogue_Data/): ").strip()
    filename = input("Enter output markdown filename (e.g., certification_metrics.md): ").strip()
    if not filename.endswith(".md"):
        filename += ".md"
        
    target_dir = os.path.join(VAULT_ROOT, vault_subfolder)
    target_file_path = os.path.join(target_dir, filename)
    
    # CRITICAL SECURITY SANITY CHECK
    try:
        validate_vault_path(target_file_path, VAULT_ROOT)
    except PermissionError as pe:
        print(f"\n❌ SECURITY EXCEPTION BLOCKED WRITING OPERATION:\n{pe}")
        sys.exit(1)
        
    # Generate content
    exported_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    yaml_frontmatter = f"""---
type: lore-matrix-export
source_db: {db_name}
exported_at: {exported_at}
---
# Export: {export_title}

"""
    markdown_table = df_to_markdown(df)
    
    # Check if target exists
    exists = os.path.exists(target_file_path)
    write_mode = 'w'
    final_content = ""
    
    if exists:
        print(f"\n⚠️ File '{filename}' already exists in target path '{vault_subfolder}'.")
        print("  [1] Overwrite existing file")
        print("  [2] Append results to existing file")
        while True:
            exists_choice = input("Enter choice (1-2): ").strip()
            if exists_choice == '1':
                write_mode = 'w'
                final_content = yaml_frontmatter + markdown_table + "\n"
                break
            elif exists_choice == '2':
                write_mode = 'a'
                final_content = f"\n\n---\n## Additional Export ({exported_at})\n\n" + markdown_table + "\n"
                break
            print("Error: Invalid choice. Enter 1 or 2.")
    else:
        write_mode = 'w'
        final_content = yaml_frontmatter + markdown_table + "\n"
        
    # Safely create target directory since path validation has already passed successfully
    os.makedirs(target_dir, exist_ok=True)
    
    try:
        with open(target_file_path, write_mode, encoding='utf-8') as f:
            f.write(final_content)
        action_word = "overwritten" if write_mode == 'w' and exists else ("appended" if write_mode == 'a' else "created")
        print(f"\n✅ Success: Markdown file has been {action_word} at:\n   {target_file_path}")
    except Exception as e:
        print(f"❌ Failed to write export file: {e}")

if __name__ == "__main__":
    main()
