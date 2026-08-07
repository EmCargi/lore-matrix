import json
import shutil
import sys
from pathlib import Path

# Try to import cv2 and easyocr
try:
    import cv2
except ImportError:
    print("❌ Error: opencv-python-headless is not installed. Run `pip install opencv-python-headless` first.")
    sys.exit(1)

try:
    import easyocr
except ImportError:
    print("❌ Error: easyocr is not installed. Run `pip install easyocr` first.")
    sys.exit(1)

from pydantic import ValidationError

from config.settings import (
    ACTIVE_AI,
    INPUT_IMAGES_DIR,
    OUTPUT_CHUNKS_DIR,
    PROCESSED_IMAGES_DIR,
    VISION_EXTRACTOR_SYSTEM_PROMPT,
)
from core.utils import NarrativeLog, clean_reasoning_response, generate_with_retry


def group_and_sort_bounding_boxes(results, img_width, img_height, direction='LTR'):
    """
    Filters margin/noise and clusters related text boxes into dialogue blocks in reading order.
    """
    parsed_boxes = []
    
    # Define margin threshold (2% of the image dimension)
    margin_w = img_width * 0.02
    margin_h = img_height * 0.02
    
    # 1. Parse and filter boxes
    for bbox, text, conf in results:
        # Confidence threshold filter
        if conf < 0.35:
            continue
            
        x_min = float(min(pt[0] for pt in bbox))
        x_max = float(max(pt[0] for pt in bbox))
        y_min = float(min(pt[1] for pt in bbox))
        y_max = float(max(pt[1] for pt in bbox))
        
        width = x_max - x_min
        height = y_max - y_min
        
        # Noise filter for negligible dimensions
        if width < 5 or height < 5:
            continue
            
        # Margin checking
        in_margin = (x_min < margin_w or x_max > img_width - margin_w or 
                     y_min < margin_h or y_max > img_height - margin_h)
                     
        is_metadata = False
        if in_margin:
            stripped = text.strip()
            # Likely page numbers, running headers/footers, or scan artifacts
            if stripped.isdigit() or len(stripped) < 4 or stripped.lower().startswith("page"):
                is_metadata = True
                
        if is_metadata:
            print(f"  [FILTERED] Margins/Noise: '{text}' at [[{x_min:.1f}, {y_min:.1f}], [{x_max:.1f}, {y_max:.1f}]]")
            continue
            
        parsed_boxes.append({
            'x_min': x_min,
            'x_max': x_max,
            'y_min': y_min,
            'y_max': y_max,
            'text': text,
            'conf': conf
        })
        
    if not parsed_boxes:
        return []
        
    # Calculate average line height to establish spatial scaling
    avg_height = sum(b['y_max'] - b['y_min'] for b in parsed_boxes) / len(parsed_boxes)
    
    # 2. spatial clustering using connected components (Union-Find)
    n = len(parsed_boxes)
    parent = list(range(n))
    
    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]
        
    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j
            
    # Proximity thresholds normalized by average line height
    vertical_threshold = 2.0 * avg_height
    horizontal_threshold = 3.0 * avg_height
    
    for i in range(n):
        for j in range(i + 1, n):
            a = parsed_boxes[i]
            b = parsed_boxes[j]
            
            # Compute gaps (overlap means gap is 0)
            y_gap = max(0.0, max(a['y_min'], b['y_min']) - min(a['y_max'], b['y_max']))
            x_gap = max(0.0, max(a['x_min'], b['x_min']) - min(a['x_max'], b['x_max']))
            
            if y_gap <= vertical_threshold and x_gap <= horizontal_threshold:
                union(i, j)
                
    # Group boxes by their connected component root
    from collections import defaultdict
    groups = defaultdict(list)
    for i in range(n):
        root = find(i)
        groups[root].append(parsed_boxes[i])
        
    # 3. Sort text inside each group, and sort the groups themselves
    grouped_segments = []
    for _root, g_boxes in groups.items():
        # Compute group boundaries
        g_x_min = min(b['x_min'] for b in g_boxes)
        g_x_max = max(b['x_max'] for b in g_boxes)
        g_y_min = min(b['y_min'] for b in g_boxes)
        g_y_max = max(b['y_max'] for b in g_boxes)
        
        # Sort boxes within the group: primarily top-to-bottom, secondarily left-to-right (LTR) or right-to-left (RTL)
        if direction == 'RTL':
            sorted_g_boxes = sorted(g_boxes, key=lambda b: (round(b['y_min'] / (0.5 * avg_height)), -b['x_max']))
        else:
            sorted_g_boxes = sorted(g_boxes, key=lambda b: (round(b['y_min'] / (0.5 * avg_height)), b['x_min']))
        
        # Combine text segments in reading order
        combined_text = " ".join(b['text'] for b in sorted_g_boxes)
        
        grouped_segments.append({
            'x_min': g_x_min,
            'x_max': g_x_max,
            'y_min': g_y_min,
            'y_max': g_y_max,
            'text': combined_text
        })
        
    # Sort groups in visual reading flow: top-to-bottom, left-to-right (LTR) or right-to-left (RTL)
    # Quantize y-coordinate to group horizontally aligned speech bubbles correctly
    if direction == 'RTL':
        # RTL Manga sorting: High X to Low X (hence -g['x_max'])
        grouped_segments = sorted(grouped_segments, key=lambda g: (round(g['y_min'] / (1.5 * avg_height)), -g['x_max']))
    else:
        # LTR Western sorting: Low X to High X
        grouped_segments = sorted(grouped_segments, key=lambda g: (round(g['y_min'] / (1.5 * avg_height)), g['x_min']))
    
    return grouped_segments


def run_vision_pipeline(image_path, reader, direction='LTR', context=None, active_ai=None, preprocess=False, binarize=False, deskew=False, debug_ocr=False):
    if active_ai is None:
        active_ai = ACTIVE_AI
        
    print(f"\n🚀 Initiating Multimodal Vision Harvesting for: {image_path.name}")
    print(f"  -> Selected direction: {direction}")
    if context:
        print(f"  -> Context: {context}")
    
    # 1. Load image and determine dimensions
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"❌ Error: Unable to read image file '{image_path}'")
        return False
        
    h, w = img.shape[:2]
    print(f"  -> Dimensions: {w}x{h}")
    
    # 2. Run Image Preprocessing if requested
    ocr_img = img
    if preprocess or binarize or deskew:
        print("  -> Applying image enhancement filters for OCR...")
        from core.image_processing import preprocess_image_for_ocr
        ocr_img = preprocess_image_for_ocr(
            img,
            binarize=binarize,
            denoise=preprocess,
            contrast=preprocess,
            deskew=deskew
        )
        h, w = ocr_img.shape[:2]
    
    # 3. Run EasyOCR detection & recognition
    print("  -> Scanning image for text segments...")
    results = reader.readtext(ocr_img)
    print(f"  -> EasyOCR detected {len(results)} raw bounding boxes.")
    
    # 3. Cluster boxes into readable dialogues
    grouped_segments = group_and_sort_bounding_boxes(results, w, h, direction=direction)
    if not grouped_segments:
        print("  ⚠️ No valid text segments remained after noise/margin filtering.")
        return False
        
    dialogues = [g['text'] for g in grouped_segments]
    
    print(f"  -> Clustered bounding boxes into {len(dialogues)} cohesive dialogue blocks:")
    for idx, text in enumerate(dialogues, 1):
        print(f"     [{idx}] {text}")
        
    # Draw OCR Debug Visualizations if requested
    if debug_ocr:
        debug_img = img.copy()
        for idx, g in enumerate(grouped_segments, 1):
            # Draw green bounding box rectangle
            cv2.rectangle(
                debug_img,
                (int(g['x_min']), int(g['y_min'])),
                (int(g['x_max']), int(g['y_max'])),
                (0, 255, 0),
                2
            )
            # Draw label box
            label = f"[{idx}]"
            (w_label, h_label), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            # Ensure background box doesn't go out of bounds at the top
            label_y = int(g['y_min'])
            cv2.rectangle(
                debug_img,
                (int(g['x_min']), label_y - h_label - 10 if label_y - h_label - 10 > 0 else 0),
                (int(g['x_min']) + w_label, label_y),
                (0, 255, 0),
                cv2.FILLED
            )
            # Draw index text
            cv2.putText(
                debug_img,
                label,
                (int(g['x_min']), label_y - 5 if label_y - 5 > 0 else 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 0),
                2
            )
        debug_dir = OUTPUT_CHUNKS_DIR / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / f"debug_{image_path.name}"
        cv2.imwrite(str(debug_path), debug_img)
        print(f"  🐞 Saved OCR debug visualization to: {debug_path}")
        
    # 4. format raw dialogues for LLM ingestion
    dialogue_input_str = "\n".join(f"{idx}. {text}" for idx, text in enumerate(dialogues, 1))
    
    raw_ocr_text = (
        f"Parse the following vision-derived text blocks chronologically according to the rules. "
        f"Generate the corresponding narrative logs matching the schema.\n\n"
        f"Parsed Image Texts:\n{dialogue_input_str}"
    )
    
    if context:
        user_prompt = f"[SCENE CONTEXT]: {context}\n\n[RAW OCR TEXT]:\n{raw_ocr_text}"
    else:
        user_prompt = raw_ocr_text
    
    # 5. Invoke AI endpoint via active_ai
    print(f"  -> Contacting LLM endpoint ({active_ai.model_name})...")
    try:
        raw_response = generate_with_retry(active_ai, VISION_EXTRACTOR_SYSTEM_PROMPT, user_prompt, response_format=NarrativeLog)
        
        # Strip reasoning tags (deepseek-r1) and any code fences, then validate
        raw_response = clean_reasoning_response(raw_response)
        validated_log = NarrativeLog.model_validate_json(raw_response)
        entries = validated_log.model_dump(by_alias=True).get("entries", [])
            
        # Ghost Node Sanitization (remap Speaker to "System/Environment" if Dialogue is empty)
        for entry in entries:
            if isinstance(entry, dict) and "Dialogue" in entry:
                dialogue_val = entry["Dialogue"]
                if dialogue_val is None or (isinstance(dialogue_val, str) and dialogue_val.strip() == ""):
                    entry["Dialogue"] = ""
                    entry["Speaker"] = "System/Environment"
                    
        final_payload = {"entries": entries}
            
        try:
            rel_path = image_path.relative_to(INPUT_IMAGES_DIR)
        except ValueError:
            rel_path = Path(image_path.name)
            
        rel_dir = rel_path.parent
        target_out_dir = OUTPUT_CHUNKS_DIR / rel_dir
        target_out_dir.mkdir(parents=True, exist_ok=True)
        
        safe_path = target_out_dir / f"vision_chunk_{image_path.stem}.json"
        with open(safe_path, 'w', encoding='utf-8') as f:
            json.dump(final_payload, f, indent=4)
            
        print(f"  ✅ Successfully compiled & saved structure to: {safe_path}")
        return True
        
    except ValidationError as e:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
        console = Console()
        error_text = Text()
        error_text.append("Schema Validation Error on Image ", style="bold red")
        error_text.append(f"{image_path.name}:\n\n", style="bold yellow")
        error_text.append(str(e), style="yellow")
        error_text.append("\n\nRaw Response was:\n", style="bold cyan")
        error_text.append(str(raw_response), style="white")
        
        panel = Panel(error_text, title="[bold red]💥 SCHEMA VALIDATION FAILED 💥[/bold red]", border_style="red")
        console.print(panel)
        
        try:
            rel_path = image_path.relative_to(INPUT_IMAGES_DIR)
        except ValueError:
            rel_path = Path(image_path.name)
        rel_dir = rel_path.parent
        target_out_dir = OUTPUT_CHUNKS_DIR / rel_dir
        target_out_dir.mkdir(parents=True, exist_ok=True)
        error_path = target_out_dir / f"vision_chunk_{image_path.stem}_ERROR.txt"
        with open(error_path, 'w', encoding='utf-8') as f:
            f.write(f"Validation Error:\n{str(e)}\n\nRaw Response:\n{raw_response}")
        print(f"  ⚠️ Logged raw response to {error_path} for investigation.")
        return False
    except Exception as e:
        print(f"  ❌ Failed vision pipeline processing: {e}")
        return False


from core.concurrency import RateLimiter, make_safe_print

# Thread-safe printing to prevent stdout interleaving
print = make_safe_print()


def process_single_image(img_path, reader, direction, context, active_ai, preprocess, binarize, deskew, debug_ocr, PROCESSED_IMAGES_DIR, rate_limiter=None):
    """
    Worker function to process a single image and archive it upon completion.
    """
    if rate_limiter:
        rate_limiter.wait()
        
    success = run_vision_pipeline(
        img_path, reader,
        direction=direction,
        context=context,
        active_ai=active_ai,
        preprocess=preprocess,
        binarize=binarize,
        deskew=deskew,
        debug_ocr=debug_ocr
    )
    
    if success:
        try:
            rel_path = img_path.relative_to(INPUT_IMAGES_DIR)
        except ValueError:
            rel_path = Path(img_path.name)
        dest_path = PROCESSED_IMAGES_DIR / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(img_path), str(dest_path))
            print(f"  📦 Successfully archived {img_path.name} to {dest_path.parent}/")
            return True
        except Exception as e:  # noqa: BLE001 - archiving failure must not fail the pipeline; report and continue
            print(f"  ⚠️ Warning: Failed to move file {img_path.name} to archives: {e}")
            return True
    else:
        print(f"  ⚠️ Keeping {img_path.name} in the input hopper for manual inspection.")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Multimodal Vision Harvester for the Lore Matrix")
    parser.add_argument("--direction", type=str, choices=["LTR", "RTL"], default="LTR", help="Reading direction: LTR (Western Comics) or RTL (Manga)")
    parser.add_argument("--context", type=str, default=None, help="Scene context to guide LLM extraction and prevent hallucinations")
    parser.add_argument("--engine", type=str, choices=["local", "gemini", "featherless"], default=None, help="AI provider engine to use")
    parser.add_argument("--model", type=str, default=None, help="Model name override")
    parser.add_argument("--preprocess", action="store_true", help="Enable image pre-processing (denoising and contrast enhancement) for OCR")
    parser.add_argument("--binarize", action="store_true", help="Apply adaptive thresholding/binarization to image")
    parser.add_argument("--deskew", action="store_true", help="Automatically detect and correct image skew/rotation")
    parser.add_argument("--debug-ocr", action="store_true", help="Output annotated debug image showing grouped bounding boxes and reading order")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent worker threads (default: 1)")
    parser.add_argument("--rate-limit", type=float, default=0.0, help="Delay in seconds between LLM calls per worker (default: 0.0)")
    args = parser.parse_args()
    direction = args.direction
    context = args.context
    preprocess = args.preprocess
    binarize = args.binarize
    deskew = args.deskew
    debug_ocr = args.debug_ocr
    workers = args.workers
    rate_limit = args.rate_limit
    
    from config.settings import get_ai_provider
    active_ai = get_ai_provider(engine_name=args.engine, model_name=args.model)
    
    print(f"Initializing Multimodal Harvester using: {active_ai.__class__.__name__} ({active_ai.model_name})...\n")
    print(f"Reading direction configuration: {direction}\n")
    if context:
        print(f"Scene context: {context}\n")
    if workers > 1:
        print(f"Concurrency configured: {workers} worker threads.\n")
    if rate_limit > 0:
        print(f"Rate limiting active: {rate_limit}s delay between LLM calls.\n")
    
    # Ensure hoppers exist
    INPUT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Scan for common image formats recursively
    extensions = ['*.png', '*.jpg', '*.jpeg', '*.webp', '*.bmp']
    target_images = []
    for ext in extensions:
        target_images.extend(INPUT_IMAGES_DIR.rglob(ext))
        target_images.extend(INPUT_IMAGES_DIR.rglob(ext.upper()))
            
    # Remove duplicate paths just in case case-sensitivity overlaps
    target_images = sorted(list(set(target_images)))
    
    if not target_images:
        print(f"📭 The input hopper is empty. No images found in {INPUT_IMAGES_DIR}/")
        sys.exit(0)
        
    print(f"👁️ Found {len(target_images)} images to harvest. Initializing EasyOCR Reader...")
    reader = easyocr.Reader(['en'])
    
    rate_limiter = RateLimiter(rate_limit) if rate_limit > 0 else None
    success_count = 0
    
    if workers > 1:
        print(f"🚀 Spawning ThreadPoolExecutor with {workers} workers...")
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    process_single_image,
                    img_path, reader, direction, context, active_ai,
                    preprocess, binarize, deskew, debug_ocr, PROCESSED_IMAGES_DIR, rate_limiter
                ): img_path for img_path in target_images
            }
            for future in as_completed(futures):
                img_path = futures[future]
                try:
                    success = future.result()
                    if success:
                        success_count += 1
                except Exception as exc:
                    print(f"  ❌ Image {img_path.name} generated an exception: {exc}")
    else:
        # Sequential execution
        for img_path in target_images:
            print("\n" + "="*50)
            print(f"🎯 PROCESSING IMAGE: {img_path.name}")
            print("="*50)
            success = process_single_image(
                img_path, reader, direction, context, active_ai,
                preprocess, binarize, deskew, debug_ocr, PROCESSED_IMAGES_DIR, rate_limiter
            )
            if success:
                success_count += 1
            
    print(f"\n🎉 Vision extraction run complete. Processed {success_count}/{len(target_images)} successfully.")


if __name__ == "__main__":
    main()
