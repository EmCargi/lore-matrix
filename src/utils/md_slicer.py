#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Path agnosticism setup
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

console = Console()

def sanitize_filename(name):
    # Remove illegal characters: /, \, :, *, ?, ", <, >, |
    sanitized = re.sub(r'[\\/*?:"<>|]', '', name)
    return sanitized.strip()

def extract_global_frontmatter(file_path):
    """
    Reads the beginning of a file to extract any YAML frontmatter block
    enclosed by '---' lines. Returns the frontmatter block string and the
    remaining lines generator.
    """
    frontmatter_lines = []
    frontmatter_captured = False
    
    f = open(file_path, encoding='utf-8')
    
    first_line = f.readline()
    if not first_line:
        f.close()
        return "", []
        
    if first_line.strip() == "---":
        frontmatter_lines.append(first_line)
        for line in f:
            frontmatter_lines.append(line)
            if line.strip() == "---":
                frontmatter_captured = True
                break
    else:
        # No frontmatter block. Yield the first line and then the rest of the file
        def remaining_lines_gen():
            yield first_line
            for line in f:
                yield line
            f.close()
        return "", remaining_lines_gen()

    if frontmatter_captured:
        global_frontmatter = "".join(frontmatter_lines)
        def remaining_lines_gen():
            for line in f:
                yield line
            f.close()
        return global_frontmatter, remaining_lines_gen()
    else:
        # Malformed or unclosed frontmatter block, treat the whole thing as content
        global_frontmatter = ""
        def remaining_lines_gen():
            for line in frontmatter_lines:
                yield line
            for line in f:
                yield line
            f.close()
        return global_frontmatter, remaining_lines_gen()

def slice_markdown_file(input_file_path, output_dir):
    input_file_path = Path(input_file_path)
    output_dir = Path(output_dir)
    
    if not input_file_path.exists():
        print_error_wall(f"Input file does not exist: {input_file_path}")
        return False

    os.makedirs(output_dir, exist_ok=True)
    
    header_pattern = re.compile(r'^#+\s+(.*)')
    
    current_file = None
    current_file_path = None
    sliced_count = 0
    total_lines_processed = 0

    try:
        # Extract the frontmatter and obtain the generator for the rest of the file
        global_frontmatter, line_generator = extract_global_frontmatter(input_file_path)
        
        for line in line_generator:
            total_lines_processed += 1
            match = header_pattern.match(line)
            
            if match:
                # Close the current file if open
                if current_file:
                    current_file.close()
                    current_file = None
                
                header_text = match.group(1).strip()
                sanitized_name = sanitize_filename(header_text)
                
                if not sanitized_name:
                    console.print(f"[bold yellow]⚠️ Warning: Header '{header_text}' at line {total_lines_processed} resulted in an empty filename. Skipping block.[/bold yellow]")
                    continue
                
                # Open new file
                filename = f"{sanitized_name}.md"
                current_file_path = output_dir / filename
                try:
                    current_file = open(current_file_path, 'w', encoding='utf-8')
                    # Write frontmatter first if present
                    if global_frontmatter:
                        current_file.write(global_frontmatter)
                    # Write the header line to start the file
                    current_file.write(line)
                    sliced_count += 1
                except Exception as write_err:
                    console.print(f"[bold red]❌ Failed to open output file '{current_file_path}': {write_err}[/bold red]")
                    current_file = None
            else:
                # If we are inside a file block, write the line
                if current_file:
                    current_file.write(line)
                    
        # Close the last file if open
        if current_file:
            current_file.close()
            
        log_success(input_file_path.name, sliced_count, output_dir)
        return True

    except Exception as e:
        print_error_wall(f"Error during markdown slicing: {e}")
        return False

def print_error_wall(message):
    panel_text = Text()
    panel_text.append("💥 SLICER EXCEPTION DETECTED 💥\n\n", style="bold red")
    panel_text.append(message, style="yellow")
    panel = Panel(panel_text, border_style="red", expand=False)
    console.print(panel)

def log_success(filename, sliced_count, output_dir):
    panel_text = Text()
    panel_text.append("🔥 DETERMINISTIC SLICE COMPLETED 🔥\n\n", style="bold green")
    panel_text.append("Monolithic File: ", style="white")
    panel_text.append(f"{filename}\n", style="bold cyan")
    panel_text.append("Output Directory: ", style="white")
    panel_text.append(f"{output_dir}\n", style="bold cyan")
    panel_text.append("Total Individual Notes Sliced: ", style="white")
    panel_text.append(f"{sliced_count}\n", style="bold yellow")
    panel_text.append("Streaming parser finished splitting successfully.", style="green")
    panel = Panel(panel_text, border_style="green", expand=False)
    console.print(panel)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Deterministic Markdown File Slicer")
    parser.add_argument("input_file", type=str, help="Path to the monolithic markdown file")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for sliced files")
    args = parser.parse_args()

    # Default output dir
    if args.output_dir:
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = PROJECT_ROOT / args.output_dir
    else:
        output_dir = PROJECT_ROOT / "obsidian_vault" / "dialogue_split"

    input_path = Path(args.input_file)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / args.input_file

    success = slice_markdown_file(input_path, output_dir)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
