import argparse
import os
import subprocess
import sys
from pathlib import Path

# Resolve absolute path to the project root directory
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Use the virtual environment Python interpreter if available
VENV_PYTHON = BASE_DIR / "venv" / "bin" / "python"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)


def run_sub_ingestor(script_name, *args):
    """
    Launches a sub-ingestor script with the provided CLI arguments.
    """
    script_path = BASE_DIR / script_name
    cmd = [str(VENV_PYTHON), str(script_path)] + list(args)
    print(f"\n🚀 Engaging Ingestor: {script_name} {' '.join(args)}")
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ {script_name} execution completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {script_name} failed with exit code {e.returncode}.")
        return False
    except Exception as e:
        print(f"❌ Unexpected error launching {script_name}: {e}")
        return False


def is_url(path):
    return path.startswith("http://") or path.startswith("https://")


def classify_and_route(input_source, model=None, engine=None):
    """
    Polymorphically routes a single input source to the appropriate ingestor.
    """
    # 1. URL Ingestion
    if is_url(input_source):
        print(f"🌐 Input Classified: Web Target URL -> {input_source}")
        # Note: extract-web.py reads from targets.txt. We can temporarily mock/append
        # or call it if it accepts custom args. Since extract-web reads targets.txt,
        # we can temporarily write the URL to a temp targets file or pass arguments.
        # Let's write the URL to a temp targets.txt if needed, or update targets.txt.
        # For simplicity, we can append to targets.txt and run extract-web.py
        targets_file = BASE_DIR / "targets.txt"
        already_present = False
        if targets_file.exists():
            with open(targets_file, encoding="utf-8") as f:
                content = f.read()
                if input_source in content:
                    already_present = True
        if not already_present:
            with open(targets_file, "a", encoding="utf-8") as f:
                f.write(f"\n{input_source}\n")
        
        args = []
        if model:
            args.extend(["--model", model])
        if engine:
            args.extend(["--engine", engine])
        run_sub_ingestor("extract-web.py", *args)

    # 2. PDF Ingestion
    elif input_source.lower().endswith(".pdf"):
        print(f"📄 Input Classified: PDF Document -> {input_source}")
        # Copy the PDF to input_pdfs/ hopper if it is located elsewhere
        input_pdfs_dir = BASE_DIR / "input_pdfs"
        input_pdfs_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = Path(input_source).resolve()
        if pdf_path.exists() and pdf_path.parent.resolve() != input_pdfs_dir.resolve():
            import shutil
            shutil.copy(pdf_path, input_pdfs_dir / pdf_path.name)
            print(f"  📂 Copied PDF to hopper: {input_pdfs_dir / pdf_path.name}")
        
        args = []
        if model:
            args.extend(["--model", model])
        if engine:
            args.extend(["--engine", engine])
        run_sub_ingestor("extract-pdf.py", *args)

    # 3. Vision Ingestion
    elif input_source.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        print(f"🖼️ Input Classified: Image Panel -> {input_source}")
        input_images_dir = BASE_DIR / "input_images"
        input_images_dir.mkdir(parents=True, exist_ok=True)
        img_path = Path(input_source).resolve()
        if img_path.exists() and img_path.parent.resolve() != input_images_dir.resolve():
            import shutil
            shutil.copy(img_path, input_images_dir / img_path.name)
            print(f"  📂 Copied Image to hopper: {input_images_dir / img_path.name}")
        
        args = []
        if model:
            args.extend(["--model", model])
        if engine:
            args.extend(["--engine", engine])
        # Ask for reading direction (default LTR)
        args.extend(["--direction", "LTR"])
        run_sub_ingestor("extract-vision.py", *args)

    # 4. Manga OCR Ingestion
    elif os.path.isdir(input_source) and ("_ocr" in input_source or any(d == "_ocr" for d in os.listdir(input_source)) or "_ocr" in [p.name for p in Path(input_source).rglob("_ocr")]):
        print(f"📖 Input Classified: Manga OCR Directory -> {input_source}")
        input_manga_dir = BASE_DIR / "input_manga_ocr"
        input_manga_dir.mkdir(parents=True, exist_ok=True)
        # If the folder is not in the hopper, warn user or process directly.
        # Since extract-manga.py scans INPUT_DIR recursively, we can link/copy or update extract-manga.py
        # to accept target directory overrides, or just copy/process.
        # For simplicity, we trigger extract-manga.py.
        args = []
        if model:
            args.extend(["--model", model])
        run_sub_ingestor("extract-manga.py", *args)

    # 5. JSON Import Ingestion
    elif input_source.lower().endswith(".lorebook.json") or input_source.lower().endswith(".json"):
        print(f"📦 Input Classified: SillyTavern JSON -> {input_source}")
        input_json_dir = BASE_DIR / "input_json"
        input_json_dir.mkdir(parents=True, exist_ok=True)
        json_path = Path(input_source).resolve()
        if json_path.exists() and json_path.parent.resolve() != input_json_dir.resolve():
            import shutil
            shutil.copy(json_path, input_json_dir / json_path.name)
            print(f"  📂 Copied JSON to hopper: {input_json_dir / json_path.name}")
        run_sub_ingestor("import-json.py", str(input_json_dir / json_path.name))

    else:
        print(f"⚠️ Unrecognized input type: '{input_source}'")
        print("Please supply a valid URL, .pdf file, image file, Mokuro OCR folder path, or SillyTavern JSON file.")


def run_hopper_scan(model=None, engine=None):
    """
    Performs a workspace-wide sweep of all default input hoppers and processes them.
    """
    print("\n🔍 Scanning Active Hoppers...")
    
    # 1. Check PDFs recursively
    input_pdfs_dir = BASE_DIR / "input_pdfs"
    pdfs = []
    if input_pdfs_dir.exists():
        for p in input_pdfs_dir.rglob("*.pdf"):
            pdfs.append(p)
        for p in input_pdfs_dir.rglob("*.PDF"):
            pdfs.append(p)
    pdfs = sorted(list(set(pdfs)))
    
    # 2. Check Web targets
    targets_file = BASE_DIR / "targets.txt"
    web_targets = []
    if targets_file.exists():
        with open(targets_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Check completed log
                    completed_log = BASE_DIR / "completed_targets.txt"
                    completed = set()
                    if completed_log.exists():
                        completed = set(completed_log.read_text(encoding="utf-8").splitlines())
                    url = line.split('|', 1)[1].strip() if '|' in line else line
                    if url not in completed:
                        web_targets.append(url)
                        
    # 3. Check Images recursively
    input_images_dir = BASE_DIR / "input_images"
    images = []
    if input_images_dir.exists():
        for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp', '*.bmp']:
            images.extend(input_images_dir.rglob(ext))
            images.extend(input_images_dir.rglob(ext.upper()))
    images = sorted(list(set(images)))
            
    # 4. Check Manga OCR
    input_manga_dir = BASE_DIR / "input_manga_ocr"
    ocr_dirs = []
    if input_manga_dir.exists():
        for root, dirs, _files in os.walk(input_manga_dir):
            for d in dirs:
                if d == "_ocr":
                    ocr_dirs.append(Path(root) / d)

    # 5. Check JSON Import Hopper
    input_json_dir = BASE_DIR / "input_json"
    json_files = []
    if input_json_dir.exists():
        for j in input_json_dir.rglob("*.json"):
            json_files.append(j)
    json_files = sorted(list(set(json_files)))

    print("\n📦 ACTIVE HOPPERS DETECTED:")
    print(f"  - 📄 PDFs: {len(pdfs)} files found (in input_pdfs/)")
    print(f"  - 🌐 Web: {len(web_targets)} pending targets found (in targets.txt)")
    print(f"  - 🖼️ Images: {len(images)} files found (in input_images/)")
    print(f"  - 📖 Manga: {len(ocr_dirs)} active OCR folders found (in input_manga_ocr/)")
    print(f"  - 📦 JSON Import: {len(json_files)} files found (in input_json/)")
    print("==========================================")

    processed_any = False

    # Execute sequentially if items found
    if pdfs:
        print("\n⚡ Processing PDF Hopper Queue...")
        args = []
        if model:
            args.extend(["--model", model])
        if engine:
            args.extend(["--engine", engine])
        run_sub_ingestor("extract-pdf.py", *args)
        processed_any = True

    if web_targets:
        print("\n⚡ Processing Web Target Hopper Queue...")
        args = []
        if model:
            args.extend(["--model", model])
        if engine:
            args.extend(["--engine", engine])
        run_sub_ingestor("extract-web.py", *args)
        processed_any = True

    if images:
        print("\n⚡ Processing Image Panel Hopper Queue...")
        args = []
        if model:
            args.extend(["--model", model])
        if engine:
            args.extend(["--engine", engine])
        # Default direction manga or Western. Let's run LTR or prompt.
        args.extend(["--direction", "LTR"])
        run_sub_ingestor("extract-vision.py", *args)
        processed_any = True

    if ocr_dirs:
        print("\n⚡ Processing Manga OCR Hopper Queue...")
        args = []
        if model:
            args.extend(["--model", model])
        run_sub_ingestor("extract-manga.py", *args)
        processed_any = True

    if json_files:
        print("\n⚡ Processing JSON Import Hopper Queue...")
        run_sub_ingestor("import-json.py")
        processed_any = True

    if not processed_any:
        print("\n📭 All input hoppers are currently empty. No pending data detected.")


def main():
    parser = argparse.ArgumentParser(description="Unified Ingestion Gateway Router for the Lore Matrix")
    parser.add_argument("input", nargs="?", default=None, help="Optional direct input source (URL, PDF file path, Image file path, or Manga OCR directory)")
    parser.add_argument("--model", type=str, default=None, help="Target LLM model override")
    parser.add_argument("--engine", type=str, choices=["local", "gemini", "featherless"], default=None, help="AI provider engine to use")
    args = parser.parse_args()

    if args.input:
        classify_and_route(args.input, model=args.model, engine=args.engine)
    else:
        run_hopper_scan(model=args.model, engine=args.engine)


if __name__ == "__main__":
    main()
