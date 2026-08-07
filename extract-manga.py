import argparse
import json
import os
import re
import sys
from pathlib import Path

# Resolve absolute path to the project root directory
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

try:
    from pydantic import ValidationError

    from config.settings import OUTPUT_CHUNKS_DIR
    from core.utils import NarrativeLog, clean_reasoning_response, generate_with_retry
except ImportError as e:
    print(f"❌ System Error: Failed to import codebase modules: {e}")
    sys.exit(1)


class DynamicLocalProvider:
    """
    Connection wrapper to interface with local Ollama endpoint.
    """
    def __init__(self, host="localhost", port=11434, model_name="deepseek-r1:7b"):
        self.host = host
        self.port = port
        self.model_name = model_name

    def generate(self, system_prompt, user_content, response_format=None):
        import requests
        url = f"http://{self.host}:{self.port}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "stream": False,
            "options": {
                "temperature": 0.3
            }
        }
        if response_format:
            payload["format"] = response_format.model_json_schema()
            
        res = requests.post(url, json=payload)
        res.raise_for_status()
        res_json = res.json()
        return res_json["message"]["content"]


def extract_page_number(file_path):
    """
    Numerically isolate the page number from the file name.
    """
    name = file_path.name
    match = re.search(r'(\d+)', name)
    if match:
        return int(match.group(1))
    return 999999


def chunk_timeline(timeline_parts, max_chars=10000):
    """
    Groups timeline pages into chunks to stay within model token constraints safely.
    """
    chunks = []
    current_chunk = []
    current_len = 0
    for part in timeline_parts:
        part_len = len(part)
        # If adding this page exceeds the chunk size, seal the current chunk
        if current_len + part_len > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [part]
            current_len = part_len
        else:
            current_chunk.append(part)
            current_len += part_len + 2  # accounted for joining separator
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks


def main():
    parser = argparse.ArgumentParser(description="Deterministic & Cognitive Manga OCR Transformation Bridge")
    parser.add_argument("--model", type=str, default="deepseek-r1:7b", help="Target processing model (e.g., deepseek-r1:7b, qwen2.5-coder)")
    parser.add_argument("--host", type=str, default="localhost", help="Ollama host endpoint")
    parser.add_argument("--port", type=int, default=11434, help="Ollama port endpoint")
    parser.add_argument("--chunk-size", type=int, default=10000, help="Max characters per cognitive processing chunk")
    args = parser.parse_args()

    # 1. Environment Bounds
    INPUT_DIR = BASE_DIR / "input_manga_ocr"
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize connection wrapper to local Ollama
    provider = DynamicLocalProvider(host=args.host, port=args.port, model_name=args.model)

    # Dynamic Input Sweep (Recursive Search)
    ocr_dirs = []
    for root, dirs, _files in os.walk(INPUT_DIR):
        for d in dirs:
            if d == "_ocr":
                ocr_dirs.append(Path(root) / d)
                
    ocr_dirs = sorted(ocr_dirs)
    if not ocr_dirs:
        print(f"📭 Empty directory state: No '_ocr' folders found recursively under {INPUT_DIR}/")
        sys.exit(0)

    # System Meta-Prompt Constraint: The Specificity Mandate
    SYSTEM_PROMPT = (
        "You are a deterministic and cognitive Transformation Bridge in a Lore Matrix ETL pipeline.\n"
        "Your task is to take a raw reconstructed dialogue timeline from manga pages, map each dialogue block to a Speaker, "
        "reassemble the narrative block context, and extract character profiles, abilities, world facts, and scene/action context.\n\n"
        "CRITICAL CONSTRAINTS:\n"
        "1. You must execute under 'The Specificity Mandate.' You must isolate proper names, dialogue facts, biomechanical metrics, "
        "or group parameters while ignoring filler prose or explanations of game mechanics.\n"
        "2. For each dialogue segment or narrative context, assign a 'Speaker' (e.g., character name or 'System/Environment').\n"
        "3. Keep the 'Dialogue' field matched to the reconstructed dialogue from the pages (leave empty if it's describing background actions or lore events).\n"
        "4. In 'Scene Description', output the calculated structural context or extracted lore attributes (character profiles, abilities, world facts, "
        "or visual scene setup).\n"
        "5. Output strictly a JSON object matching the requested schema. No conversational filler, no extra explanation.\n"
    )

    for ocr_dir in ocr_dirs:
        # Path Variable Extraction
        title = ocr_dir.parent.name
        artist = ocr_dir.parent.parent.name
        
        # Support both direct _ocr and nested structures in _ocr/title
        ocr_subdirs = [d for d in ocr_dir.iterdir() if d.is_dir()]
        active_ocr_paths = ocr_subdirs if ocr_subdirs else [ocr_dir]

        for active_ocr_dir in active_ocr_paths:
            print(f"🎯 Artist Node Discovered: {artist}")
            print(f"🎯 Mokuro Directory Located: {active_ocr_dir}")
            print(f"🧹 Building Script Stream for Title: {title}")

            # Discover and sort page JSON files numerically
            page_files = sorted(
                [p for p in active_ocr_dir.glob("*.json") if p.is_file()],
                key=extract_page_number
            )
            
            if not page_files:
                print(f"  ⚠️ No JSON files found in {active_ocr_dir}. Skipping...")
                continue

            print(f"🧹 Fragment Text Sorted for {artist}/{title}")

            # Phase 1: Ingestion & Aggregation
            timeline_parts = []
            for pf in page_files:
                page_num = extract_page_number(pf)
                try:
                    with open(pf, encoding="utf-8") as f:
                        page_data = json.load(f)
                except Exception as e:  # noqa: BLE001 - skip a corrupt page file, keep ingesting the rest
                    print(f"  ❌ Error reading {pf.name}: {e}")
                    continue

                blocks = page_data.get("blocks", [])
                page_dialogues = []
                for block in blocks:
                    lines = block.get("lines", [])
                    if lines:
                        text = " ".join(lines).strip()
                        if text:
                            page_dialogues.append(text)

                # Label by page number
                page_str = f"--- Page {page_num} ---"
                if page_dialogues:
                    page_str += "\n" + "\n".join(page_dialogues)
                timeline_parts.append(page_str)

            # Segment into chunks
            chunks = chunk_timeline(timeline_parts, max_chars=args.chunk_size)
            all_entries = []

            # Phase 2 & 3: Cognitive Layer, Cleaning, and Strict Validation
            for chunk_idx, chunk in enumerate(chunks, 1):
                print(f"🔥 GPU Matrix Pumping Tokens for {artist}/{title} (Chunk {chunk_idx}/{len(chunks)})...")
                
                try:
                    raw_response = generate_with_retry(provider, SYSTEM_PROMPT, chunk, response_format=NarrativeLog)
                    
                    # Strip reasoning tags (deepseek-r1) and any code fences, then validate
                    raw_response = clean_reasoning_response(raw_response)
                    validated_log = NarrativeLog.model_validate_json(raw_response)
                    entries = validated_log.model_dump(by_alias=True).get("entries", [])
                    
                    # Ghost Node Sanitization
                    for entry in entries:
                        dialogue_val = entry.get("Dialogue")
                        if dialogue_val is None or (isinstance(dialogue_val, str) and dialogue_val.strip() == ""):
                            entry["Dialogue"] = ""
                            entry["Speaker"] = "System/Environment"

                    all_entries.extend(entries)

                except ValidationError as e:
                    from rich.console import Console
                    from rich.panel import Panel
                    from rich.text import Text
                    console = Console()
                    error_text = Text()
                    error_text.append("Schema Validation Error on Chunk ", style="bold red")
                    error_text.append(f"{chunk_idx}:\n\n", style="bold yellow")
                    error_text.append(str(e), style="yellow")
                    error_text.append("\n\nRaw Response was:\n", style="bold cyan")
                    error_text.append(str(raw_response), style="white")
                    
                    panel = Panel(error_text, title="[bold red]💥 SCHEMA VALIDATION FAILED 💥[/bold red]", border_style="red")
                    console.print(panel)
                    raise e
                except Exception as exc:
                    print(f"❌ Failed cognitive layer execution for {artist}/{title}: {exc}")
                    raise exc

            # Phase 5: Output Management
            final_payload = {"entries": all_entries}
            
            # Final strict validation on the full compiled payload
            try:
                if hasattr(NarrativeLog, "model_validate"):
                    NarrativeLog.model_validate(final_payload)
                else:
                    NarrativeLog.validate(final_payload)
            except Exception as final_err:
                print(f"❌ Failed final payload validation check: {final_err}")
                raise ValueError(f"Compiled payload schema validation failed: {final_err}") from final_err

            # Construct safe path mirroring the organization
            output_dir = OUTPUT_CHUNKS_DIR / artist
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"manga_chunk_{title}.json"

            with open(output_file, "w", encoding="utf-8") as out_f:
                json.dump(final_payload, out_f, indent=4, ensure_ascii=False)

            print(f"📦 Staging Payload Commited: {output_file}")


if __name__ == "__main__":
    main()
