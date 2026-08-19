#!/usr/bin/env python3
"""Convert MonsterProfile JSONs → Markdown stat blocks (Weebly-page style).
Stratum is derived from the target list, not the LLM output."""

import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "output" / "json_staging" / "monsters"
OUTPUT_DIR = BASE_DIR / "output" / "monster_markdown"
TARGETS_FILE = BASE_DIR / "monster_targets.txt"


def parse_strata():
    """Parse monster_targets.txt to get stratum assignments.
    Targets are grouped by # === Stratum Name === comments."""
    strata = {}
    current = "Unknown"
    with open(TARGETS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# ===") and "Stratum" in line:
                current = line.replace("#", "").replace("===", "").strip()
            elif "|" in line:
                name = line.split("|")[0].strip()
                strata[name] = current
    return strata


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>| ]', "_", name).strip("_")


def monster_json_to_md(json_path, output_root, strata_map):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    name = data.get("Name", "Unknown")

    # Match by filename stem → target name (filenames come from target list)
    stem = json_path.stem  # e.g., "monster_Slime" → "Slime"
    target_key = stem.replace("monster_", "").replace("_", " ")
    stratum = strata_map.get(target_key, "Unknown")
    if stratum == "Unknown":
        # Fuzzy fallback: try matching the JSON Name against target names
        for tname, s in strata_map.items():
            if _slug(tname) in _slug(name) or _slug(name) in _slug(tname):
                stratum = s
                break

    safe_name = sanitize_filename(name)
    strata_dir = output_root / stratum.replace(" ", "_")
    strata_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"# {name}")
    lines.append("")

    flavor = data.get("FlavorText", "")
    if flavor:
        lines.append("## Tamer's Memo")
        lines.append("")
        for para in flavor.split("\n"):
            para = para.strip()
            if para:
                lines.append(f">{para}")
                lines.append("")
        lines.append("")

    abilities = data.get("Abilities", [])
    if abilities:
        lines.append("## Abilities")
        lines.append("")
        lines.append("| LV | Skill | Effect |")
        lines.append("|---|---|---|")
        for a in abilities:
            lv = a.get("Level", "?")
            skill = a.get("Skill", "").replace("|", "\\|")
            effect = a.get("Effect", "").replace("|", "\\|")
            lines.append(f"| {lv} | {skill} | {effect} |")
        lines.append("")

    hp = data.get("MaxHP", "?")
    mp = data.get("MaxMP", "?")
    exp = data.get("Experience", "?")
    gold = data.get("Gold", "?")
    lines.append("## Other Information")
    lines.append("")
    lines.append("| Stat | Value |")
    lines.append("|---|---|")
    lines.append(f"| HP | {hp} |")
    lines.append(f"| MP | {mp} |")
    lines.append(f"| Experience | {exp} |")
    lines.append(f"| Dropped Gold | {gold} |")
    lines.append("")

    elem = data.get("ElementalResistances", {})
    if elem:
        lines.append("## Elemental Resistances")
        lines.append("")
        lines.append("| Element | Resistance |")
        lines.append("|---|---|")
        for element in ["Slash", "Pierce", "Blunt", "Fire", "Ice",
                          "Shock", "Wind", "Holy", "Dark"]:
            val = elem.get(element, 0)
            sign = "+" if val > 0 else ""
            lines.append(f"| {element} | {sign}{val}% |")
        lines.append("")

    status = data.get("StatusResistances", {})
    if status:
        lines.append("## Status Resistances")
        lines.append("")
        lines.append("| Status | Resistance |")
        lines.append("|---|---|")
        for s in ["KO", "Poison", "Charm", "Stun", "Blind",
                     "Silence", "Paralysis", "Sleep", "Confuse"]:
            val = status.get(s, 0)
            sign = "+" if val > 0 else ""
            lines.append(f"| {s} | {sign}{val}% |")
        lines.append("")

    outpath = strata_dir / f"{safe_name}.md"
    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return outpath, stratum


def _slug(s):
    return s.lower().replace(" ", "").replace("-", "").replace("'", "")


if __name__ == "__main__":
    strata_map = parse_strata()
    print(f"Loaded {len(strata_map)} targets with stratum assignments\n")

    if not INPUT_DIR.exists():
        print(f"  No input directory at {INPUT_DIR}")
        exit(1)

    # Clean old output
    import shutil
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    json_files = sorted(INPUT_DIR.glob("monster_*.json"))
    print(f"Converting {len(json_files)} monster profiles to markdown...\n")

    counts = {}
    for jf in json_files:
        try:
            outpath, stratum = monster_json_to_md(jf, OUTPUT_DIR, strata_map)
            counts[stratum] = counts.get(stratum, 0) + 1
            print(f"  {stratum:20s} {outpath.name}")
        except Exception as e:
            print(f"  FAILED {jf.name}: {e}")

    print(f"\nDone. Output: {OUTPUT_DIR}/")
    for s, c in sorted(counts.items()):
        print(f"  {s}: {c} monsters")
