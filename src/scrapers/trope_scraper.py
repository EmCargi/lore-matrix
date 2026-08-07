import datetime
import json
import os
import random
import re
import sys
import tempfile
import time

import requests
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Established pipeline imports
from pydantic import ValidationError

from config.settings import CHUNK_CHAR_LIMIT, OVERLAP_PARAGRAPHS
from core.utils import generate_with_retry, scrape_wiki_text, semantic_chunker


# Define the Trope model per Stage 1 requirements
class TropeModel(BaseModel):
    Trope_Title: str = Field(..., description="The standard title or name of the narrative trope")
    Namespace: str = Field(..., description="The media namespace or category of the trope (e.g., Literature, Film, TV, Series, Main)")
    Definition: str = Field(..., description="A concise and clear definition of the trope")
    Examples: list[str] = Field(..., description="List of examples showcasing this trope in different works")
    Scrape_Timestamp: str = Field(default="", description="The timestamp when this trope was captured (ISO 8601 format)")
    Source_URL: str = Field(default="", description="The lineage source URL where this trope was found")

class TropeLog(BaseModel):
    tropes: list[TropeModel]

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>| ]', "_", name).strip("_")

def load_trope_config():
    config_path = os.path.join(project_root, "config", "trope_settings.json")
    try:
        with open(config_path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Warning: Could not load configuration. Using defaults. Error: {e}")
        return {
            "TARGET_NAMESPACES": ["Literature", "Film", "TV", "Series", "Main"],
            "polite_scrape_delay": 2.0,
            "CACHE_DIR": "cache/tropes"
        }

def get_cached_content(url, cache_dir):
    import hashlib
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    cache_path = os.path.join(cache_dir, f"{url_hash}.txt")
    if os.path.exists(cache_path):
        with open(cache_path, encoding='utf-8') as f:
            return f.read()
    return None

def set_cached_content(url, content, cache_dir):
    import hashlib
    os.makedirs(cache_dir, exist_ok=True)
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    cache_path = os.path.join(cache_dir, f"{url_hash}.txt")
    with open(cache_path, 'w', encoding='utf-8') as f:
        f.write(content)

def atomic_write(data, target_path):
    target_dir = os.path.dirname(target_path)
    os.makedirs(target_dir, exist_ok=True)
    # Write to a temporary file in the same directory, then rename to guarantee atomicity
    with tempfile.NamedTemporaryFile('w', dir=target_dir, delete=False, encoding='utf-8') as tf:
        json.dump(data, tf, indent=4)
        temp_name = tf.name
    try:
        os.replace(temp_name, target_path)
    except Exception as e:
        if os.path.exists(temp_name):
            os.remove(temp_name)
        raise e

def scrape_with_backoff(url, max_retries=4, base_delay=2.0):
    """
    Scrapes wiki text content with exponential backoff on errors or rate limits.
    Provides Ramsay-style warnings if rate limit (HTTP 429) or other errors occur.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    for attempt in range(max_retries):
        try:
            # Check for 429 rate limits explicitly
            try:
                test_resp = requests.head(url, headers=headers, timeout=5)
                if test_resp.status_code == 429:
                    print("⚠️ Rate Limit Hit - Backing off")
                    raise Exception("HTTP 429 Rate Limit")
            except Exception as e:
                if "429" in str(e):
                    raise e
                # Allow other failures to be handled by scrape_wiki_text
                pass

            content = scrape_wiki_text(url)
            if content:
                if "Enable JavaScript and cookies to continue" in content or "429 Too Many Requests" in content:
                    print("⚠️ Rate Limit Hit - Backing off")
                    raise Exception("Access blocked or rate limit hit")
                if "AuthenticationRequiredError" in content or "bad network reputation" in content:
                    print("⚠️ Rate Limit Hit - Backing off")
                    raise Exception("Jina API blocked due to authentication/reputation error.")
                return content
            else:
                raise Exception("Scrape returned empty content.")
                
        except Exception as e:
            backoff_time = (base_delay ** attempt) + random.uniform(0.5, 1.5)
            if attempt < max_retries - 1:
                print(f"⚠️ Rate Limit Hit - Backing off (Attempt {attempt+1}/{max_retries}). Reason: {e}")
                time.sleep(backoff_time)
            else:
                print(f"❌ Extraction Failed: Failed to scrape {url} after {max_retries} attempts.")
                raise e
    return None

def extract_namespace_from_url(url, target_namespaces):
    # Standard format: .../pmwiki.php/Namespace/PageName
    parts = url.split('/')
    for part in parts:
        for ns in target_namespaces:
            if part.lower() == ns.lower():
                return ns
    return "Main"

def harvest_tropes(url, active_ai, config):
    namespaces = config.get("TARGET_NAMESPACES", ["Literature", "Film", "TV", "Series", "Main"])
    cache_dir_rel = config.get("CACHE_DIR", "cache/tropes")
    cache_dir = os.path.join(project_root, cache_dir_rel)
    
    # Lineage information
    timestamp = datetime.datetime.now(datetime.UTC).isoformat()
    namespace = extract_namespace_from_url(url, namespaces)
    
    print("\n======================================")
    print(f"🎯 TARGET URL ACQUIRED: {url}")
    print("======================================")
    
    # Cache / Scrape
    raw_text = get_cached_content(url, cache_dir)
    if raw_text:
        print("  📂 Retrieved raw content from local cache.")
    else:
        try:
            raw_text = scrape_with_backoff(url)
            if raw_text:
                set_cached_content(url, raw_text, cache_dir)
                print("  💾 Saved raw content to local cache.")
            else:
                print("❌ Extraction Failed: Content is empty.")
                return False
        except Exception as e:
            print(f"❌ Extraction Failed: {e}")
            return False
            
    # Chunk raw text
    chunks = semantic_chunker(raw_text, chunk_char_limit=CHUNK_CHAR_LIMIT, overlap_paragraphs=OVERLAP_PARAGRAPHS)
    print(f"  -> Text semantically divided into {len(chunks)} logic blocks.")
    
    # Prompt Setup
    system_prompt = (
        "You are an expert literary analyst and narrative structure researcher.\n"
        "Your task is to analyze the provided text and extract narrative tropes (patterns, archetypes, and narrative formulas).\n"
        "For each trope, you must provide:\n"
        "- Trope_Title: The standard name of the trope.\n"
        "- Namespace: The category of work or namespace (e.g., Literature, Film, TV, Series).\n"
        "- Definition: A concise, clear definition of the trope.\n"
        "- Examples: A list of works or scenes that demonstrate this trope.\n\n"
        "You must output a JSON object containing a list of tropes under the key 'tropes', strictly conforming to the requested schema."
    )
    
    output_tropes_dir = os.path.join(project_root, "output", "tropes")
    os.makedirs(output_tropes_dir, exist_ok=True)
    
    success_count = 0
    
    for index, text_chunk in enumerate(chunks, 1):
        print(f"  -> Processing Logic Block {index}/{len(chunks)} ({len(text_chunk)} chars)...")
        user_prompt = (
            f"Please extract all narrative tropes from this text block:\n\n{text_chunk}\n\n"
            f"Infer the namespace (e.g. {namespace}) if it matches. "
            "Return the output as structured JSON matching the TropeLog schema."
        )
        
        try:
            # Query LLM with response_format constraint via generate_with_retry
            raw_response = generate_with_retry(active_ai, system_prompt, user_prompt, response_format=TropeLog)
            
            # Standard Pydantic model validation
            validated_log = TropeLog.model_validate_json(raw_response)
            tropes_list = validated_log.tropes
                
            # Save each trope atomically
            for trope_model in tropes_list:
                # Set current scraping metadata (Lineage Logging)
                trope_model.Scrape_Timestamp = timestamp
                trope_model.Source_URL = url
                if not trope_model.Namespace:
                    trope_model.Namespace = namespace
                
                # Target Path
                safe_title = sanitize_filename(trope_model.Trope_Title)
                if not safe_title:
                    safe_title = f"unnamed_trope_{int(time.time())}_{random.randint(100, 999)}"
                
                target_path = os.path.join(output_tropes_dir, f"{safe_title}.json")
                
                # Atomic write
                atomic_write(trope_model.model_dump(by_alias=True), target_path)
                print(f"🎯 Trope Ingested: {trope_model.Trope_Title}")
                success_count += 1
            
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
        except Exception as e:
            print(f"❌ Extraction Failed: Chunk {index}. Error: {e}")
                    
    return success_count > 0

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Trope Harvesting Scraper for Trope-RAG Pipeline")
    parser.add_argument("--engine", type=str, choices=["local", "gemini", "featherless"], default=None, help="AI provider engine to use")
    parser.add_argument("--model", type=str, default=None, help="Model name override")
    parser.add_argument("--url", type=str, default=None, help="Specific TV Tropes/web URL to harvest")
    args = parser.parse_args()
    
    config = load_trope_config()
    
    # Initialize Provider
    from config.settings import get_ai_provider
    active_ai = get_ai_provider(engine_name=args.engine, model_name=args.model)
    
    # If no URL given in args, gather URLs
    target_urls = []
    if args.url:
        target_urls.append(args.url)
    else:
        # Prompt user or read targets.txt
        url_input = input("Enter TV Tropes / Web URL to harvest (or press Enter to run targets from targets.txt): ").strip()
        if url_input:
            target_urls.append(url_input)
        else:
            from config.settings import TARGETS_FILE
            try:
                with open(TARGETS_FILE, encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '|' in line:
                            _, url = line.split('|', 1)
                            target_urls.append(url.strip())
                        else:
                            target_urls.append(line.strip())
            except FileNotFoundError:
                print(f"❌ Error: Could not find targets file at '{TARGETS_FILE}'.")
                sys.exit(1)
                
    if not target_urls:
        print("📭 No targets found to scrape. Add URLs to targets.txt or provide a URL via CLI.")
        sys.exit(0)
        
    print(f"Initializing Trope Harvester for {len(target_urls)} targets...")
    
    polite_delay = config.get("polite_scrape_delay", 2.0)
    
    for idx, url in enumerate(target_urls):
        if idx > 0:
            print(f"Polite scraping delay: waiting {polite_delay}s...")
            time.sleep(polite_delay)
            
        harvest_tropes(url, active_ai, config)

if __name__ == "__main__":
    main()
