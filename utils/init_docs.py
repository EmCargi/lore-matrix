#!/usr/bin/env python3
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
        
    print("============================================================\n")

if __name__ == '__main__':
    main()
