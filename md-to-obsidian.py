import glob
import os
import random
import time
from pathlib import Path

from config.settings import ACTIVE_AI, COMPILED_VAULT_DIR, COMPILER_SYSTEM_PROMPT, RAW_VAULT_DIR


def run_forge(input_folder, output_folder, active_ai=None):
    if active_ai is None:
        active_ai = ACTIVE_AI
        
    # Setup directories
    source_dir = Path(input_folder)
    target_dir = Path(output_folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Grab all raw markdown files recursively
    md_files = glob.glob(os.path.join(source_dir, "**", "*.md"), recursive=True)
    
    print(f"🔨 Obsidian Forge Ignited. Found {len(md_files)} raw notes to compile.")
    
    for file_path in md_files:
        path_obj = Path(file_path)
        
        # Preserve the internal folder structure!
        relative_path = path_obj.relative_to(source_dir)
        output_path = target_dir / relative_path
        
        if output_path.exists():
            print(f"  ⏭️ Skipping already compiled file: {path_obj.name}")
            continue
            
        print(f"  -> Compiling: {path_obj.name}...")
        
        with open(file_path, encoding='utf-8') as f:
            raw_content = f.read()
            
        for attempt in range(3):
            try:
                # Pass the raw text through the compiler
                # The compile_note equivalent in engines is generate()
                compiled_content = active_ai.generate(COMPILER_SYSTEM_PROMPT, raw_content)
                
                # Strip any leading conversational text the local model might have hallucinated
                if "---" in compiled_content:
                    compiled_content = "---" + compiled_content.split("---", 1)[1]
                
                # Ensure the specific sub-folder exists in the target directory before saving
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(compiled_content)
                    
                print("  ✅ Forged successfully!")
                break
                
            except Exception as e:
                if attempt < 2:
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    print(f"  ⚠️ Attempt {attempt + 1}/3 failed for {path_obj.name}: {e}. Retrying in {backoff:.2f}s...")
                    time.sleep(backoff)
                else:
                    print(f"  ❌ Failed compiling {path_obj.name} after 3 attempts. Last error: {e}")
                    break
            
        # Brief pause to prevent overheating
        time.sleep(random.uniform(1.5, 3.0))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Obsidian Forge Compiler for the Lore Matrix")
    parser.add_argument("--engine", type=str, choices=["local", "gemini", "featherless"], default=None, help="AI provider engine to use")
    parser.add_argument("--model", type=str, default=None, help="Model name override")
    args = parser.parse_args()
    
    from config.settings import get_ai_provider
    active_ai = get_ai_provider(engine_name=args.engine, model_name=args.model)
    
    print(f"Initializing Wiki Compiler using: {active_ai.__class__.__name__} ({active_ai.model_name})...\n")
    run_forge(RAW_VAULT_DIR, COMPILED_VAULT_DIR, active_ai=active_ai)
    print("\n🎉 All notes have been compiled and are ready to drop into Obsidian!")
