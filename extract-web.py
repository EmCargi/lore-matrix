import json
import os
import random
import re
import time
from pathlib import Path

from pydantic import ValidationError

from config.settings import (
    ACTIVE_AI,
    ARCHIVEBOX_VAULT_DIR,
    CHUNK_CHAR_LIMIT,
    EXTRACTOR_SYSTEM_PROMPT,
    OUTPUT_CHUNKS_DIR,
    OVERLAP_PARAGRAPHS,
    TARGETS_FILE,
)
from core.utils import LorebookLog, clean_reasoning_response, generate_with_retry, scrape_wiki_text, semantic_chunker


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>| ]', "_", name).strip("_")

def run_lorebook_web_pipeline(url, name="", active_ai=None):
    if active_ai is None:
        active_ai = ACTIVE_AI
        
    category = ""
    char_name = "web_target"
    if name:
        if '/' in name:
            category, char_name = name.rsplit('/', 1)
            category = category.strip()
            char_name = char_name.strip()
        else:
            char_name = name
            
    # Output subfolder path
    output_dir = os.path.join(OUTPUT_CHUNKS_DIR, category) if category else OUTPUT_CHUNKS_DIR
    os.makedirs(output_dir, exist_ok=True)
    
    safe_char_name = sanitize_filename(char_name)

    try:
        print("\n======================================")
        print(f"🎯 TARGET WEB URL ACQUIRED: {url}")
        print("======================================")
        
        raw_text = scrape_wiki_text(url)
        if not raw_text:
            print("  ❌ Scrape failed. Skipping.")
            return False
            
        chunks = semantic_chunker(raw_text, chunk_char_limit=CHUNK_CHAR_LIMIT, overlap_paragraphs=OVERLAP_PARAGRAPHS)
        print(f"  -> Text semantically divided into {len(chunks)} logic blocks.")
        
        for index, text_chunk in enumerate(chunks, 1):
            print(f"  -> Processing Logic Block {index}/{len(chunks)} ({len(text_chunk)} chars)...")
            user_prompt = f"Extract all mechanics from this text block:\n\n{text_chunk}"
            
            try:
                raw_response = generate_with_retry(active_ai, EXTRACTOR_SYSTEM_PROMPT, user_prompt, response_format=LorebookLog)
                
                # Strip reasoning tags (deepseek-r1) and any code fences, then validate
                raw_response = clean_reasoning_response(raw_response)
                validated_log = LorebookLog.model_validate_json(raw_response)
                normalized_payload = validated_log.model_dump(by_alias=True)
                
                safe_path = os.path.join(output_dir, f"web_chunk_{safe_char_name}_{index:03d}.json")
                with open(safe_path, 'w', encoding='utf-8') as f:
                    json.dump(normalized_payload, f, indent=4)
                    
                print(f"  ✅ Saved {safe_path}")
                
            except ValidationError as ve:
                from rich.console import Console
                from rich.panel import Panel
                from rich.text import Text
                console = Console()
                error_text = Text()
                error_text.append("Schema Validation Error on Chunk ", style="bold red")
                error_text.append(f"{index}:\n\n", style="bold yellow")
                error_text.append(str(ve), style="yellow")
                error_text.append("\n\nRaw Response was:\n", style="bold cyan")
                error_text.append(str(raw_response), style="white")
                
                panel = Panel(error_text, title="[bold red]💥 SCHEMA VALIDATION FAILED 💥[/bold red]", border_style="red")
                console.print(panel)
                
                error_path = os.path.join(output_dir, f"web_chunk_{safe_char_name}_{index:03d}_ERROR.txt")
                with open(error_path, 'w', encoding='utf-8') as f:
                    f.write(f"Validation Error:\n{str(ve)}\n\nRaw Response:\n{raw_response}")
            except Exception as e:  # noqa: BLE001 - continue-on-error: note bad chunk, keep harvesting the rest
                print(f"  ❌ Chunk {index}: Failed processing. Error: {e}")
                error_path = os.path.join(output_dir, f"web_chunk_{safe_char_name}_{index:03d}_ERROR.txt")
                with open(error_path, 'w', encoding='utf-8') as f:
                    f.write(f"Pipeline Error: {e}")
            
        return True
    except Exception as e:
        print(f"  ❌ Critical pipeline error on URL {url}: {e}")
        return False

def extract_from_local_archive(timestamp_id, name="", active_ai=None):
    import unicodedata

    from bs4 import BeautifulSoup
    
    archive_dir = Path(ARCHIVEBOX_VAULT_DIR) / timestamp_id
    file_path = archive_dir / "singlefile.html"
    
    if not archive_dir.exists() or not file_path.exists():
        print(f"❌ Target snapshot [{timestamp_id}] not found in local ArchiveBox vault.")
        return False

    try:
        with open(file_path, encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"❌ Error reading local snapshot file: {e}")
        return False

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Isolate Weebly main content subtree if it exists
        main_content = soup.find(class_='wsite-not-footer')
        if main_content:
            soup = main_content
            
        # THE SCALPEL: Destroy all navigation, footers, and scripts before extracting
        for tag in soup(['header', 'footer', 'nav', 'aside', 'script', 'style']):
            tag.decompose()
            
        # Decompose any element with class names containing 'menu', 'nav', 'sidebar', or 'footer'
        class_pattern = re.compile(r'menu|nav|sidebar|(?<!not-)(?<!no-)footer', re.IGNORECASE)
        for tag in soup.find_all(class_=class_pattern):
            tag.decompose()
            
        content = soup.get_text(separator='\n\n', strip=True) # Double newline for semantic chunking
        clean_content = unicodedata.normalize('NFKC', content)
        
        # Limit the characters to scrape
        from config.settings import MAX_SCRAPE_CHARS
        raw_text = clean_content[:MAX_SCRAPE_CHARS]
    except Exception as e:
        print(f"❌ Error parsing HTML content from local snapshot: {e}")
        return False

    if not raw_text:
        print("  ❌ Scraped text is empty. Skipping.")
        return False

    # Now run the semantic chunks extraction pipeline
    if active_ai is None:
        active_ai = ACTIVE_AI
        
    category = ""
    char_name = f"archive_{timestamp_id}"
    if name:
        if '/' in name:
            category, char_name = name.rsplit('/', 1)
            category = category.strip()
            char_name = char_name.strip()
        else:
            char_name = name
            
    # Output subfolder path
    output_dir = os.path.join(OUTPUT_CHUNKS_DIR, category) if category else OUTPUT_CHUNKS_DIR
    os.makedirs(output_dir, exist_ok=True)
    
    safe_char_name = sanitize_filename(char_name)

    try:
        print("\n======================================")
        print(f"🎯 TARGET LOCAL ARCHIVE ACQUIRED: {file_path}")
        print("======================================")
        
        chunks = semantic_chunker(raw_text, chunk_char_limit=CHUNK_CHAR_LIMIT, overlap_paragraphs=OVERLAP_PARAGRAPHS)
        print(f"  -> Text semantically divided into {len(chunks)} logic blocks.")
        
        for index, text_chunk in enumerate(chunks, 1):
            print(f"  -> Processing Logic Block {index}/{len(chunks)} ({len(text_chunk)} chars)...")
            user_prompt = f"Extract all mechanics from this text block:\n\n{text_chunk}"
            
            try:
                raw_response = generate_with_retry(active_ai, EXTRACTOR_SYSTEM_PROMPT, user_prompt, response_format=LorebookLog)
                
                # Strip reasoning tags (deepseek-r1) and any code fences, then validate
                raw_response = clean_reasoning_response(raw_response)
                validated_log = LorebookLog.model_validate_json(raw_response)
                normalized_payload = validated_log.model_dump(by_alias=True)
                
                safe_path = os.path.join(output_dir, f"web_chunk_{safe_char_name}_{index:03d}.json")
                with open(safe_path, 'w', encoding='utf-8') as f:
                    json.dump(normalized_payload, f, indent=4)
                    
                print(f"  ✅ Saved {safe_path}")
                
            except ValidationError as ve:
                from rich.console import Console
                from rich.panel import Panel
                from rich.text import Text
                console = Console()
                error_text = Text()
                error_text.append("Schema Validation Error on Chunk ", style="bold red")
                error_text.append(f"{index}:\n\n", style="bold yellow")
                error_text.append(str(ve), style="yellow")
                error_text.append("\n\nRaw Response was:\n", style="bold cyan")
                error_text.append(str(raw_response), style="white")
                
                panel = Panel(error_text, title="[bold red]💥 SCHEMA VALIDATION FAILED 💥[/bold red]", border_style="red")
                console.print(panel)
                
                error_path = os.path.join(output_dir, f"web_chunk_{safe_char_name}_{index:03d}_ERROR.txt")
                with open(error_path, 'w', encoding='utf-8') as f:
                    f.write(f"Validation Error:\n{str(ve)}\n\nRaw Response:\n{raw_response}")
            except Exception as e:  # noqa: BLE001 - continue-on-error: note bad chunk, keep harvesting the rest
                print(f"  ❌ Chunk {index}: Failed processing. Error: {e}")
                error_path = os.path.join(output_dir, f"web_chunk_{safe_char_name}_{index:03d}_ERROR.txt")
                with open(error_path, 'w', encoding='utf-8') as f:
                    f.write(f"Pipeline Error: {e}")
            
        return True
    except Exception as e:
        print(f"  ❌ Critical pipeline error on local archive {file_path}: {e}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Web Ingestion Engine for the Lore Matrix")
    parser.add_argument("--engine", type=str, choices=["local", "gemini", "featherless"], default=None, help="AI provider engine to use")
    parser.add_argument("--model", type=str, default=None, help="Model name override")
    parser.add_argument("--archive", type=str, default=None, help="ArchiveBox Timestamp ID to ingest locally")
    args = parser.parse_args()
    
    from config.settings import get_ai_provider
    active_ai = get_ai_provider(engine_name=args.engine, model_name=args.model)
    
    if args.archive:
        success = extract_from_local_archive(args.archive, active_ai=active_ai)
        exit(0 if success else 1)
    
    target_urls = []
    
    try:
        with open(TARGETS_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Split at the pipe and grab both name and URL
                if '|' in line:
                    name, url = line.split('|', 1)
                    target_urls.append((name.strip(), url.strip()))
                else:
                    # Fallback just in case you paste a raw URL
                    target_urls.append(("", line.strip()))
                    
    except FileNotFoundError:
        print(f"❌ Error: Could not find targets file at '{TARGETS_FILE}'.")
        exit(1)

    if not target_urls:
        print(f"📭 The targets file '{TARGETS_FILE}' is empty. Add URLs to process!")
        exit(0)

    completed_log_path = "completed_targets.txt"
    if not os.path.exists(completed_log_path):
        with open(completed_log_path, 'w', encoding='utf-8') as f:
            pass
            
    completed_urls = set()
    with open(completed_log_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                completed_urls.add(line)

    print(f"☕ Initializing Lore-Forge for {len(target_urls)} web targets...")
    for name, url in target_urls:
        if url in completed_urls:
            print(f"  ⏭️ Skipping already completed target: {url}")
            continue
            
        success = run_lorebook_web_pipeline(url, name=name, active_ai=active_ai)
        if success:
            with open(completed_log_path, 'a', encoding='utf-8') as f:
                f.write(url + '\n')
            completed_urls.add(url)
            
        time.sleep(random.uniform(4, 8))
