#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Path agnosticism: resolve everything relative to this script's directory
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from config.settings import INPUT_GAME_TEXT_DIR, OUTPUT_CHUNKS_DIR
except ImportError:
    # Fallbacks in case config settings fail or import fails
    INPUT_GAME_TEXT_DIR = SCRIPT_DIR / "input_game_text"
    OUTPUT_CHUNKS_DIR = SCRIPT_DIR / "output" / "json_staging"

console = Console()

def strip_outer_quotes(text):
    text = text.strip()
    while text and (text[0] in ('"', "'") or text[-1] in ('"', "'")):
        if text[0] in ('"', "'"):
            text = text[1:].strip()
        if text and text[-1] in ('"', "'"):
            text = text[:-1].strip()
    return text

def parse_game_text_file(file_path):
    """
    Parses a game dialogue raw file and returns a dictionary of parsed blocks.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print_error_wall(f"Failed to read file '{file_path}': {e}")
        return None

    coord_pattern = re.compile(r'<\|([^<>\n|]+(?:\|[^<>\n|]+)*)\|>')
    matches = list(coord_pattern.finditer(content))
    
    if not matches:
        return {}

    parsed_blocks = {}
    for i, match in enumerate(matches):
        try:
            components = match.group(1).split('|')
            composite_key = "-".join(components)
            
            c1 = components[0] if len(components) > 0 else ""
            c2 = components[1] if len(components) > 1 else ""
            c3 = components[2] if len(components) > 2 else ""
            c4 = components[3] if len(components) > 3 else ""

            def to_int_or_str(val):
                val_stripped = val.strip()
                if val_stripped.isdigit():
                    return int(val_stripped)
                return val_stripped

            file_id = to_int_or_str(c1)
            map_id = to_int_or_str(c2)
            event_id = to_int_or_str(c3)
            line_id = to_int_or_str(c4)

            # Block boundaries
            start_idx = match.end()
            end_idx = matches[i+1].start() if i+1 < len(matches) else len(content)
            block_text = content[start_idx:end_idx].strip()
            
            if not block_text:
                continue

            lines = [line.strip() for line in block_text.splitlines()]
            non_empty_lines = [line for line in lines if line]
            if not non_empty_lines:
                continue

            first_line = non_empty_lines[0]
            
            # Detect speaker if first line contains global icon references or wrapping quotes
            has_icon = bool(re.search(r'\\I\[(\d+)\]', first_line))
            has_quotes = first_line.startswith('"') or first_line.endswith('"') or first_line.startswith("'") or first_line.endswith("'")
            
            if has_icon or has_quotes:
                raw_name_line = first_line
                body_lines = non_empty_lines[1:]
                
                # Extract spritesheet reference: \I[index]
                icon_index = None
                icon_match = re.search(r'\\I\[(\d+)\]', raw_name_line)
                if icon_match:
                    icon_index = int(icon_match.group(1))
                    raw_name_line = re.sub(r'\\I\[\d+\]', '', raw_name_line).strip()

                name = strip_outer_quotes(raw_name_line)
            else:
                name = ""
                body_lines = non_empty_lines
                icon_index = None
            
            # Clean and join body text
            body_text = "\n".join(body_lines).strip()

            # Match and extract any keywords inside non-zero color tags: \C[1-9...] ... \C[0]
            # Use [\s\S]*? to support multi-line matches across newlines
            keywords = []
            highlight_pattern = re.compile(r'\\C\[([1-9]\d*)\]([\s\S]*?)\\C\[0\]')
            for kw_match in highlight_pattern.finditer(body_text):
                kw_text = kw_match.group(2).strip()
                # Also strip color tag markers if nested inside the keyword text
                kw_text = re.sub(r'\\C\[\d+\]', '', kw_text).strip()
                if kw_text:
                    keywords.append(kw_text)

            # Strip all engine color tags from body
            cleaned_body = re.sub(r'\\C\[\d+\]', '', body_text).strip()

            # Drop empty entries gracefully
            if not name and not cleaned_body:
                continue

            parsed_blocks[composite_key] = {
                "file_id": file_id,
                "map_id": map_id,
                "event_id": event_id,
                "line_id": line_id,
                "name": name,
                "body": cleaned_body,
                "icon_index": icon_index,
                "keywords": keywords
            }
        except Exception as e:
            # Capturing block-level runtime violations without breaking the whole file processing
            console.print(f"[bold red]⚠️ Error parsing block at coordinate match {match.group(0)}: {e}[/bold red]")
            continue

    return parsed_blocks

def print_error_wall(message):
    panel_text = Text()
    panel_text.append("💥 PIPELINE EXCEPTION DETECTED 💥\n\n", style="bold red")
    panel_text.append(message, style="yellow")
    panel = Panel(panel_text, border_style="red", expand=False)
    console.print(panel)

def log_success(filename, entry_count, output_path):
    panel_text = Text()
    panel_text.append("🔥 HARVEST SUCCESSFUL 🔥\n\n", style="bold green")
    panel_text.append("Source File: ", style="white")
    panel_text.append(f"{filename}\n", style="bold cyan")
    panel_text.append("Staged Output: ", style="white")
    panel_text.append(f"{output_path}\n", style="bold cyan")
    panel_text.append("Total Staged Records: ", style="white")
    panel_text.append(f"{entry_count}\n", style="bold yellow")
    panel_text.append("Deterministic parsing completed successfully without errors.", style="green")
    panel = Panel(panel_text, border_style="green", expand=False)
    console.print(panel)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Deterministic Game Text Harvester")
    parser.add_argument("--input-file", type=str, default=None, help="Process a single raw text file")
    args = parser.parse_args()

    # Enforce directory setup
    os.makedirs(INPUT_GAME_TEXT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_CHUNKS_DIR, exist_ok=True)

    try:
        files_to_process = []
        if args.input_file:
            files_to_process.append(Path(args.input_file))
        else:
            # Scan for all files in input directory
            for entry in os.scandir(INPUT_GAME_TEXT_DIR):
                if entry.is_file():
                    files_to_process.append(Path(entry.path))

        if not files_to_process:
            console.print(f"[bold yellow]📭 No game text files found in '{INPUT_GAME_TEXT_DIR}'.[/bold yellow]")
            return

        for file_path in files_to_process:
            console.print(f"📖 Processing game text: [bold]{file_path.name}[/bold]")
            parsed_data = parse_game_text_file(file_path)
            
            if parsed_data is None:
                continue

            if not parsed_data:
                console.print(f"⚠️ No valid dialogue entries extracted from '{file_path.name}'.")
                continue

            # Standardized output name format
            output_filename = f"game_text_{file_path.stem}.json"
            output_path = OUTPUT_CHUNKS_DIR / output_filename

            # Serialize output to JSON format
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(parsed_data, f, indent=4, ensure_ascii=False)
                log_success(file_path.name, len(parsed_data), output_path)
            except Exception as e:
                print_error_wall(f"Failed to write JSON output for '{file_path.name}': {e}")

    except Exception as e:
        print_error_wall(f"Unexpected harvester pipeline error: {e}")

if __name__ == "__main__":
    main()
