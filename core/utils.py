import re
import unicodedata

import pdfplumber
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

# =====================================================================
# CORE UTILITY FUNCTIONS (Scraping, Chunking, Extraction, & Parsing)
# =====================================================================

def scrape_wiki_text(url, max_chars=20000): 
    """
    Fetches raw text content from a wiki/URL using BeautifulSoup first, 
    falls back to the Jina Reader API, and normalizes unicode characters.
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        # --- ENGINE 1: BeautifulSoup (Fast, simple, great for Weebly) ---
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
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
            
            # If we didn't hit a Cloudflare JS blocker, we are good to go!
            if "Enable JavaScript and cookies to continue" not in content:
                print(f"  -> Successfully scraped via BeautifulSoup: {url}")
                clean_content = unicodedata.normalize('NFKC', content)
                return clean_content[:max_chars]
                
        # --- ENGINE 2: Jina Reader Fallback (For Wikis & Blocked Sites) ---
        print("  -> Direct scrape blocked. Falling back to Jina API...")
        jina_url = f"https://r.jina.ai/{url}"
        jina_headers = {'User-Agent': 'Mozilla/5.0'} 
        jina_response = requests.get(jina_url, headers=jina_headers, timeout=20)
        
        clean_content = unicodedata.normalize('NFKC', jina_response.text)
        return clean_content[:max_chars]
        
    except Exception as e:  # noqa: BLE001 - graceful degrade: return "" so caller falls to next source
        print(f"  -> Warning: Failed to scrape {url}. Error: {e}")
        return ""


def semantic_chunker(text, chunk_char_limit=8000, overlap_paragraphs=1):
    """
    Cuts chunks logically at double newlines so paragraphs are not sliced in half.
    Includes overlap_paragraphs to prevent context amnesia between chunks.
    """
    paragraphs = text.split('\n\n')
    chunks = []
    current_paragraphs = []
    
    for p in paragraphs:
        # Clean up block and ignore if empty
        p = p.strip()
        if not p:
            continue
            
        # Hard clamp if paragraph exceeds limit
        if len(p) > chunk_char_limit:
            p = p[:chunk_char_limit]
            
        if current_paragraphs:
            # Calculate length if we were to append the current paragraph to the current chunk
            tentative_len = sum(len(x) for x in current_paragraphs) + 2 * len(current_paragraphs) + len(p)
            
            if tentative_len > chunk_char_limit:
                # Seal the current chunk
                chunks.append("\n\n".join(current_paragraphs).strip())
                
                # Retrieve the candidate overlap paragraphs from the sealed chunk
                overlap_list = current_paragraphs[-overlap_paragraphs:] if overlap_paragraphs > 0 else []
                
                # Dynamically trim overlap paragraphs (discarding the oldest first) 
                # if they plus the new paragraph exceed the character limit.
                while overlap_list:
                    overlap_len = sum(len(x) for x in overlap_list) + 2 * len(overlap_list) + len(p)
                    if overlap_len > chunk_char_limit:
                        overlap_list.pop(0)
                    else:
                        break
                
                current_paragraphs = overlap_list + [p]
                continue
                
        current_paragraphs.append(p)
        
    if current_paragraphs:
        chunks.append("\n\n".join(current_paragraphs).strip())
        
    return chunks


def extract_pdf_text_via_pdfplumber(pdf_path):
    """
    Reads a PDF using pdfplumber and extracts text while preserving structural layout.
    """
    text_content = []
    print(f"📖 Opening PDF via pdfplumber: {pdf_path}")
    with pdfplumber.open(pdf_path) as pdf:
        for _page_num, page in enumerate(pdf.pages, start=1):
            # Extract text preserving visual columns and layouts
            page_text = page.extract_text(layout=True)
            if page_text:
                text_content.append(page_text)
    return "\n\n".join(text_content)


def sanitize_json_response(raw_response):
    """
    Cleans up LLM markdown blocks (like ```json ... ```) and extracts the raw JSON text.
    """
    cleaned = raw_response.strip()
    
    # Use regex to isolate the outermost JSON array/object structure if LLM added conversational text
    json_match = re.search(r'(\{.*\}|\[.*\])', cleaned, re.DOTALL)
    if json_match:
        return json_match.group(1)
        
    return cleaned


def clean_reasoning_response(raw_response):
    """
    Strips reasoning tags (like <think>...</think>) based on config settings,
    and isolates the JSON structure.
    """
    from config.settings import IS_REASONING_MODEL, REASONING_TAG_NAME
    
    cleaned = raw_response
    if IS_REASONING_MODEL and REASONING_TAG_NAME:
        pattern = rf'<{REASONING_TAG_NAME}>.*?</{REASONING_TAG_NAME}>'
        cleaned = re.sub(pattern, '', raw_response, flags=re.DOTALL).strip()
        
    # Try to extract the JSON array/object structure
    json_match = re.search(r'(\[.*\]|\{.*\})', cleaned, re.DOTALL)
    if json_match:
        return json_match.group(1)
        
    return cleaned


class NarrativeEntry(BaseModel):
    Speaker: str = Field(..., description="Name of the speaker (include thought/whisper modality in parentheses, e.g. 'Makoto (Thought)')")
    Dialogue: str = Field(..., description="Dialogue text (leave empty if the segment is a silent action or scene description)")
    Scene_Description: str = Field(..., serialization_alias="Scene Description", validation_alias="Scene Description", description="Describing the scene, action, or context surrounding the dialogue")


class NarrativeLog(BaseModel):
    entries: list[NarrativeEntry]


class LorebookEntry(BaseModel):
    id: int = Field(..., description="Unique integer identifier starting from 1")
    name: str = Field(..., description="Name or title of the entity or mechanic")
    keys: list[str] = Field(..., description="3 to 6 unique specific trigger strings, e.g. ['spell name', 'spell keyword']")
    content: str = Field(..., description="Compressed dense description followed by bracketed metadata tags like '[Type: Spell] [Level: 3]'")
    insertion_order: int = Field(50, description="Order of insertion, default is 50")
    priority: int = Field(50, description="Priority value, default is 50")


class LorebookLog(BaseModel):
    entries: list[LorebookEntry]


from rich.console import Console
from rich.text import Text
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

console = Console()

def log_retry(retry_state):
    sleep_time = retry_state.next_action.sleep
    exc = retry_state.outcome.exception()
    attempt = retry_state.attempt_number
    
    msg = Text()
    msg.append("⚠️ Request throttled/failed (Attempt ", style="bold yellow")
    msg.append(f"{attempt}", style="bold cyan")
    msg.append(f"). Error: {exc}. Re-attempting in ", style="bold yellow")
    msg.append(f"{sleep_time:.2f} seconds...", style="bold green")
    
    console.print(msg)

def is_retryable_exception(exception):
    # Retry on requests exceptions (HTTP errors, connection issues, timeouts)
    if isinstance(exception, requests.exceptions.RequestException):
        return True
    
    # Or general network/API errors that might indicate server overload
    exc_str = str(exception).lower()
    for keyword in ["rate limit", "throttled", "429", "503", "500", "timeout", "connection", "http"]:
        if keyword in exc_str:
            return True
            
    return False

@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(multiplier=1, min=2, max=30),
    before_sleep=log_retry,
    retry=retry_if_exception(is_retryable_exception)
)
def generate_with_retry(active_ai, system_prompt, user_prompt, response_format=None):
    """
    Executes raw generate client call with exponential backoff retry policy on network/HTTP failures.
    """
    return active_ai.generate(system_prompt, user_prompt, response_format=response_format)
