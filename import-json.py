import argparse
import json
import sys
from pathlib import Path

# Resolve absolute path to the project root directory
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

try:
    from config.settings import OUTPUT_CHUNKS_DIR
    from core.utils import LorebookEntry, LorebookLog
except ImportError as e:
    print(f"❌ System Error: Failed to import codebase modules: {e}")
    sys.exit(1)


def parse_keys(key_val):
    """
    Parses key inputs of varying types into a list of clean trigger strings.
    """
    if not key_val:
        return []
    if isinstance(key_val, list):
        return [str(k).strip() for k in key_val if str(k).strip()]
    if isinstance(key_val, str):
        for sep in [",", ";"]:
            if sep in key_val:
                return [k.strip() for k in key_val.split(sep) if k.strip()]
        return [key_val.strip()]
    return [str(key_val).strip()]


def map_sillytavern_entry(uid, entry_dict):
    """
    Map SillyTavern entry structure to LorebookEntry schema.
    """
    raw_keys = entry_dict.get('key', [])
    raw_keys_sec = entry_dict.get('keysecondary', [])
    
    combined_keys = list(set(parse_keys(raw_keys) + parse_keys(raw_keys_sec)))
    
    # Assign defaults and fallbacks
    name = entry_dict.get('name') or entry_dict.get('title') or f"Entry_{uid}"
    content = entry_dict.get('content') or entry_dict.get('description') or ''
    priority = entry_dict.get('priority', 50)
    insertion_order = entry_dict.get('insertion_order', 50)

    try:
        priority = int(priority)
    except (ValueError, TypeError):
        priority = 50

    try:
        insertion_order = int(insertion_order)
    except (ValueError, TypeError):
        insertion_order = 50

    return LorebookEntry(
        id=uid,
        name=str(name),
        keys=combined_keys,
        content=str(content),
        priority=priority,
        insertion_order=insertion_order
    )


def extract_entries_from_json(data):
    """
    Extract entries from parsed JSON data regardless of format structure.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "entries" in data:
            entries_val = data["entries"]
            if isinstance(entries_val, dict):
                return list(entries_val.values())
            if isinstance(entries_val, list):
                return entries_val
        if data and all(str(k).isdigit() for k in data.keys()):
            return list(data.values())
        
        # Check values for potential nested entry dictionaries
        candidate_entries = []
        for val in data.values():
            if isinstance(val, dict) and ('key' in val or 'content' in val or 'name' in val):
                candidate_entries.append(val)
        if candidate_entries:
            return candidate_entries
            
    return []


def process_sillytavern_json(file_path):
    """
    Process SillyTavern JSON and convert to LorebookLog format.
    """
    print(f"📦 JSON Cargo Detected: {file_path}")
    
    # 1. Read and parse external JSON file
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ❌ Error reading JSON: {e}")
        return False

    raw_entries = extract_entries_from_json(data)
    if not raw_entries:
        print("  ⚠️ No entries found in the JSON file structure.")
        return False

    print("🔍 Harmonizing Keys to Lore Matrix Standard")

    # 2. Transform entries using map_sillytavern_entry
    mapped_entries = []
    for idx, entry_dict in enumerate(raw_entries, start=1):
        if not isinstance(entry_dict, dict):
            continue
        mapped = map_sillytavern_entry(idx, entry_dict)
        mapped_entries.append(mapped)

    # 3. Wrap validated entries in LorebookLog envelope
    log_payload = LorebookLog(entries=mapped_entries)
    
    # Perform strict validation of the final model serialization
    try:
        if hasattr(LorebookLog, "model_validate"):
            validated_payload = LorebookLog.model_validate(log_payload)
            final_json = validated_payload.model_dump(by_alias=True)
        else:
            validated_payload = LorebookLog.validate(log_payload)
            final_json = validated_payload.dict(by_alias=True)
    except Exception as exc:
        print(f"  ❌ Schema validation check failed: {exc}")
        raise ValueError(f"Strict validation check failed: {exc}") from exc

    # 4. Save to output directory
    output_dir = OUTPUT_CHUNKS_DIR / "imported"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    original_filename = Path(file_path).stem
    # Handle files with double extensions like .lorebook.json
    if original_filename.endswith(".lorebook"):
        original_filename = original_filename[:-9]
        
    output_file = output_dir / f"imported_chunk_{original_filename}.json"
    
    with open(output_file, "w", encoding="utf-8") as out_f:
        json.dump(final_json, out_f, indent=4, ensure_ascii=False)

    print(f"✅ Fast-Lane Staging Complete: {output_file}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Ingest Pre-formatted SillyTavern JSON Lorebooks")
    parser.add_argument("input_file", nargs="?", default=None, help="Path to SillyTavern JSON lorebook file")
    args = parser.parse_args()

    INPUT_DIR = BASE_DIR / "input_json"
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.input_file:
        success = process_sillytavern_json(args.input_file)
        sys.exit(0 if success else 1)
    else:
        # Sweep the input_json directory
        json_files = sorted(list(INPUT_DIR.glob("*.json")))
        if not json_files:
            print(f"📭 Empty directory state: No JSON files found in {INPUT_DIR}/")
            sys.exit(0)
            
        success_count = 0
        for jf in json_files:
            if process_sillytavern_json(jf):
                success_count += 1
        print(f"\n🎉 Batch Ingestion complete: processed {success_count}/{len(json_files)} successfully.")


if __name__ == "__main__":
    main()
