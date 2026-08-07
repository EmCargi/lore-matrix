import os
from pathlib import Path

from core.engines import FeatherlessProvider, GeminiProvider, LocalProvider

# Resolve absolute path to the project root directory (parent of config/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Active Model Engine Provider Configuration
# Swap this out for GeminiProvider() or FeatherlessProvider(model_name) as needed.
ACTIVE_VISION_MODEL = "deepseek-r1:7b"
IS_REASONING_MODEL = True
REASONING_TAG_NAME = "think"

DEFAULT_ENGINE = "local"

def get_ai_provider(engine_name=None, model_name=None):
    """
    Returns an instance of the requested AI provider engine.
    If engine_name or model_name is not provided, falls back to the configured defaults.
    """
    engine = engine_name or DEFAULT_ENGINE
    engine = engine.lower()
    
    if engine == "gemini":
        model = model_name or "gemini-2.5-flash-preview-09-2025"
        return GeminiProvider(model_name=model)
    elif engine == "featherless":
        model = model_name or "deepseek-ai/DeepSeek-V3"
        return FeatherlessProvider(model_name=model)
    else: # local
        model = model_name or ACTIVE_VISION_MODEL
        return LocalProvider(model_name=model)

ACTIVE_AI = get_ai_provider()

# Pipeline Constraints & Limits
ACTIVE_SYSTEM = "BFRPG"
CHUNK_CHAR_LIMIT = 8000
OVERLAP_PARAGRAPHS = 1
MAX_SCRAPE_CHARS = 20000

# Directory and File Paths
INPUT_PDFS_DIR = BASE_DIR / "input_pdfs"
PROCESSED_PDFS_DIR = BASE_DIR / "processed_pdfs"
INPUT_IMAGES_DIR = BASE_DIR / "input_images"
PROCESSED_IMAGES_DIR = BASE_DIR / "processed_images"
OUTPUT_CHUNKS_DIR = BASE_DIR / "output" / "json_staging"
TARGETS_FILE = BASE_DIR / "targets.txt"
RAW_VAULT_DIR = BASE_DIR / "TTRPG_Vault"
COMPILED_VAULT_DIR = BASE_DIR / "vault"
ARCHIVEBOX_VAULT_DIR = Path(os.environ.get("ARCHIVEBOX_VAULT_DIR", BASE_DIR / "archivebox"))
INPUT_GAME_TEXT_DIR = BASE_DIR / "input_game_text"

# Load system prompts dynamically from config markdown files
def load_prompt(filename):
    prompt_path = BASE_DIR / "config" / filename
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        print(f"⚠️ Warning: Could not find system prompt file at '{prompt_path}'")
        return ""

EXTRACTOR_SYSTEM_PROMPT = load_prompt("extractor-prompt.md")
COMPILER_SYSTEM_PROMPT = load_prompt("compiler-prompt.md")
VISION_EXTRACTOR_SYSTEM_PROMPT = load_prompt("vision-extractor-prompt.md")