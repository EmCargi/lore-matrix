import datetime
import glob
import json
import os
import re
import sys
import tempfile

from pydantic import BaseModel, Field

# Ensure project root is in sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Established pipeline imports
from config.settings import get_ai_provider


# Schema enforcement for transformed chunks (narrative tokens)
class TropeChunkModel(BaseModel):
    Trope_Title: str = Field(..., description="The parent trope title")
    Namespace: str = Field(..., description="The parent namespace")
    Clean_Content: str = Field(..., description="The cleaned chunk content, including lineage prefix")
    Source_URL: str = Field(..., description="The lineage source URL")
    Generation_Timestamp: str = Field(..., description="Timestamp of generation (ISO 8601 format)")

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>| ]', "_", name).strip("_")

def clean_text_programmatic(text):
    if not text:
        return ""
    # Strip HTML tags
    text = re.sub(r'<[^>]*>', '', text)
    # Strip TV Tropes / Wiki link brackets but keep the text
    # e.g., [[Main/TheChosenOne|Chosen One]] -> Chosen One
    # e.g., [[TheChosenOne]] -> TheChosenOne
    text = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', text)
    # Strip external links
    text = re.sub(r'https?://\S+', '', text)
    # Clean up double spacing and formatting anomalies
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def clean_text_llm(text, active_ai):
    system_prompt = (
        "You are an expert editor and database archivist.\n"
        "Your task is to refine the narrative trope definition provided below. "
        "Remove all casual wiki slop, conversational commentary, forum-style remarks, "
        "and formatting artifacts. Output ONLY the polished, high-density, formal definition "
        "of the trope, preserving all core narrative meaning. Do not write any introduction or explanation."
    )
    user_prompt = f"Raw definition to clean:\n\n{text}"
    try:
        cleaned = active_ai.generate(system_prompt, user_prompt)
        cleaned = cleaned.strip()
        # Clean up any potential markdown code fences wrapped by model
        cleaned = re.sub(r'^```json\s*', '', cleaned)
        cleaned = re.sub(r'^```\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        return cleaned.strip()
    except Exception as e:
        print(f"⚠️ LLM cleaning failed: {e}. Falling back to programmatic cleanup.")
        return clean_text_programmatic(text)

def snippet_chunker(definition, examples, max_chars=800):
    """
    Groups definition and examples into distinct text segments (chunks)
    under the max_chars limit to keep core structural definition separated
    from specific media examples.
    """
    chunks = []
    
    # 1. Add Definition chunks
    if len(definition) <= max_chars:
        chunks.append(f"Definition: {definition}")
    else:
        # Split definition into sentences
        sentences = re.split(r'(?<=[.!?])\s+', definition)
        current_chunk = []
        current_len = 0
        for sentence in sentences:
            if current_len + len(sentence) + 1 > max_chars:
                if current_chunk:
                    chunks.append("Definition: " + " ".join(current_chunk))
                current_chunk = [sentence]
                current_len = len(sentence)
            else:
                current_chunk.append(sentence)
                current_len += len(sentence) + 1
        if current_chunk:
            chunks.append("Definition: " + " ".join(current_chunk))
            
    # 2. Add Examples chunks (decoupled)
    current_examples_chunk = []
    current_examples_len = 0
    for example in examples:
        example_str = f"- {example}"
        if current_examples_len + len(example_str) + 1 > max_chars:
            if current_examples_chunk:
                chunks.append("Examples:\n" + "\n".join(current_examples_chunk))
            current_examples_chunk = [example_str]
            current_examples_len = len(example_str)
        else:
            current_examples_chunk.append(example_str)
            current_examples_len += len(example_str) + 1
    if current_examples_chunk:
        chunks.append("Examples:\n" + "\n".join(current_examples_chunk))
        
    return chunks

def atomic_write(data, target_path):
    target_dir = os.path.dirname(target_path)
    os.makedirs(target_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=target_dir, delete=False, encoding='utf-8') as tf:
        json.dump(data, tf, indent=4)
        temp_name = tf.name
    try:
        os.replace(temp_name, target_path)
    except Exception as e:
        if os.path.exists(temp_name):
            os.remove(temp_name)
        raise e

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Trope ETL Forge (Meta Archivist)")
    parser.add_argument("--engine", type=str, choices=["local", "gemini", "featherless"], default=None, help="AI provider engine to use")
    parser.add_argument("--model", type=str, default=None, help="Model name override")
    args = parser.parse_args()
    
    # Initialize Provider
    active_ai = get_ai_provider(engine_name=args.engine, model_name=args.model)
    
    # Paths
    input_dir = os.path.join(project_root, "output", "tropes")
    output_dir = os.path.join(project_root, "processed_data", "trope_tokens")
    journal_dir = os.path.join(project_root, "journal")
    
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(journal_dir, exist_ok=True)
    
    # Metric counters
    files_parsed = 0
    tokens_generated = 0
    validation_failures = 0
    parsing_details = []
    
    input_files = glob.glob(os.path.join(input_dir, "*.json"))
    print(f"🚀 Starting ETL Forge on {len(input_files)} raw trope files...")
    
    for file_path in input_files:
        filename = os.path.basename(file_path)
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
                
            # Ingestion
            title = data.get("Trope_Title", "")
            namespace = data.get("Namespace", "Main")
            raw_definition = data.get("Definition", "")
            examples = data.get("Examples", [])
            source_url = data.get("Source_URL", "")
            
            if not title or not raw_definition:
                print(f"⚠️ Warning: Missing required fields in {filename}. Skipping.")
                validation_failures += 1
                parsing_details.append({"file": filename, "status": "FAILED", "error": "Missing Title or Definition"})
                continue
                
            files_parsed += 1
            print(f"📖 Processing: '{title}' ({namespace})")
            
            # Specificity Pass (Cleaning)
            cleaned_definition = clean_text_llm(raw_definition, active_ai)
            
            # Decoupling & Segmenting
            segments = snippet_chunker(cleaned_definition, examples)
            
            # Write segments
            prefix = f"[Trope: {title} | Namespace: {namespace}]"
            gen_timestamp = datetime.datetime.now(datetime.UTC).isoformat()
            
            trope_tokens_written = 0
            for idx, segment in enumerate(segments, 1):
                # Lineage Injection Chunking
                clean_content_with_lineage = f"{prefix} {segment}"
                
                # Validation payload
                chunk_payload = {
                    "Trope_Title": title,
                    "Namespace": namespace,
                    "Clean_Content": clean_content_with_lineage,
                    "Source_URL": source_url,
                    "Generation_Timestamp": gen_timestamp
                }
                
                try:
                    # Validate against Pydantic schema
                    validated_chunk = TropeChunkModel(**chunk_payload)
                    
                    # Target file naming
                    safe_title = sanitize_filename(title)
                    target_file = os.path.join(output_dir, f"{safe_title}_chunk_{idx:03d}.json")
                    
                    # Atomic storage
                    atomic_write(validated_chunk.model_dump(by_alias=True), target_file)
                    tokens_generated += 1
                    trope_tokens_written += 1
                    
                except Exception as ve:
                    print(f"  ❌ Validation failed for chunk {idx} of '{title}': {ve}")
                    validation_failures += 1
            
            parsing_details.append({
                "file": filename,
                "trope": title,
                "status": "SUCCESS",
                "chunks_created": trope_tokens_written
            })
            
        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            validation_failures += 1
            parsing_details.append({"file": filename, "status": "ERROR", "error": str(e)})
            
    # Dev Journal Pass (Lineage & Auditing Report)
    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d_%H-%M")
    report_filename = f"transform_summary_{timestamp_str}.md"
    report_path = os.path.join(journal_dir, report_filename)
    
    report_content = f"""# Trope ETL Forge: Transformation Audit Report

**Run Timestamp**: {now.isoformat()}
**Engine Used**: {args.engine or "default"}
**Model Used**: {args.model or "default"}

## 📊 Summary Metrics

| Metric | Count |
| :--- | :--- |
| **Files Scanned** | {len(input_files)} |
| **Files Successfully Parsed** | {files_parsed} |
| **Narrative Tokens (Chunks) Generated** | {tokens_generated} |
| **Validation / Processing Failures** | {validation_failures} |

## 🔍 Detail Audit Log

| File | Trope Title | Status | Result / Error |
| :--- | :--- | :--- | :--- |
"""

    for detail in parsing_details:
        status = detail["status"]
        status_emoji = "✅" if status == "SUCCESS" else "❌"
        file_name = detail["file"]
        trope_title = detail.get("trope", "N/A")
        
        if status == "SUCCESS":
            result_str = f"Generated {detail['chunks_created']} chunks"
        else:
            result_str = detail.get("error", "Unknown error")
            
        report_content += f"| {file_name} | {trope_title} | {status_emoji} {status} | {result_str} |\n"
        
    try:
        with open(report_path, 'w', encoding='utf-8') as rf:
            rf.write(report_content)
        print(f"\n📝 Audit report successfully generated at journal/{report_filename}")
    except Exception as re:
        print(f"⚠️ Warning: Could not write transform summary report to {report_path}: {re}")

if __name__ == "__main__":
    main()
