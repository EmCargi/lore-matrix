import json
import os
import shutil
from pathlib import Path

from pydantic import ValidationError

from config.settings import (
    ACTIVE_AI,
    CHUNK_CHAR_LIMIT,
    EXTRACTOR_SYSTEM_PROMPT,
    INPUT_PDFS_DIR,
    OUTPUT_CHUNKS_DIR,
    OVERLAP_PARAGRAPHS,
    PROCESSED_PDFS_DIR,
)
from core.utils import (
    LorebookLog,
    clean_reasoning_response,
    extract_pdf_text_via_pdfplumber,
    generate_with_retry,
    semantic_chunker,
)


def run_extraction_pipeline(pdf_file_path, active_ai=None):
    if active_ai is None:
        active_ai = ACTIVE_AI
        
    print("🚀 Starting PDF Extraction Pipeline...")
    
    # 1. Extract raw text from the PDF using pdfplumber layout engine
    full_text = extract_pdf_text_via_pdfplumber(pdf_file_path)
    
    # 2. Slice text semantically
    chunks = semantic_chunker(
        full_text, 
        chunk_char_limit=CHUNK_CHAR_LIMIT, 
        overlap_paragraphs=OVERLAP_PARAGRAPHS
    )
    print(f"  -> Text semantically divided into {len(chunks)} logic blocks.")
    
    # Determine output directory dynamically to sort outputs intelligently
    pdf_path = Path(pdf_file_path)
    try:
        rel_path = pdf_path.relative_to(INPUT_PDFS_DIR)
    except ValueError:
        rel_path = Path(pdf_path.name)
        
    rel_dir = rel_path.parent
    target_out_dir = OUTPUT_CHUNKS_DIR / rel_dir / pdf_path.stem
    target_out_dir.mkdir(parents=True, exist_ok=True)
    
    # 3. Process each chunk
    saved_chunks = 0
    for chunk_id, text_chunk in enumerate(chunks, 1):
        print(f"  -> Processing Chunk {chunk_id}/{len(chunks)} ({len(text_chunk)} chars)...")
        
        user_prompt = f"Extract all mechanics from this text:\n\n{text_chunk}"
        
        try:
            raw_response = generate_with_retry(active_ai, EXTRACTOR_SYSTEM_PROMPT, user_prompt, response_format=LorebookLog)
            
            # Strip reasoning tags (deepseek-r1) and any code fences, then validate
            raw_response = clean_reasoning_response(raw_response)
            validated_log = LorebookLog.model_validate_json(raw_response)
            final_payload = validated_log.model_dump(by_alias=True)
                
            safe_path = os.path.join(target_out_dir, f"chunk_{chunk_id:03d}.json")
            with open(safe_path, 'w', encoding='utf-8') as f:
                json.dump(final_payload, f, indent=4)
                
            print(f"  ✅ Saved {safe_path}")
            saved_chunks += 1
                
        except ValidationError as e:
            from rich.console import Console
            from rich.panel import Panel
            from rich.text import Text
            console = Console()
            error_text = Text()
            error_text.append("Schema Validation Error on Chunk ", style="bold red")
            error_text.append(f"{chunk_id}:\n\n", style="bold yellow")
            error_text.append(str(e), style="yellow")
            error_text.append("\n\nRaw Response was:\n", style="bold cyan")
            error_text.append(str(raw_response), style="white")
            
            panel = Panel(error_text, title="[bold red]💥 SCHEMA VALIDATION FAILED 💥[/bold red]", border_style="red")
            console.print(panel)
            
            error_path = os.path.join(target_out_dir, f"chunk_{chunk_id:03d}_ERROR.txt")
            with open(error_path, 'w', encoding='utf-8') as f:
                f.write(f"Validation Error:\n{str(e)}\n\nRaw Response:\n{raw_response}")
        except Exception as e:  # noqa: BLE001 - continue-on-error: log bad chunk, keep processing remaining pages
            print(f"  ❌ Error on Chunk {chunk_id}: {e}")

    return saved_chunks

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PDF Mechanics Extractor for the Lore Matrix")
    parser.add_argument("--engine", type=str, choices=["local", "gemini", "featherless"], default=None, help="AI provider engine to use")
    parser.add_argument("--model", type=str, default=None, help="Model name override")
    args = parser.parse_args()
    
    from config.settings import get_ai_provider
    active_ai = get_ai_provider(engine_name=args.engine, model_name=args.model)
    
    print(f"Initializing Core Extractor using: {active_ai.__class__.__name__} ({active_ai.model_name})...\n")
    
    # Ensure they exist so the script never crashes on a fresh install
    os.makedirs(INPUT_PDFS_DIR, exist_ok=True)
    os.makedirs(PROCESSED_PDFS_DIR, exist_ok=True)

    # 1. Dynamically sweep the hopper for any PDFs recursively
    target_pdfs = []
    if INPUT_PDFS_DIR.exists():
        for p in Path(INPUT_PDFS_DIR).rglob("*.pdf"):
            target_pdfs.append(p)
        for p in Path(INPUT_PDFS_DIR).rglob("*.PDF"):
            target_pdfs.append(p)
    target_pdfs = sorted(list(set(target_pdfs)))

    if not target_pdfs:
        print(f"📭 The hopper is empty. No PDFs found in {INPUT_PDFS_DIR}/")
    else:
        print(f"☕ Found {len(target_pdfs)} PDFs in the hopper. Igniting engine...")

        # 2. Process each file
        for pdf_file in target_pdfs:
            print("\n======================================")
            print(f"🎯 TARGET ACQUIRED: {pdf_file.name}")
            print("======================================")
            
            try:
                saved_chunks = run_extraction_pipeline(pdf_file, active_ai=active_ai)
                
                # Archive only if at least one valid chunk was extracted; otherwise
                # leave the source in the hopper so it can be inspected/re-run.
                if saved_chunks == 0:
                    print(f"  ⚠️ No valid chunks extracted from {pdf_file.name}. Leaving file in input hopper for inspection.")
                    continue
                
                # 3. Archive successfully processed PDF preserving directory structure
                try:
                    rel_path = pdf_file.relative_to(INPUT_PDFS_DIR)
                except ValueError:
                    rel_path = Path(pdf_file.name)
                destination = PROCESSED_PDFS_DIR / rel_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(pdf_file), str(destination))
                print(f"  📦 Successfully archived {pdf_file.name} to {destination.parent}/")
                
            except Exception as e:  # noqa: BLE001 - leave source in hopper on failure; never destroy raw input
                # If it fails, leave it in the hopper so you can inspect it!
                print(f"  💥 CRITICAL FAILURE on {pdf_file.name}: {e}")
                print("  -> Leaving file in input hopper and moving to the next target...")
