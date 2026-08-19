#!/usr/bin/env python3
"""
Lore Matrix — SillyTavern JSONL to Prose Converter
Converts a SillyTavern roleplay export (.jsonl) into prose (.txt)
that the narrative structure extractor can ingest.
"""

import argparse
import json
import sys
from pathlib import Path

# Path agnosticism setup
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name != "lore-matrix" else SCRIPT_DIR
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import BASE_DIR


def resolve_path(path_str: str) -> Path:
    """Resolve a path relative to BASE_DIR if not already absolute."""
    p = Path(path_str)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


def convert_jsonl_to_prose(input_path: Path, output_path: Path, include_user: bool = True) -> dict:
    """Convert a SillyTavern JSONL file to prose format.

    Returns stats about the conversion.
    """
    lines = input_path.read_text(encoding="utf-8-sig").strip().split("\n")

    if not lines:
        raise ValueError("Empty file")

    # 1. Parse metadata (first line)
    try:
        metadata = json.loads(lines[0])
    except json.JSONDecodeError:
        raise ValueError(f"First line is not valid JSON metadata: {lines[0][:100]}")

    character_name = metadata.get("character_name", "Character")
    user_name = metadata.get("user_name", "User")

    # 2. Parse messages
    messages = []
    for i, line in enumerate(lines[1:], 2):
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("is_system", False):
            continue
        messages.append(msg)

    # 3. Convert to prose
    paragraphs = []
    for msg in messages:
        name = msg.get("name", "Unknown")
        is_user = msg.get("is_user", False)
        text = msg.get("mes", "").strip()

        if not text:
            continue

        if is_user:
            if not include_user:
                continue
            speaker = user_name if user_name != "unused" else name
        else:
            speaker = character_name if character_name != "unused" and name == character_name else name

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        paragraphs.append(f"{speaker}:\n{text}")

    prose = "\n\n".join(paragraphs)

    # 4. Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prose, encoding="utf-8")

    char_msgs = sum(1 for m in messages if not m.get("is_user") and not m.get("is_system"))
    user_msgs = sum(1 for m in messages if m.get("is_user"))

    return {
        "total_messages": len(messages),
        "character_messages": char_msgs,
        "user_messages": user_msgs,
        "paragraphs": len(paragraphs),
        "chars": len(prose),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Convert SillyTavern JSONL to prose for narrative extraction"
    )
    parser.add_argument("--input", required=True, help="Path to .jsonl file")
    parser.add_argument("--output", default=None, help="Output .txt path (default: <input-stem>.txt)")
    parser.add_argument(
        "--character-only",
        action="store_true",
        help="Only include the AI character's messages (skip user messages)",
    )
    args = parser.parse_args()

    input_path = resolve_path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    out_name = args.output or f"{input_path.stem}.txt"
    out_dir = BASE_DIR / "output" / "json_staging" / "converted"
    out_path = out_dir / out_name

    print(f"Converting: {input_path}")
    stats = convert_jsonl_to_prose(input_path, out_path, include_user=not args.character_only)

    print(f"\n{'=' * 55}")
    print(f"  Conversion complete")
    print(f"{'=' * 55}")
    print(f"  Messages parsed: {stats['total_messages']}")
    print(f"  Character msgs: {stats['character_messages']}")
    print(f"  User msgs: {stats['user_messages']}")
    print(f"  Paragraphs: {stats['paragraphs']}")
    print(f"  Output chars: {stats['chars']}")
    print(f"{'=' * 55}")
    print(f"  Output: {out_path}")
    print(f"\n  Run: python3 extract-narrative.py --input {out_path}")


if __name__ == "__main__":
    main()
