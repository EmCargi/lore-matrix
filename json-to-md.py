import json
import os
import re
from pathlib import Path

from config.settings import ACTIVE_SYSTEM, OUTPUT_CHUNKS_DIR, RAW_VAULT_DIR


def unpack_universal_rulebook(json_path, target_vault_dir, system_name="Generic_RPG"):
    print(f"⚙️ Ingesting {system_name} data from {json_path}...")
    vault_path = Path(target_vault_dir) / system_name
    vault_path.mkdir(parents=True, exist_ok=True)

    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)
        entries = data.get('entries', data)

    for entry in entries:
        raw_name = entry.get('name', 'Unnamed')
        safe_title = re.sub(r'[\\/*?:"<>|]', "-", raw_name).strip()
        content = entry.get('content', '')

        # 1. Alias Extraction (SillyTavern keys -> Obsidian Aliases)
        st_keys = entry.get('keys', [])
        if isinstance(st_keys, str):
            st_keys = [k.strip() for k in st_keys.split(',')]
        
        # 2. Dynamic YAML Foundation
        yaml_dict = {
            "system": system_name,
            "tags": [system_name.lower(), "auto-gen"],
            "aliases": st_keys
        }

        # 3. Dynamic Bracket Extraction [Key: Value]
        metadata_matches = re.findall(r'\[([^\]:]+):\s*([^\]]+)\]', content)
        
        for key, value in metadata_matches:
            clean_key = key.strip().lower().replace(" ", "_")
            yaml_dict[clean_key] = value.strip()
            # Strip the brackets from the markdown text with flexible whitespace
            pattern = rf'\[\s*{re.escape(key.strip())}\s*:\s*{re.escape(value.strip())}\s*\]'
            content = re.sub(pattern, "", content)

        # 4. Build YAML Frontmatter
        yaml_lines = ["---"]
        for k, v in yaml_dict.items():
            if isinstance(v, list):
                yaml_lines.append(f"{k}: {json.dumps(v)}")
            else:
                yaml_lines.append(f"{k}: {v}")
        yaml_lines.append("---\n")
        yaml_frontmatter = "\n".join(yaml_lines)

        # 5. Smart Folder Routing
        subfolder_name = yaml_dict.get('type', 'General_Rules').title()
        final_dir = vault_path / subfolder_name
        final_dir.mkdir(exist_ok=True)

        # 6. Write out the Markdown Note
        filepath = final_dir / f"{safe_title}.md"
        with open(filepath, "w", encoding='utf-8') as md_file:
            md_file.write(yaml_frontmatter)
            md_file.write(f"# {raw_name}\n\n")
            md_file.write(content.strip())

    print(f"  ✅ Vault built successfully at: {vault_path.absolute()}")

if __name__ == "__main__":
    # Sweep output chunks from the settings configuration directory recursively
    chunk_files = []
    if OUTPUT_CHUNKS_DIR.exists():
        for p in OUTPUT_CHUNKS_DIR.rglob("*.json"):
            # Exclude debug folders
            if "debug" not in p.parts:
                chunk_files.append(p)
    
    # Fallback to local 'JSON_Lorebooks' if configured output is empty and it exists
    if not chunk_files and os.path.exists("JSON_Lorebooks"):
        print("  ℹ️ No JSON chunks found in output directory. Checking fallback 'JSON_Lorebooks'...")
        for p in Path("JSON_Lorebooks").rglob("*.json"):
            chunk_files.append(p)
        
    if not chunk_files:
        print(f"📭 No JSON chunks found to compile. Run extraction first or populate '{OUTPUT_CHUNKS_DIR}'.")
        exit(0)
        
    print(f"Found {len(chunk_files)} chunks. Starting vault assembly...")
    for json_file in chunk_files:
        json_path_obj = Path(json_file)
        
        # Check if the file is nested inside subdirectories of OUTPUT_CHUNKS_DIR
        try:
            rel_path = json_path_obj.relative_to(OUTPUT_CHUNKS_DIR)
            parts = rel_path.parent.parts
        except ValueError:
            parts = ()
            
        if parts:
            # The top-level subdirectory is the system/artist name
            system_name = parts[0]
        else:
            filename = json_path_obj.name
            if "chunk" in filename.lower():
                system_name = ACTIVE_SYSTEM
            else:
                cleaned_name = filename
                for part in ["main_", "_world_info", ".json"]:
                    cleaned_name = cleaned_name.replace(part, "")
                cleaned_name = cleaned_name.replace("_", " ").strip()
                system_name = cleaned_name
            
        unpack_universal_rulebook(
            json_path=str(json_path_obj), 
            target_vault_dir=RAW_VAULT_DIR, 
            system_name=system_name
        )
