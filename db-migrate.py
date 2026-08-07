#!/usr/bin/env python3
"""
Lore Matrix - Database Migration & Backup Manager
Creates timestamped backups of SQLite databases before migration or ingestion tasks,
and handles rollback/restore operations with safety checks.
"""

import glob
import os
import shutil
from datetime import datetime

# Resolve workspace directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = SCRIPT_DIR
BACKUPS_DIR = os.path.join(WORKSPACE_DIR, "backups")

def list_databases():
    """
    Scans the workspace root and databases/ directory for .db or .sqlite files.
    """
    db_patterns = [
        os.path.join(WORKSPACE_DIR, "*.db"),
        os.path.join(WORKSPACE_DIR, "*.sqlite"),
        os.path.join(WORKSPACE_DIR, "databases", "*.db"),
        os.path.join(WORKSPACE_DIR, "databases", "*.sqlite")
    ]
    found_files = []
    for pattern in db_patterns:
        found_files.extend(glob.glob(pattern))
    # Deduplicate and return absolute normalized paths
    return sorted(list(set(os.path.abspath(p) for p in found_files)))

def create_backup(db_path):
    """
    Copies the selected database to the backups/ directory.
    Uses relative-path encoding in the filename to preserve subdirectories.
    """
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    
    # Calculate relative path from workspace root
    rel_path = os.path.relpath(db_path, WORKSPACE_DIR)
    
    # Encode folder structure to avoid filesystem conflicts
    rel_path_encoded = rel_path.replace(os.sep, "__DIR__")
    
    # Generate timestamped backup path
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"{rel_path_encoded}_backup_{timestamp}.bak"
    backup_path = os.path.join(BACKUPS_DIR, backup_filename)
    
    try:
        shutil.copy2(db_path, backup_path)
        db_name = os.path.basename(db_path)
        print(f"✅ Database '{db_name}' successfully snapshotted to backups/{backup_filename}.")
        return backup_path
    except Exception as e:
        print(f"❌ Failed to create backup: {e}")
        return None

def restore_backup():
    """
    Scans backups/ directory and allows user to restore a snapshot.
    """
    if not os.path.exists(BACKUPS_DIR):
        print("\n[SYSTEM LOG] No backups directory found (no backups created yet).")
        return
        
    backup_pattern = os.path.join(BACKUPS_DIR, "*.bak")
    backups = sorted(glob.glob(backup_pattern))
    
    if not backups:
        print("\n[SYSTEM LOG] No backup (.bak) files found in backups/ directory.")
        return
        
    print("\n📂 Available Database Backups:")
    for idx, backup_path in enumerate(backups, start=1):
        filename = os.path.basename(backup_path)
        # Parse visual info
        parts = filename.split('_backup_')
        encoded_name = parts[0]
        original_rel_path = encoded_name.replace("__DIR__", os.sep)
        timestamp_part = parts[1].replace(".bak", "") if len(parts) > 1 else "unknown"
        print(f"[{idx}] {original_rel_path} (Backed up on: {timestamp_part})")
        
    while True:
        try:
            choice_str = input(f"Select backup to restore (1-{len(backups)}) or 'c' to cancel: ").strip()
            if choice_str.lower() == 'c':
                print("Restore operation cancelled.")
                return
            choice = int(choice_str)
            if 1 <= choice <= len(backups):
                selected_backup = backups[choice - 1]
                break
            else:
                print(f"Error: Please enter a number between 1 and {len(backups)}.")
        except ValueError:
            print("Error: Invalid input. Please enter a number or 'c'.")
            
    # Decode target destination
    backup_basename = os.path.basename(selected_backup)
    parts = backup_basename.split('_backup_')
    encoded_name = parts[0]
    original_rel_path = encoded_name.replace("__DIR__", os.sep)
    target_db_path = os.path.join(WORKSPACE_DIR, original_rel_path)
    
    # CRITICAL SAFETY: prompt before overwriting
    print("\n⚠️ WARNING: Restoring this backup will OVERWRITE the current file at:")
    print(f"   {target_db_path}")
    confirm = input("Are you absolutely sure you want to proceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Restore operation aborted.")
        return
        
    try:
        # Ensure parent folder of target path exists (e.g. databases/)
        os.makedirs(os.path.dirname(target_db_path), exist_ok=True)
        shutil.copy2(selected_backup, target_db_path)
        print(f"✅ Database successfully restored to active sandbox: {original_rel_path}")
    except Exception as e:
        print(f"❌ Failed to restore database: {e}")

def main():
    while True:
        print("\n" + "=" * 60)
        print("💾 DATABASE SNAPSHOT & ROLLBACK ENGINE")
        print("=" * 60)
        print("1. Create Database Backup (Snapshot)")
        print("2. Restore Database from Backup")
        print("3. Exit")
        print("=" * 60)
        
        choice = input("Enter choice (1-3): ").strip()
        
        if choice == '1':
            databases = list_databases()
            if not databases:
                print("\n[SYSTEM LOG] Empty state: No SQLite databases found in workspace to backup.")
                continue
                
            print("\n📂 Found Active Relational Sandboxes:")
            for idx, db_path in enumerate(databases, start=1):
                # Print relative path from workspace root
                rel_path = os.path.relpath(db_path, WORKSPACE_DIR)
                print(f"[{idx}] {rel_path}")
                
            while True:
                try:
                    db_choice_str = input(f"Select database to backup (1-{len(databases)}) or 'c' to cancel: ").strip()
                    if db_choice_str.lower() == 'c':
                        break
                    db_choice = int(db_choice_str)
                    if 1 <= db_choice <= len(databases):
                        create_backup(databases[db_choice - 1])
                        break
                    else:
                        print(f"Error: Please enter a number between 1 and {len(databases)}.")
                except ValueError:
                    print("Error: Invalid input. Please enter a number or 'c'.")
                    
        elif choice == '2':
            restore_backup()
        elif choice == '3':
            print("Exiting Snapshot Engine.")
            break
        else:
            print("⚠️ Invalid choice. Please enter a number between 1 and 3.")

if __name__ == "__main__":
    main()
