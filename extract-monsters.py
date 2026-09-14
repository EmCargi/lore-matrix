import json
import os
import random
import re
import sys
import time

from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import (
    ACTIVE_AI,
    MONSTER_EXTRACTOR_SYSTEM_PROMPT,
    OUTPUT_CHUNKS_DIR,
)
from core.utils import MonsterProfile, clean_reasoning_response, generate_with_retry, scrape_wiki_text

MONSTER_TARGETS_FILE = os.environ.get("MONSTER_TARGETS_FILE", "monster_targets.txt")
MONSTER_OUTPUT_DIR = os.path.join(OUTPUT_CHUNKS_DIR, "monsters")


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>| ]', "_", name).strip("_")


def extract_monster_page(url, name, active_ai=None):
    if active_ai is None:
        active_ai = ACTIVE_AI

    os.makedirs(MONSTER_OUTPUT_DIR, exist_ok=True)
    safe_name = sanitize_filename(name)

    print(f"\n{'='*60}")
    print(f"Monster target: {name} → {url}")
    print(f"{'='*60}")

    raw_text = scrape_wiki_text(url, max_chars=30000)
    if not raw_text:
        print("  Scrape failed. Skipping.")
        return False

    user_prompt = f"Extract the complete monster stat block from this Weebly page:\n\n{raw_text}"

    try:
        raw_response = generate_with_retry(
            active_ai,
            MONSTER_EXTRACTOR_SYSTEM_PROMPT,
            user_prompt,
            response_format=MonsterProfile,
        )

        raw_response = clean_reasoning_response(raw_response)
        validated = MonsterProfile.model_validate_json(raw_response)
        payload = validated.model_dump(by_alias=True)

        safe_path = os.path.join(MONSTER_OUTPUT_DIR, f"monster_{safe_name}.json")
        with open(safe_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        print(f"  Saved {safe_path}")
        print(f"  {validated.Name}: HP={validated.MaxHP} MP={validated.MaxMP} "
              f"EXP={validated.Experience} GOLD={validated.Gold} "
              f"Stratum={validated.Stratum} Abilities={len(validated.Abilities)}")
        return True

    except ValidationError as ve:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
        console = Console()
        error_text = Text()
        error_text.append("Schema Validation Error:\n\n", style="bold red")
        error_text.append(str(ve), style="yellow")
        error_text.append("\n\nRaw Response was:\n", style="bold cyan")
        error_text.append(str(raw_response), style="white")
        panel = Panel(error_text, title="Schema Validation Failed", border_style="red")
        console.print(panel)

        error_path = os.path.join(MONSTER_OUTPUT_DIR, f"monster_{safe_name}_ERROR.txt")
        with open(error_path, "w", encoding="utf-8") as f:
            f.write(f"Validation Error:\n{str(ve)}\n\nRaw Response:\n{raw_response}")
        return False

    except Exception as e:
        print(f"  Pipeline error: {e}")
        error_path = os.path.join(MONSTER_OUTPUT_DIR, f"monster_{safe_name}_ERROR.txt")
        with open(error_path, "w", encoding="utf-8") as f:
            f.write(f"Pipeline Error: {e}")
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Monster stat block extractor for Shota×Monsters 2 Weebly pages")
    parser.add_argument("--engine", type=str, choices=["local", "gemini", "featherless"], default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--target", type=str, default=None, help="Process a single target: Name|URL")
    args = parser.parse_args()

    from config.settings import get_ai_provider
    active_ai = get_ai_provider(engine_name=args.engine, model_name=args.model)

    if args.target:
        if "|" in args.target:
            name, url = args.target.split("|", 1)
        else:
            name, url = "", args.target
        success = extract_monster_page(url.strip(), name.strip(), active_ai=active_ai)
        exit(0 if success else 1)

    targets = []
    try:
        with open(MONSTER_TARGETS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "|" in line:
                    name, url = line.split("|", 1)
                    targets.append((name.strip(), url.strip()))
                else:
                    targets.append(("", line.strip()))
    except FileNotFoundError:
        print(f"Targets file not found: {MONSTER_TARGETS_FILE}")
        exit(1)

    if not targets:
        print(f"The targets file '{MONSTER_TARGETS_FILE}' is empty.")
        exit(0)

    completed_log = "completed_monsters.txt"
    if not os.path.exists(completed_log):
        with open(completed_log, "w", encoding="utf-8") as f:
            pass

    completed = set()
    with open(completed_log, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                completed.add(line)

    print(f"Bootstrapping monster extraction for {len(targets)} targets...\n")
    for name, url in targets:
        if url in completed:
            print(f"  Skipping already completed: {url}")
            continue

        success = extract_monster_page(url, name, active_ai=active_ai)
        if success:
            with open(completed_log, "a", encoding="utf-8") as f:
                f.write(url + "\n")
            completed.add(url)

        time.sleep(random.uniform(4, 8))

    print(f"\nDone. Output in {MONSTER_OUTPUT_DIR}/")
