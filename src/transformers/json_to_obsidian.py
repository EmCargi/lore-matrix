import hashlib
import json
import os
import random
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

# Thread-safe printing + RateLimiter live in core/concurrency.py (set up after the core import below).


class CompilationCache:
    """
    Thread-safe compilation cache based on content hashing.
    """
    def __init__(self, cache_file_path):
        self.cache_file_path = Path(cache_file_path)
        self.lock = threading.Lock()
        self.cache = {}
        self.load()

    def load(self):
        with self.lock:
            if self.cache_file_path.exists():
                try:
                    with open(self.cache_file_path, encoding="utf-8") as f:
                        self.cache = json.load(f)
                except Exception as e:
                    print(f"  ⚠️ Warning: Failed to load compilation cache: {e}")
                    self.cache = {}

    def save(self):
        try:
            # Ensure parent dir exists
            self.cache_file_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write to cache file
            temp_path = self.cache_file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=4)
            os.replace(temp_path, self.cache_file_path)
        except Exception as e:
            print(f"  ⚠️ Warning: Failed to save compilation cache: {e}")

    def get_hash(self, content):
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def should_skip(self, target_path, content):
        target_path_str = str(Path(target_path).resolve())
        # File must exist on disk
        if not os.path.exists(target_path_str):
            return False
        
        current_hash = self.get_hash(content)
        with self.lock:
            cached_hash = self.cache.get(target_path_str)
            return cached_hash == current_hash

    def update(self, target_path, content):
        target_path_str = str(Path(target_path).resolve())
        current_hash = self.get_hash(content)
        with self.lock:
            self.cache[target_path_str] = current_hash
            self.save()

# Ensure project root is in sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import config settings
from config.settings import (
    ACTIVE_SYSTEM,
    BASE_DIR,
    COMPILED_VAULT_DIR,
    COMPILER_SYSTEM_PROMPT,
    OUTPUT_CHUNKS_DIR,
    get_ai_provider,
)
from core.concurrency import RateLimiter, make_safe_print
from core.utils import LorebookEntry, LorebookLog, NarrativeLog

# Thread-safe printing to prevent stdout interleaving
print = make_safe_print()

# Vault output root directory inside project
VAULT_ROOT_DIR = COMPILED_VAULT_DIR

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


def build_raw_markdown_in_memory(entry, system_name):
    """
    Extracts keys, parses brackets, creates YAML frontmatter,
    and constructs a raw markdown buffer fully in-memory.
    """
    # Check if this is a Narrative entry (Dialogue, Speaker, Scene Description)
    if 'Speaker' in entry or 'Dialogue' in entry or 'Scene Description' in entry:
        raw_name = entry.get('Speaker') or 'System-Environment'
        # Backward-compat: pre-v3.0 vision chunks wrote the underscore form.
        # Canonical is the space-alias; fall back defensively so legacy data still compiles.
        scene_desc = entry.get('Scene Description') or entry.get('Scene_Description') or ''
        dialogue = entry.get('Dialogue') or ''
        content = f"Dialogue: {dialogue}\n\nScene Description: {scene_desc}"
        st_keys = [raw_name]
        
        # Build YAML dict
        yaml_dict = {
            "system": system_name,
            "tags": [system_name.lower(), "auto-gen", "narrative"],
            "aliases": st_keys,
            "type": "Narrative"
        }
    else:
        raw_name = entry.get('name', 'Unnamed')
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

    # 5. Determine subfolder name based on entry type
    subfolder_name = yaml_dict.get('type', 'General_Rules')
    if isinstance(subfolder_name, list):
        subfolder_name = subfolder_name[0] if subfolder_name else 'General_Rules'
    subfolder_name = str(subfolder_name).title()
    subfolder_name = re.sub(r'[\\/*?:"<>|]', "-", subfolder_name).strip()
    if not subfolder_name:
        subfolder_name = 'General_Rules'
    
    # Compile the final raw markdown buffer
    raw_markdown = yaml_frontmatter + f"# {raw_name}\n\n" + content.strip()
    
    safe_title = re.sub(r'[\\/*?:"<>|]', "-", raw_name).strip()
    if not safe_title:
        safe_title = "Unnamed"
        
    return safe_title, subfolder_name, raw_markdown


def atomic_write(content, target_path):
    """
    Writes data atomically to prevent partial run data corruption.
    """
    target_dir = os.path.dirname(target_path)
    os.makedirs(target_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=target_dir, delete=False, encoding='utf-8') as tf:
        tf.write(content)
        temp_name = tf.name
    try:
        os.replace(temp_name, target_path)
    except Exception as e:
        if os.path.exists(temp_name):
            os.remove(temp_name)
        raise e


def validate_yaml_frontmatter(content):
    """
    Validates that the content starts with a valid YAML frontmatter block.
    Returns (is_valid, error_message).
    """
    if not content.startswith("---"):
        return False, "Does not start with '---'"
    
    parts = content.split("---", 2)
    if len(parts) < 3:
        return False, "Missing closing '---' for frontmatter"
    
    frontmatter = parts[1]
    lines = frontmatter.splitlines()
    for line_num, line in enumerate(lines, start=2):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        # Check if line contains a colon separator
        if ":" not in line:
            return False, f"Line {line_num}: Missing ':' separator in YAML key-value pair"
        
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        
        if not key:
            return False, f"Line {line_num}: Empty key in YAML frontmatter"
        
        # Basic validation of value format
        # If it starts with [ and ends with ], check if it is a valid JSON array
        if val.startswith("[") and val.endswith("]"):
            try:
                # Python's json.loads can parse valid YAML/JSON lists
                import json
                json.loads(val)
            except Exception as je:
                return False, f"Line {line_num}: Invalid list format in value: {je}"
        # If it starts with " or ', check that quotes are matched
        elif val.startswith('"') or val.startswith("'"):
            quote = val[0]
            if len(val) < 2 or not val.endswith(quote):
                return False, f"Line {line_num}: Mismatched quotes in value"
            
    return True, ""


def auto_link_markdown(content, name_to_title, current_title):
    """
    Scans the markdown content (below frontmatter) and wraps known terms in wiki links.
    """
    if not name_to_title:
        return content
        
    # Split content into frontmatter and body
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = "---" + parts[1] + "---"
            body = parts[2]
        else:
            frontmatter = ""
            body = content
    else:
        frontmatter = ""
        body = content
        
    sorted_keys = sorted(name_to_title.keys(), key=len, reverse=True)
    # Filter out empty or extremely short keys (e.g. less than 3 chars to avoid false positives)
    sorted_keys = [k for k in sorted_keys if len(k) >= 3]
    if not sorted_keys:
        return content
        
    escaped_names = [re.escape(name) for name in sorted_keys]
    names_pattern = r'\b(' + '|'.join(escaped_names) + r')\b'
    pattern = re.compile(
        r'(?s)(```.*?```|`.*?`|\[\[.*?\]\]|\[.*?\]\(.*?\))|' + names_pattern,
        re.IGNORECASE
    )
    
    def replace_match(match):
        if match.group(1):
            return match.group(1)
        
        matched_text = match.group(2)
        matched_lower = matched_text.lower()
        
        target_title = name_to_title.get(matched_lower)
        if not target_title:
            return matched_text
            
        if target_title.lower() == current_title.lower():
            return matched_text
            
        if matched_text.lower() == target_title.lower():
            return f"[[{target_title}]]"
        else:
            return f"[[{target_title}|{matched_text}]]"
            
    linked_body = pattern.sub(replace_match, body)
    return frontmatter + linked_body


def compile_and_vault_note(safe_title, subfolder_name, raw_content, system_name, active_ai, compilation_cache=None, name_to_title=None):
    """
    Passes raw markdown to the LLM compiler, cleans the returned response,
    and writes it directly to the target vault directory.
    """
    target_vault_path = VAULT_ROOT_DIR / system_name / subfolder_name / f"{safe_title}.md"
    
    # Check cache and disk existence for skipping
    if compilation_cache and compilation_cache.should_skip(target_vault_path, raw_content):
        print(f"  ⏭️ Skipping already compiled vault file: {safe_title}.md (hash matches)")
        return True
    elif not compilation_cache and target_vault_path.exists():
        # Fallback if no cache helper passed
        print(f"  ⏭️ Skipping already compiled vault file: {safe_title}.md")
        return True

    for attempt in range(3):
        try:
            # Pass the in-memory raw buffer directly to compiler
            compiled_content = active_ai.generate(COMPILER_SYSTEM_PROMPT, raw_content)
            
            # Clean formatting fences and model remarks
            if "---" in compiled_content:
                compiled_content = "---" + compiled_content.split("---", 1)[1]
                
            # Validate YAML frontmatter
            is_valid, err_msg = validate_yaml_frontmatter(compiled_content)
            if not is_valid:
                raise ValueError(f"Invalid YAML frontmatter: {err_msg}")
                
            # Auto-link terms within the note
            if name_to_title:
                compiled_content = auto_link_markdown(compiled_content, name_to_title, safe_title)
                
            # Perform direct atomic write to target vault folder
            atomic_write(compiled_content, str(target_vault_path))
            if compilation_cache:
                compilation_cache.update(target_vault_path, raw_content)
            print(f"  ✅ Forged successfully: {safe_title}.md")
            return True
            
        except Exception as e:
            if attempt < 2:
                backoff = (2 ** attempt) + random.uniform(0, 1)
                print(f"  ⚠️ Attempt {attempt + 1}/3 failed for {safe_title}: {e}. Retrying in {backoff:.2f}s...")
                time.sleep(backoff)
            else:
                print(f"  ❌ Failed compiling {safe_title} after 3 attempts. Last error: {e}")
                try:
                    error_dir = OUTPUT_CHUNKS_DIR / "errors"
                    error_dir.mkdir(parents=True, exist_ok=True)
                    error_file = error_dir / f"error_{system_name}_{subfolder_name}_{safe_title}.txt"
                    with open(error_file, "w", encoding="utf-8") as err_f:
                        err_f.write(f"ERROR: {e}\n\nRAW CONTENT:\n{raw_content}")
                    print(f"  ⚠️ Saved failure details to {error_file}")
                except Exception as log_err:
                    print(f"  ⚠️ Warning: Failed to write error log: {log_err}")
                return False
                
    return False


def process_single_entry(entry, system_name, active_ai, rate_limiter=None, compilation_cache=None, name_to_title=None):
    """
    Worker function to compile and vault a single entry.
    """
    if rate_limiter:
        rate_limiter.wait()
    else:
        # Brief pause to prevent overheating if no custom rate limit is set
        time.sleep(random.uniform(1.5, 3.0))

    try:
        safe_title, subfolder, raw_md = build_raw_markdown_in_memory(entry, system_name)
        success = compile_and_vault_note(
            safe_title=safe_title,
            subfolder_name=subfolder,
            raw_content=raw_md,
            system_name=system_name,
            active_ai=active_ai,
            compilation_cache=compilation_cache,
            name_to_title=name_to_title
        )
        return success
    except Exception as e:
        print(f"  ❌ Error preparing entry '{entry.get('name', entry.get('Speaker', 'Unnamed'))}': {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Unified Obsidian Assembly Forge")
    parser.add_argument("--engine", type=str, choices=["local", "gemini", "featherless"], default=None, help="AI provider engine to use")
    parser.add_argument("--model", type=str, default=None, help="Model name override")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent worker threads (default: 1)")
    parser.add_argument("--rate-limit", type=float, default=0.0, help="Delay in seconds between LLM calls per worker (default: 0.0)")
    args = parser.parse_args()
    
    workers = args.workers
    rate_limit = args.rate_limit
    
    active_ai = get_ai_provider(engine_name=args.engine, model_name=args.model)
    print(f"Ignited Unified Obsidian Vault Compiler using: {active_ai.__class__.__name__} ({active_ai.model_name})...\n")
    if workers > 1:
        print(f"Concurrency configured: {workers} worker threads.\n")
    if rate_limit > 0:
        print(f"Rate limiting active: {rate_limit}s delay between LLM calls.\n")
    
    # 1. Gather JSON Chunks
    chunk_files = []
    if OUTPUT_CHUNKS_DIR.exists():
        for p in OUTPUT_CHUNKS_DIR.rglob("*.json"):
            if "debug" not in p.parts:
                chunk_files.append(p)
                
    if not chunk_files and os.path.exists("JSON_Lorebooks"):
        for p in Path("JSON_Lorebooks").rglob("*.json"):
            chunk_files.append(p)
            
    if not chunk_files:
        print(f"📭 No JSON chunks found to compile. Populate '{OUTPUT_CHUNKS_DIR}' or extraction paths first.")
        sys.exit(0)
        
    print(f"Found {len(chunk_files)} JSON source chunks. Unpacking & compiling directly to Obsidian vault...")
    
    # 2. Build Name-to-Title Index for Wiki Link Extraction
    system_indexes = {}
    for json_file in chunk_files:
        json_path_obj = Path(json_file)
        
        # Determine system_name
        try:
            rel_path = json_path_obj.relative_to(OUTPUT_CHUNKS_DIR)
            parts = rel_path.parent.parts
        except ValueError:
            parts = ()
            
        if parts:
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
                
        system_indexes.setdefault(system_name, {})
        name_to_title = system_indexes[system_name]
        
        try:
            with open(json_file, encoding='utf-8') as f:
                data = json.load(f)
                entries = extract_entries_from_json(data)
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    
                    raw_name = entry.get('Speaker') or entry.get('name') or entry.get('title')
                    if not raw_name:
                        continue
                    
                    safe_title = re.sub(r'[\\/*?:"<>|]', "-", raw_name).strip()
                    if not safe_title:
                        safe_title = "Unnamed"
                        
                    name_to_title[raw_name.lower()] = safe_title
                    name_to_title[safe_title.lower()] = safe_title
                    
                    st_keys = entry.get('keys', entry.get('key', []))
                    if isinstance(st_keys, str):
                        st_keys = [k.strip() for k in st_keys.split(',') if k.strip()]
                    elif isinstance(st_keys, list):
                        st_keys = [str(k).strip() for k in st_keys if str(k).strip()]
                    else:
                        st_keys = []
                        
                    for key in st_keys:
                        name_to_title[key.lower()] = safe_title
        except Exception:
            pass
    
    total_compiled = 0
    total_failed = 0
    
    for json_file in chunk_files:
        json_path_obj = Path(json_file)
        
        # Determine system_name
        try:
            rel_path = json_path_obj.relative_to(OUTPUT_CHUNKS_DIR)
            parts = rel_path.parent.parts
        except ValueError:
            parts = ()
            
        if parts:
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
                
        print(f"\n📂 Processing chunk file: {json_path_obj.name} (RPG System: {system_name})")
        
        try:
            with open(json_path_obj, encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as jde:
            print(f"  ⚠️ Skipping {json_path_obj.name} - Invalid JSON syntax: {jde}")
            total_failed += 1
            continue
        except Exception as je:
            print(f"  ❌ Failed to parse JSON file {json_path_obj.name}: {je}")
            total_failed += 1
            continue

        raw_entries = extract_entries_from_json(data)
        if not raw_entries:
            print(f"  ⚠️ No entries found in chunk file {json_path_obj.name}.")
            continue

        is_lorebook = False
        is_narrative = False
        if raw_entries and isinstance(raw_entries[0], dict):
            first = raw_entries[0]
            if 'content' in first or 'keys' in first or 'name' in first:
                is_lorebook = True
            elif 'Dialogue' in first or 'Scene Description' in first or 'Speaker' in first:
                is_narrative = True

        validated_entries = []
        try:
            if is_lorebook:
                mapped_entries = []
                for idx, entry_dict in enumerate(raw_entries, start=1):
                    if not isinstance(entry_dict, dict):
                        continue
                    mapped = map_sillytavern_entry(idx, entry_dict)
                    mapped_entries.append(mapped)
                
                log_payload = LorebookLog(entries=mapped_entries)
                if hasattr(LorebookLog, "model_validate"):
                    validated_payload = LorebookLog.model_validate(log_payload)
                    final_json = validated_payload.model_dump(by_alias=True)
                else:
                    validated_payload = LorebookLog.validate(log_payload)
                    final_json = validated_payload.dict(by_alias=True)
                validated_entries = final_json.get('entries', [])
                print("  🔍 Validated as LorebookLog (Pydantic schema passed).")

            elif is_narrative:
                log_payload = NarrativeLog(entries=raw_entries)
                if hasattr(NarrativeLog, "model_validate"):
                    validated_payload = NarrativeLog.model_validate(log_payload)
                    final_json = validated_payload.model_dump(by_alias=True)
                else:
                    validated_payload = NarrativeLog.validate(log_payload)
                    final_json = validated_payload.dict(by_alias=True)
                validated_entries = final_json.get('entries', [])
                print("  🔍 Validated as NarrativeLog (Pydantic schema passed).")

            else:
                validated_entries = raw_entries
                print("  ℹ️ Processed with generic fallback validation.")
        except Exception as exc:
            print(f"  ❌ Schema validation check failed for {json_path_obj.name}: {exc}")
            total_failed += 1
            continue
            
        name_to_title = system_indexes.get(system_name, {})
        rate_limiter = RateLimiter(rate_limit) if rate_limit > 0 else None
        compilation_cache = CompilationCache(BASE_DIR / "cache" / "obsidian_compilation_cache.json")
        
        if workers > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        process_single_entry,
                        entry, system_name, active_ai, rate_limiter, compilation_cache, name_to_title
                    ): entry for entry in validated_entries
                }
                for future in as_completed(futures):
                    try:
                        success = future.result()
                        if success:
                            total_compiled += 1
                        else:
                            total_failed += 1
                    except Exception as exc:
                        entry = futures[future]
                        name = entry.get('name', entry.get('Speaker', 'Unnamed'))
                        print(f"  ❌ Entry '{name}' generated an exception: {exc}")
                        total_failed += 1
        else:
            for entry in validated_entries:
                success = process_single_entry(entry, system_name, active_ai, rate_limiter, compilation_cache, name_to_title)
                if success:
                    total_compiled += 1
                else:
                    total_failed += 1
                
        # Brief pause between chunks to keep processor cool
        time.sleep(1.0)
        
    print(f"\n🎉 Direct Obsidian Assembly Complete. Total successfully compiled: {total_compiled}, failed: {total_failed}.")

if __name__ == "__main__":
    main()
