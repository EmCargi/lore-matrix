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
    BASE_DIR,
    COMPILED_VAULT_DIR,
    COMPILER_SYSTEM_PROMPT,
    OUTPUT_CHUNKS_DIR,
    RAW_VAULT_DIR,
    get_ai_provider,
)
from core.concurrency import RateLimiter, make_safe_print
from core.raw_vault_builder import (
    build_raw_markdown_in_memory,
    extract_entries_from_json,
    parse_keys,
    sweep_chunk_files,
    write_raw_vault,
)
from core.utils import LorebookEntry, LorebookLog, NarrativeLog

# Thread-safe printing to prevent stdout interleaving
print = make_safe_print()

# Vault output root directory inside project
VAULT_ROOT_DIR = COMPILED_VAULT_DIR

def map_sillytavern_entry(uid, entry_dict):
    """
    Map SillyTavern entry structure to LorebookEntry schema.
    """
    raw_keys = entry_dict.get('key') or entry_dict.get('keys') or []
    raw_keys_sec = entry_dict.get('keysecondary', [])

    # Order-preserving dedupe (set() would scramble alias order non-deterministically)
    combined_keys = list(dict.fromkeys(parse_keys(raw_keys) + parse_keys(raw_keys_sec)))
    
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


def build_name_to_title_index(chunks):
    """Build per-system name→title indexes for wiki-link extraction (one-shot)."""
    system_indexes = {}
    for json_file, system_name in chunks:
        system_indexes.setdefault(system_name, {})
        name_to_title = system_indexes[system_name]

        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
                entries = extract_entries_from_json(data)
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue

                    raw_name = entry.get("Speaker") or entry.get("name") or entry.get("title")
                    if not raw_name:
                        continue

                    safe_title = re.sub(r'[\\/*?:"<>|]', "-", raw_name).strip() or "Unnamed"
                    name_to_title[raw_name.lower()] = safe_title
                    name_to_title[safe_title.lower()] = safe_title

                    st_keys = entry.get("keys", entry.get("key", []))
                    if isinstance(st_keys, str):
                        st_keys = [k.strip() for k in st_keys.split(",") if k.strip()]
                    elif isinstance(st_keys, list):
                        st_keys = [str(k).strip() for k in st_keys if str(k).strip()]
                    else:
                        st_keys = []

                    for key in st_keys:
                        name_to_title[key.lower()] = safe_title
        except Exception:
            pass

    return system_indexes


def build_raw_vault_index():
    """Build name→title index from the raw vault for compile-phase auto-linking."""
    name_to_title = {}
    for raw_path in RAW_VAULT_DIR.rglob("*.md"):
        safe_title = raw_path.stem
        name_to_title[safe_title.lower()] = safe_title

        try:
            content = raw_path.read_text(encoding="utf-8")
        except OSError:
            continue

        if not content.startswith("---"):
            continue
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue

        for line in parts[1].splitlines():
            line = line.strip()
            if not line.startswith("aliases:"):
                continue
            alias_str = line.split(":", 1)[1].strip()
            try:
                aliases = json.loads(alias_str)
            except json.JSONDecodeError:
                aliases = []
            for alias in aliases:
                name_to_title[str(alias).lower()] = safe_title

    return name_to_title


def run_raw_phase():
    """Sweep JSON chunks → raw markdown in RAW_VAULT_DIR. No LLM, ever."""
    chunks = sweep_chunk_files()
    if not chunks:
        print(f"📭 No JSON chunks found. Populate '{OUTPUT_CHUNKS_DIR}' or extraction paths first.")
        sys.exit(0)

    total = 0
    for json_file, system_name in chunks:
        json_path_obj = Path(json_file)
        try:
            with open(json_path_obj, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠️ Skipping {json_path_obj.name} - {e}")
            continue

        entries = extract_entries_from_json(data)
        if not entries:
            print(f"  ⚠️ No entries found in chunk file {json_path_obj.name}.")
            continue

        written = write_raw_vault(entries, system_name, RAW_VAULT_DIR)
        total += written
        print(f"  ✅ {written} raw notes from {json_path_obj.name} → {RAW_VAULT_DIR / system_name}")

    print(f"\n🎉 Raw vault assembled: {total} notes in {RAW_VAULT_DIR}. No LLM touched.")


def run_compile_phase(active_ai, args):
    """Compile existing RAW_VAULT_DIR markdown → COMPILED_VAULT_DIR (LLM)."""
    raw_notes = sorted(RAW_VAULT_DIR.rglob("*.md"))
    print(f"🔨 Compiling {len(raw_notes)} raw notes from {RAW_VAULT_DIR}...")

    compilation_cache = CompilationCache(BASE_DIR / "cache" / "obsidian_compilation_cache.json")
    name_to_title = build_raw_vault_index()
    total_compiled = 0
    total_failed = 0

    for raw_path in raw_notes:
        rel = raw_path.relative_to(RAW_VAULT_DIR)
        system_name = rel.parts[0]
        subfolder = rel.parts[1] if len(rel.parts) > 1 else "General_Rules"
        safe_title = raw_path.stem
        raw_content = raw_path.read_text(encoding="utf-8")

        success = compile_and_vault_note(
            safe_title=safe_title,
            subfolder_name=subfolder,
            raw_content=raw_content,
            system_name=system_name,
            active_ai=active_ai,
            compilation_cache=compilation_cache,
            name_to_title=name_to_title,
        )
        if success:
            total_compiled += 1
        else:
            total_failed += 1

    print(f"\n🎉 Compile complete. Compiled: {total_compiled}, failed: {total_failed}.")


def run_one_shot(active_ai, args):
    """One-shot: JSON → in-memory raw → compile → COMPILED_VAULT_DIR."""
    workers = args.workers
    rate_limit = args.rate_limit

    chunks = sweep_chunk_files()
    if not chunks:
        print(f"📭 No JSON chunks found. Populate '{OUTPUT_CHUNKS_DIR}' or extraction paths first.")
        sys.exit(0)

    print(f"Found {len(chunks)} JSON source chunks. Unpacking & compiling directly to Obsidian vault...")

    system_indexes = build_name_to_title_index(chunks)

    total_compiled = 0
    total_failed = 0

    for json_file, system_name in chunks:
        json_path_obj = Path(json_file)
        print(f"\n📂 Processing chunk file: {json_path_obj.name} (RPG System: {system_name})")

        try:
            with open(json_path_obj, encoding="utf-8") as f:
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
            if "content" in first or "keys" in first or "name" in first:
                is_lorebook = True
            elif "Dialogue" in first or "Scene Description" in first or "Speaker" in first:
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
                validated_entries = final_json.get("entries", [])
                print("  🔍 Validated as LorebookLog (Pydantic schema passed).")

            elif is_narrative:
                log_payload = NarrativeLog(entries=raw_entries)
                if hasattr(NarrativeLog, "model_validate"):
                    validated_payload = NarrativeLog.model_validate(log_payload)
                    final_json = validated_payload.model_dump(by_alias=True)
                else:
                    validated_payload = NarrativeLog.validate(log_payload)
                    final_json = validated_payload.dict(by_alias=True)
                validated_entries = final_json.get("entries", [])
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
                        name = entry.get("name", entry.get("Speaker", "Unnamed"))
                        print(f"  ❌ Entry '{name}' generated an exception: {exc}")
                        total_failed += 1
        else:
            for entry in validated_entries:
                success = process_single_entry(
                    entry, system_name, active_ai, rate_limiter, compilation_cache, name_to_title
                )
                if success:
                    total_compiled += 1
                else:
                    total_failed += 1

        time.sleep(1.0)

    print(f"\n🎉 Direct Obsidian Assembly Complete. Total successfully compiled: {total_compiled}, failed: {total_failed}.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Unified Obsidian Assembly Forge")
    parser.add_argument("--engine", type=str, choices=["local", "gemini", "featherless"], default=None, help="AI provider engine to use")
    parser.add_argument("--model", type=str, default=None, help="Model name override")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent worker threads (default: 1)")
    parser.add_argument("--rate-limit", type=float, default=0.0, help="Delay in seconds between LLM calls per worker (default: 0.0)")
    parser.add_argument("--phase", type=str, choices=["raw", "compile"], default=None,
                        help="raw: JSON chunks → RAW_VAULT_DIR (no LLM). compile: RAW_VAULT_DIR → COMPILED_VAULT_DIR. Omit for one-shot.")
    args = parser.parse_args()

    # --phase raw is pure: never construct a provider
    if args.phase == "raw":
        run_raw_phase()
        return

    # --phase compile bails before touching a provider when there's nothing to compile
    if args.phase == "compile" and not any(RAW_VAULT_DIR.rglob("*.md")):
        print(f"⚠️ No raw notes found in {RAW_VAULT_DIR}. Run with --phase raw first.")
        sys.exit(0)

    active_ai = get_ai_provider(engine_name=args.engine, model_name=args.model)
    print(f"Ignited Unified Obsidian Vault Compiler using: {active_ai.__class__.__name__} ({active_ai.model_name})...\n")
    if args.workers > 1:
        print(f"Concurrency configured: {args.workers} worker threads.\n")
    if args.rate_limit > 0:
        print(f"Rate limiting active: {args.rate_limit}s delay between LLM calls.\n")

    if args.phase == "compile":
        run_compile_phase(active_ai, args)
    else:
        run_one_shot(active_ai, args)


if __name__ == "__main__":
    main()
