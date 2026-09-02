"""Pure JSON → raw markdown unwrapper for SillyTavern-style world-info lorebooks.

Deterministic and LLM-free by design: this module imports only stdlib and
config.settings path constants. It must NEVER import get_ai_provider or any
provider engine — the raw vault phase is a no-model transformation.
"""

import json
import re
from pathlib import Path

from config import settings


def _chunks_dir(chunks_dir=None):
    """Resolve the chunk discovery root (call-time settings read keeps tests clean)."""
    return Path(chunks_dir) if chunks_dir else settings.OUTPUT_CHUNKS_DIR


def _raw_vault_dir(target_dir=None):
    return Path(target_dir) if target_dir else settings.RAW_VAULT_DIR


def parse_keys(key_val):
    """Parse key inputs of varying types into a clean list of trigger strings."""
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


def extract_entries_from_json(data):
    """Extract entry dicts from parsed JSON regardless of format structure."""
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

        candidate_entries = []
        for val in data.values():
            if isinstance(val, dict) and ("key" in val or "content" in val or "name" in val):
                candidate_entries.append(val)
        if candidate_entries:
            return candidate_entries

    return []


def build_raw_markdown_in_memory(entry, system_name):
    """Build the raw markdown buffer for one entry (pure, no LLM).

    Handles narrative entries (Speaker/Dialogue/Scene Description) and lorebook
    entries. Returns (safe_title, subfolder_name, raw_markdown).
    """
    if "Speaker" in entry or "Dialogue" in entry or "Scene Description" in entry:
        raw_name = entry.get("Speaker") or "System-Environment"
        scene_desc = entry.get("Scene Description") or entry.get("Scene_Description") or ""
        dialogue = entry.get("Dialogue") or ""
        content = f"Dialogue: {dialogue}\n\nScene Description: {scene_desc}"
        st_keys = [raw_name]

        yaml_dict = {
            "system": system_name,
            "tags": [system_name.lower(), "auto-gen", "narrative"],
            "aliases": st_keys,
            "type": "Narrative",
        }
    else:
        raw_name = entry.get("name", "Unnamed")
        content = entry.get("content", "")

        # 1. Alias extraction (SillyTavern keys -> Obsidian aliases)
        st_keys = entry.get("keys", [])
        if isinstance(st_keys, str):
            st_keys = [k.strip() for k in st_keys.split(",")]

        # 2. Dynamic YAML foundation
        yaml_dict = {
            "system": system_name,
            "tags": [system_name.lower(), "auto-gen"],
            "aliases": st_keys,
        }

    # 3. Dynamic bracket extraction [Key: Value]
    metadata_matches = re.findall(r"\[([^\]:]+):\s*([^\]]+)\]", content)
    for key, value in metadata_matches:
        clean_key = key.strip().lower().replace(" ", "_")
        yaml_dict[clean_key] = value.strip()
        pattern = rf"\[\s*{re.escape(key.strip())}\s*:\s*{re.escape(value.strip())}\s*\]"
        content = re.sub(pattern, "", content)

    # 4. Build YAML frontmatter
    yaml_lines = ["---"]
    for k, v in yaml_dict.items():
        if isinstance(v, list):
            yaml_lines.append(f"{k}: {json.dumps(v)}")
        else:
            yaml_lines.append(f"{k}: {v}")
    yaml_lines.append("---\n")
    yaml_frontmatter = "\n".join(yaml_lines)

    # 5. Subfolder routing from entry type
    subfolder_name = yaml_dict.get("type", "General_Rules")
    if isinstance(subfolder_name, list):
        subfolder_name = subfolder_name[0] if subfolder_name else "General_Rules"
    subfolder_name = str(subfolder_name).title()
    subfolder_name = re.sub(r'[\\/*?:"<>|]', "-", subfolder_name).strip()
    if not subfolder_name:
        subfolder_name = "General_Rules"

    # 6. Assemble raw markdown buffer
    raw_markdown = yaml_frontmatter + f"# {raw_name}\n\n" + content.strip()

    safe_title = re.sub(r'[\\/*?:"<>|]', "-", raw_name).strip()
    if not safe_title:
        safe_title = "Unnamed"

    return safe_title, subfolder_name, raw_markdown


def sweep_chunk_files(chunks_dir=None):
    """Discover JSON chunks and resolve each one's system name from path structure.

    A top-level subdirectory under chunks_dir names the system; bare files fall
    back to ACTIVE_SYSTEM (chunk files) or a cleaned filename. Returns a list of
    (Path, system_name) tuples.
    """
    chunks_dir = _chunks_dir(chunks_dir)
    files = []
    if chunks_dir.exists():
        for p in chunks_dir.rglob("*.json"):
            if "debug" not in p.parts:
                files.append(p)

    if not files and Path("JSON_Lorebooks").exists():
        for p in Path("JSON_Lorebooks").rglob("*.json"):
            files.append(p)

    result = []
    for p in files:
        try:
            parts = p.relative_to(chunks_dir).parent.parts
        except ValueError:
            parts = ()

        if parts:
            system_name = parts[0]
        else:
            filename = p.name
            if "chunk" in filename.lower():
                system_name = settings.ACTIVE_SYSTEM
            else:
                cleaned = filename
                for part in ["main_", "_world_info", ".json"]:
                    cleaned = cleaned.replace(part, "")
                cleaned = cleaned.replace("_", " ").strip()
                system_name = cleaned

        result.append((p, system_name))

    return result


def write_raw_vault(entries, system_name, target_dir=None):
    """Write unwrapped raw markdown entries to target_dir/{system}/{Type}/.md.

    Returns the number of notes written. Pure — never touches an LLM.
    """
    vault_root = _raw_vault_dir(target_dir)
    vault_path = vault_root / system_name
    vault_path.mkdir(parents=True, exist_ok=True)

    written = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        safe_title, subfolder_name, raw_markdown = build_raw_markdown_in_memory(entry, system_name)
        final_dir = vault_path / subfolder_name
        final_dir.mkdir(parents=True, exist_ok=True)
        out_path = final_dir / f"{safe_title}.md"
        out_path.write_text(raw_markdown, encoding="utf-8")
        written += 1

    return written