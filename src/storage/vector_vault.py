import contextlib
import datetime
import glob
import hashlib
import json
import logging
import os
import sys

# Ensure project root is in sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Suppress ChromaDB/ONNX/HuggingFace verbose logging for silent database initialization
logging.getLogger("chromadb").setLevel(logging.ERROR)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Import chromadb
import chromadb
from chromadb.utils import embedding_functions


def get_chroma_client():
    db_path = os.path.join(project_root, "storage", "chroma_vault")
    os.makedirs(db_path, exist_ok=True)
    # Silent initialization
    with open(os.devnull, "w") as f, contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
        client = chromadb.PersistentClient(path=db_path)
    return client

def get_collection(name="narrative_tropes"):
    client = get_chroma_client()
    # Utilizing Chroma's default local ONNX MiniLM embedding function
    # It executes fully locally on the host machine.
    ef = embedding_functions.DefaultEmbeddingFunction()
    
    with open(os.devnull, "w") as f, contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
        collection = client.get_or_create_collection(
            name=name,
            embedding_function=ef
        )
    return collection

def ingest_processed_tokens():
    """
    Reads intermediate trope chunk JSONs, performs zero-duplication checks,
    and indexes them in the local persistent ChromaDB collection.
    """
    tokens_dir = os.path.join(project_root, "processed_data", "trope_tokens")
    
    if not os.path.exists(tokens_dir):
        print(f"❌ Vault Ingestion Failed: Directory '{tokens_dir}' does not exist.")
        return
        
    input_files = glob.glob(os.path.join(tokens_dir, "*.json"))
    if not input_files:
        print("📭 No processed trope tokens found to ingest.")
        return
        
    print(f"🎬 Initializing Vector Vault Ingestion for {len(input_files)} chunk files...")
    
    try:
        collection = get_collection()
        print("🎯 Collection Initialized")
    except Exception as ce:
        print(f"❌ Vault Ingestion Failed: Collection initialization failed: {ce}")
        return
        
    success_count = 0
    duplicate_count = 0
    
    ingestion_timestamp = datetime.datetime.now(datetime.UTC).isoformat()
    
    for file_path in input_files:
        filename = os.path.basename(file_path)
        try:
            with open(file_path, encoding='utf-8') as f:
                chunk_data = json.load(f)
                
            title = chunk_data.get("Trope_Title", "")
            namespace = chunk_data.get("Namespace", "Main")
            clean_content = chunk_data.get("Clean_Content", "")
            source_url = chunk_data.get("Source_URL", "")
            
            if not title or not clean_content:
                print(f"⚠️ Warning: Missing required fields in {filename}. Skipping.")
                continue
                
            # Create a unique chunk ID (fingerprint) using MD5 of content or file identifier
            # to guarantee idempotence and prevent duplicate insertions
            # E.g., title + MD5 hash of clean_content
            content_hash = hashlib.md5(clean_content.encode('utf-8')).hexdigest()[:12]
            chunk_id = f"{title.lower().replace(' ', '_')}_{content_hash}"
            
            # Zero-Duplication Check: Query collection for this unique ID
            existing = collection.get(ids=[chunk_id])
            if existing and existing.get("ids") and len(existing["ids"]) > 0:
                print(f"⚠️ Duplicate Chunk Skipped: {title} ({chunk_id})")
                duplicate_count += 1
                continue
                
            # Metadata Payload
            metadata = {
                "Trope_Title": title,
                "Namespace": namespace,
                "Source_URL": source_url,
                "Ingestion_Timestamp": ingestion_timestamp
            }
            
            # Persist vector entry
            collection.add(
                documents=[clean_content],
                metadatas=[metadata],
                ids=[chunk_id]
            )
            print(f"🎯 Trope Vaulted: {title} (ID: {chunk_id})")
            success_count += 1
            
        except Exception as e:
            print(f"❌ Vault Ingestion Failed for {filename}: {e}")
            
    print(f"\n✅ Ingestion Sync complete: {success_count} vaulted, {duplicate_count} skipped.")

def query_trope(query_text: str, n_results: int = 3, collection_name: str = "narrative_tropes"):
    """
    Queries the persistent ChromaDB vault for the highest-scoring vector matches.
    Returns clean payload blocks with lineage prefixes intact.
    """
    try:
        collection = get_collection(name=collection_name)
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results
        )
        
        matches = []
        if results and results.get("documents") and len(results["documents"]) > 0:
            docs = results["documents"][0]
            metadatas = results["metadatas"][0] if results.get("metadatas") else [None] * len(docs)
            distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
            ids = results["ids"][0] if results.get("ids") else ["N/A"] * len(docs)
            
            for i in range(len(docs)):
                matches.append({
                    "id": ids[i],
                    "content": docs[i],
                    "metadata": metadatas[i],
                    "distance": distances[i]
                })
        return matches
    except Exception as e:
        print(f"❌ Extraction Failed: Query execution failed: {e}")
        return []

def run_query_wizard():
    print("\n🔍 --- Intent-Driven Trope Search Wizard ---")
    query_text = input("Enter search query (e.g. 'prophesied hero' or 'Xanatos Gambit'): ").strip()
    if not query_text:
        print("⚠️ Query cannot be empty.")
        return
        
    n_results_str = input("Number of results to retrieve (default: 3): ").strip()
    n_results = 3
    if n_results_str.isdigit():
        n_results = int(n_results_str)
        
    print(f"\nSearching vault for semantics matching: '{query_text}'...")
    results = query_trope(query_text, n_results=n_results)
    
    if not results:
        print("📭 No matching tropes found in the vector vault.")
        return
        
    print(f"\n=================== FOUND {len(results)} MATCHES ===================")
    for idx, match in enumerate(results, 1):
        metadata = match["metadata"] or {}
        dist = match["distance"]
        # Convert distance to a similarity score for presentation
        score = 1.0 - dist if dist <= 1.0 else 0.0
        print(f"\n[{idx}] Score: {score:.4f} | ID: {match['id']}")
        print(f"Lineage Details: URL={metadata.get('Source_URL', 'N/A')}")
        print("Raw Text Block:")
        print("----------------------------------------------------------------------")
        print(match["content"])
        print("----------------------------------------------------------------------")

def run_submenu():
    while True:
        print("\n==========================================")
        print("  Trope Vector Vault Submenu")
        print("==========================================")
        print("1. Ingest/Sync Processed Tropes to Vault")
        print("2. Search/Query Narrative Tropes")
        print("3. Return to Main Menu")
        print("==========================================")
        choice = input("Enter choice (1-3): ").strip()
        
        if choice == '1':
            ingest_processed_tokens()
        elif choice == '2':
            run_query_wizard()
        elif choice == '3':
            break
        else:
            print("⚠️ Invalid choice. Please enter 1, 2, or 3.")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Trope Vector Vault Engine")
    parser.add_argument("command", type=str, nargs="?", choices=["ingest", "query"], help="Command to run")
    parser.add_argument("--query", type=str, default="", help="Query semantics to search")
    parser.add_argument("--limit", type=int, default=3, help="Max results to return")
    args = parser.parse_args()
    
    if args.command == "ingest":
        ingest_processed_tokens()
    elif args.command == "query":
        if not args.query:
            print("❌ Error: --query argument required for query command.")
            sys.exit(1)
        results = query_trope(args.query, n_results=args.limit)
        # Output clean json for downstream compilers
        print(json.dumps(results, indent=4))
    else:
        run_submenu()

if __name__ == "__main__":
    main()
