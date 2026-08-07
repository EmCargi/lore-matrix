import os
import subprocess
import sys

from config.settings import ACTIVE_SYSTEM


def run_script(script_name, *args, env=None):
    """
    Executes a python script in a subprocess, catching execution errors.
    """
    print(f"\n🚀 Launching {script_name}...")
    try:
        # Resolve path relative to this script's directory for reliability
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(script_dir, script_name)
        
        # Merge environment variables if passed
        subprocess_env = os.environ.copy()
        if env:
            subprocess_env.update(env)
            
        subprocess.run([sys.executable, full_path] + list(args), check=True, env=subprocess_env)
        print(f"\n✅ {script_name} completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error: {script_name} failed with exit code {e.returncode}.")
    except Exception as e:
        print(f"\n❌ Unexpected error launching {script_name}: {e}")


def scan_workspace_databases(workspace_dir):
    """
    Scans the active workspace (root folder and a databases/ subdirectory)
    for files ending in .db or .sqlite.
    """
    import glob
    db_patterns = [
        os.path.join(workspace_dir, "*.db"),
        os.path.join(workspace_dir, "*.sqlite"),
        os.path.join(workspace_dir, "databases", "*.db"),
        os.path.join(workspace_dir, "databases", "*.sqlite")
    ]
    
    found_files = []
    for pattern in db_patterns:
        found_files.extend(glob.glob(pattern))
        
    unique_paths = sorted(list(set(os.path.abspath(p) for p in found_files)))
    return unique_paths


def inspect_database_tables(db_path):
    """
    Connects to the database and retrieves the names of all tables.
    """
    try:
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            return tables
    except Exception as e:
        print(f"\n[SYSTEM LOG] Error inspecting database tables: {e}")
        return []


def run_visualizer_wizard():
    """
    Interactive wizard to run the Data Visualizer Engine using SQLite databases or raw files.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Scan for database files
    try:
        db_files = scan_workspace_databases(script_dir)
    except Exception as e:
        print(f"\n[SYSTEM LOG] Error scanning workspace: {e}")
        db_files = []
        
    if not db_files:
        print("\n[SYSTEM LOG] Empty directory state: No SQLite database files (.db or .sqlite) found in the active workspace.")
        choice = input("Would you like to run the SQL Data Loader Engine to generate your first database schema? (y/n): ").strip().lower()
        if choice == 'y':
            run_sql_loader_wizard()
        return

    print("\n📂 Found Active Relational Sandboxes:")
    for idx, db_path in enumerate(db_files, start=1):
        print(f"[{idx}] {os.path.basename(db_path)}")
    
    new_db_option_num = len(db_files) + 1
    raw_file_option_num = len(db_files) + 2
    
    print(f"[{new_db_option_num}] Create a brand new database file")
    print(f"[{raw_file_option_num}] Visualize a raw CSV/XLSX file instead")
    
    selected_db_path = None
    visualize_raw_file = False
    
    while True:
        try:
            choice_str = input(f"Enter choice (1-{raw_file_option_num}): ").strip()
            if not choice_str:
                continue
            choice = int(choice_str)
            if 1 <= choice <= len(db_files):
                selected_db_path = db_files[choice - 1]
                break
            elif choice == new_db_option_num:
                new_db_name = input("Enter a fresh database file name (e.g., certification_metrics.db): ").strip()
                if not new_db_name:
                    print("Error: Database name cannot be empty.")
                    continue
                if not new_db_name.endswith('.db') and not new_db_name.endswith('.sqlite'):
                    new_db_name += '.db'
                selected_db_path = os.path.join(script_dir, new_db_name)
                # Touch/Create the file safely
                with open(selected_db_path, 'a'):
                    os.utime(selected_db_path, None)
                print(f"Created/selected database file: {os.path.basename(selected_db_path)}")
                break
            elif choice == raw_file_option_num:
                visualize_raw_file = True
                break
            else:
                print(f"Error: Please enter a number between 1 and {raw_file_option_num}.")
        except ValueError:
            print("Error: Invalid numeric input. Please try again.")

    if visualize_raw_file:
        user_input = input("Enter the path to the raw data (CSV/XLSX): ").strip()
        user_output = input("Enter the name for the output image (e.g., chart.png): ").strip()
        user_type = input("Select chart type (bar, line, box): ").strip()
        
        print("\n🚀 Launching visualize-data.py...")
        try:
            script_path = os.path.join(script_dir, "core", "visualize-data.py")
            subprocess.run(
                [sys.executable, script_path, "--input", user_input, "--output", user_output, "--chart-type", user_type],
                check=True
            )
            print("\n✅ core/visualize-data.py completed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Error: visualize-data.py failed with exit code {e.returncode}.")
        except Exception as e:
            print(f"\n❌ Unexpected error launching visualize-data.py: {e}")
        return

    # Check tables in selected database
    tables = inspect_database_tables(selected_db_path)
    if not tables:
        print(f"\n[SYSTEM LOG] Empty schema state: Database '{os.path.basename(selected_db_path)}' has no tables.")
        choice = input("Would you like to run the SQL Data Loader Engine to load data into this database? (y/n): ").strip().lower()
        if choice == 'y':
            run_sql_loader_wizard(prefilled_db=selected_db_path)
        return

    # Stream tables out as a secondary interactive selection list
    print("\n📂 Available Database Tables:")
    for idx, table in enumerate(tables, start=1):
        print(f"[{idx}] {table}")
        
    while True:
        try:
            table_choice_str = input(f"Select a table (1-{len(tables)}): ").strip()
            if not table_choice_str:
                continue
            table_choice = int(table_choice_str)
            if 1 <= table_choice <= len(tables):
                selected_table = tables[table_choice - 1]
                break
            else:
                print(f"Error: Please enter a number between 1 and {len(tables)}.")
        except ValueError:
            print("Error: Invalid numeric input. Please try again.")

    user_output = input("Enter the name for the output image (e.g., chart.png): ").strip()
    user_type = input("Select chart type (bar, line, box): ").strip()

    print("\n🚀 Launching visualize-data.py...")
    try:
        script_path = os.path.join(script_dir, "core", "visualize-data.py")
        subprocess.run(
            [sys.executable, script_path, "--db", selected_db_path, "--table", selected_table, "--output", user_output, "--chart-type", user_type],
            check=True
        )
        print("\n✅ core/visualize-data.py completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error: visualize-data.py failed with exit code {e.returncode}.")
    except Exception as e:
        print(f"\n❌ Unexpected error launching visualize-data.py: {e}")


def run_sql_loader_wizard(prefilled_db=None):
    """
    Interactive wizard to run the SQL Data Loader Engine.
    """
    user_in = input("Enter the path to the dataset (CSV/XLSX): ").strip()
    if prefilled_db:
        default_db = os.path.basename(prefilled_db)
        user_db = input(f"Enter target SQLite database filename [default: {default_db}]: ").strip()
        if not user_db:
            user_db = prefilled_db
    else:
        user_db = input("Enter target SQLite database filename (e.g., data_lab.db): ").strip()
    user_table = input("Enter destination table name: ").strip()
    
    print("\n🚀 Launching sql_loader.py...")
    try:
        # Resolve path relative to this script's directory for reliability
        script_dir = os.path.dirname(os.path.abspath(__file__))
        loader_script = os.path.join(script_dir, "sql-loader.py")
        
        subprocess.run(
            [sys.executable, loader_script, '--input', user_in, '--db', user_db, '--table', user_table,
             '--if-exists', 'replace'],
            check=True
        )
        print("\n✅ sql-loader.py completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error: sql-loader.py failed with exit code {e.returncode}.")
    except Exception as e:
        print(f"\n❌ Unexpected error launching sql-loader.py: {e}")


def run_dual_commit_wizard():
    """
    Interactive wizard to dual-commit game dialogue JSON files to SQLite and ChromaDB.
    """
    import glob

    from config.settings import OUTPUT_CHUNKS_DIR
    
    # Scan for game_text_*.json files in OUTPUT_CHUNKS_DIR
    search_pattern = os.path.join(OUTPUT_CHUNKS_DIR, "game_text_*.json")
    json_files = glob.glob(search_pattern)
    
    if not json_files:
        print(f"\n[SYSTEM LOG] Empty output state: No game_text_*.json files found in '{OUTPUT_CHUNKS_DIR}'.")
        print("Please run option 5 (Ingest Game Dialogue) first to generate a staging file.")
        return
        
    print("\n📂 Found Staged Game Dialogue JSON Chunks:")
    for idx, file_path in enumerate(json_files, start=1):
        print(f"[{idx}] {os.path.basename(file_path)}")
        
    print(f"[{len(json_files) + 1}] Cancel and return")
    
    while True:
        try:
            choice_str = input(f"Select a file (1-{len(json_files) + 1}): ").strip()
            if not choice_str:
                continue
            choice = int(choice_str)
            if 1 <= choice <= len(json_files):
                selected_file = json_files[choice - 1]
                break
            elif choice == len(json_files) + 1:
                return
            else:
                print(f"Error: Please enter a number between 1 and {len(json_files) + 1}.")
        except ValueError:
            print("Error: Invalid numeric input. Please try again.")
            
    db_name = input("Enter target SQLite database filename [default: game_vault.db]: ").strip()
    if not db_name:
        db_name = "game_vault.db"
        
    if not db_name.endswith('.db') and not db_name.endswith('.sqlite'):
        db_name += '.db'
        
    print(f"\n🚀 Launching dual_commit.py on {os.path.basename(selected_file)}...")
    run_script("src/storage/dual_commit.py", selected_file, "--db", db_name)


def run_slicer_wizard():
    """
    Interactive wizard to slice monolithic markdown files into individual card files.
    """
    input_file = input("Enter path to monolithic Markdown file to slice: ").strip()
    if not input_file:
        print("⚠️ Input file path cannot be empty.")
        return
        
    output_dir = input("Enter target vault sub-folder [default: obsidian_vault/dialogue_split]: ").strip()
    if not output_dir:
        output_dir = "obsidian_vault/dialogue_split"
        
    print(f"\n🚀 Launching md_slicer.py on {input_file}...")
    run_script("src/utils/md_slicer.py", input_file, "--output-dir", output_dir)



def main():
    while True:
        # Clear the terminal screen
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Stylized ASCII header
        print("================================================================================================")
        print("  _______ _    _ ______   _      ____  _____  ______   __  __          _______ _____  _______   __")
        print(" |__   __| |  | |  ____| | |    / __ \\|  __ \\|  ____| |  \\/  |   /\\   |__   __|  __ \\|_   _\\ \\ / /")
        print("    | |  | |__| | |__    | |   | |  | | |__) | |__    | \\  / |  /  \\     | |  | |__) | | |  \\ V / ")
        print("    | |  |  __  |  __|   | |   | |  | |  _  /|  __|   | |\\/| | / /\\ \\    | |  |  _  /  | |   > <  ")
        print("    | |  | |  | | |____  | |___| |__| | | \\ \\| |____  | |  | |/ ____ \\   | |  | | \\ \\ _| |_ / . \\ ")
        print("    |_|  |_|  |_|______| |______\\____/|_|  \\_\\______| |_|  |_/_/    \\_\\  |_|  |_|  \\_\\_____/_/ \\_\\")
        print("                                                                                                ")
        print("================================================================================================")
        print(f"Active System: {ACTIVE_SYSTEM}")
        print("================================================================================================")
        print("1. Run Unified Ingestor (ingest.py)")
        print("2. Compile JSON to Obsidian Notes (json_to_obsidian.py)")
        print("3. Data Visualizer Engine")
        print("4. SQL Data Loader Engine")
        print("5. Extract Data Tables (Strict PDF-to-CSV) (extract-tables.py)")
        print("6. Profile and Sanitize Raw Datasets (data-profile.py)")
        print("7. Database Backup & Rollback Manager (db-migrate.py)")
        print("8. Export SQL to Obsidian Markdown (sql-to-md.py)")
        print("9. Harvest Narrative Tropes (trope_scraper.py)")
        print("10. Vault & Query Tropes Submenu (vector_vault.py)")
        print("11. Advanced: Run Individual Ingestors Submenu")
        print("12. Ingest Frozen Asset from ArchiveBox (via Timestamp ID)")
        print("13. Slice Monolithic Markdown File (md_slicer.py)")
        print("14. Exit")
        print("================================================================================================")
        
        choice = input("Enter choice (1-14): ").strip()
        
        if choice == '1':
            model_input = input("Enter processing model override (optional, press Enter to skip): ").strip()
            cmd_args = []
            if model_input:
                cmd_args.extend(["--model", model_input])
            run_script("ingest.py", *cmd_args)
        elif choice == '2':
            # Setup environment variables: include PYTHONPATH so src/transformers/json_to_obsidian.py can import core
            script_dir = os.path.dirname(os.path.abspath(__file__))
            env = os.environ.copy()
            env["PYTHONPATH"] = script_dir + (os.pathsep + env.get("PYTHONPATH", "")) if env.get("PYTHONPATH") else script_dir
            run_script("src/transformers/json_to_obsidian.py", env=env)
        elif choice == '3':
            run_visualizer_wizard()
        elif choice == '4':
            run_sql_loader_wizard()
        elif choice == '5':
            run_script("extract-tables.py")
        elif choice == '6':
            run_script("data-profile.py")
        elif choice == '7':
            run_script("db-migrate.py")
        elif choice == '8':
            run_script("sql-to-md.py")
        elif choice == '9':
            # Setup environment variables: include PYTHONPATH so src/scrapers/trope_scraper.py can import core
            script_dir = os.path.dirname(os.path.abspath(__file__))
            env = os.environ.copy()
            env["PYTHONPATH"] = script_dir + (os.pathsep + env.get("PYTHONPATH", "")) if env.get("PYTHONPATH") else script_dir
            run_script("src/scrapers/trope_scraper.py", env=env)
        elif choice == '10':
            # Setup environment variables: include PYTHONPATH so src/storage/vector_vault.py can import core
            script_dir = os.path.dirname(os.path.abspath(__file__))
            env = os.environ.copy()
            env["PYTHONPATH"] = script_dir + (os.pathsep + env.get("PYTHONPATH", "")) if env.get("PYTHONPATH") else script_dir
            run_script("src/storage/vector_vault.py", env=env)
        elif choice == '11':
            print("\n==========================================")
            print("  Advanced: Individual Ingestors Menu")
            print("==========================================")
            print("1. Ingest PDFs (extract-pdf.py)")
            print("2. Ingest Web Targets (extract-web.py)")
            print("3. Ingest Images (extract-vision.py)")
            print("4. Ingest Manga OCR (extract-manga.py)")
            print("5. Ingest Game Dialogue (extract-game-text.py)")
            print("6. Dual-Commit Game Text JSON (dual_commit.py)")
            print("7. Return to Main Menu")
            print("==========================================")
            sub_choice = input("Enter choice (1-7): ").strip()
            
            if sub_choice == '1':
                run_script("extract-pdf.py")
            elif sub_choice == '2':
                run_script("extract-web.py")
            elif sub_choice == '3':
                while True:
                    dir_choice = input("Are these images Manga (RTL) or Western Comics (LTR)? (Type RTL or LTR): ").strip().upper()
                    if dir_choice in ['RTL', 'LTR']:
                        break
                    print("⚠️ Invalid choice. Please enter 'RTL' or 'LTR'.")
                
                context_input = input("Enter scene context (optional, press Enter to skip): ").strip()
                
                preprocess_choice = input("Enable image pre-processing (denoising & contrast)? (y/N): ").strip().lower()
                deskew_choice = input("Enable automatic deskewing (rotation correction)? (y/N): ").strip().lower()
                binarize_choice = input("Enable binarization (high-contrast black/white)? (y/N): ").strip().lower()
                debug_ocr_choice = input("Enable Visual OCR Debugging (saves annotated bounding boxes)? (y/N): ").strip().lower()
                workers_input = input("Enter number of concurrent workers (default 1): ").strip()
                rate_limit_input = input("Enter rate limit delay in seconds (default 0): ").strip()
                
                cmd_args = ["--direction", dir_choice]
                if context_input:
                    cmd_args.extend(["--context", context_input])
                if preprocess_choice == 'y':
                    cmd_args.append("--preprocess")
                if deskew_choice == 'y':
                    cmd_args.append("--deskew")
                if binarize_choice == 'y':
                    cmd_args.append("--binarize")
                if debug_ocr_choice == 'y':
                    cmd_args.append("--debug-ocr")
                if workers_input.isdigit() and int(workers_input) > 1:
                    cmd_args.extend(["--workers", workers_input])
                try:
                    if rate_limit_input and float(rate_limit_input) > 0:
                        cmd_args.extend(["--rate-limit", rate_limit_input])
                except ValueError:
                    pass
                    
                run_script("extract-vision.py", *cmd_args)
            elif sub_choice == '4':
                model_input = input("Enter processing model [default: deepseek-r1:7b]: ").strip()
                cmd_args = []
                if model_input:
                    cmd_args.extend(["--model", model_input])
                run_script("extract-manga.py", *cmd_args)
            elif sub_choice == '5':
                run_script("extract-game-text.py")
            elif sub_choice == '6':
                run_dual_commit_wizard()
        elif choice == '12':
            timestamp_id = input("Enter ArchiveBox Timestamp ID (e.g. 1718912345): ").strip()
            if timestamp_id:
                run_script("extract-web.py", "--archive", timestamp_id)
            else:
                print("⚠️ Timestamp ID cannot be empty.")
        elif choice == '13':
            run_slicer_wizard()
        elif choice == '14':
            print("\nGoodbye!")
            break
        else:
            print("\n⚠️ Invalid choice. Please enter a number between 1 and 14.")
            
        input("\nPress Enter to return to the main menu...")

if __name__ == "__main__":
    main()
