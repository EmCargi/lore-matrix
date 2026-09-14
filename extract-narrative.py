#!/usr/bin/env python3
"""
Lore Matrix — Narrative Structure Extractor
Reads a prose narrative, calls an LLM to extract its graph structure,
validates against NME-compatible Pydantic models, and writes JSON.

Includes: perspective normalization, fuzzy node deduplication,
act inference from topology, and optional NME vault handoff.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Path agnosticism setup
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name != "lore-matrix" else SCRIPT_DIR
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import BASE_DIR, get_ai_provider, load_prompt
from core.narrative_types import NarrativeStructure
from core.utils import clean_reasoning_response, generate_with_retry, semantic_chunker


def resolve_path(path_str: str) -> Path:
    """Resolve a path relative to BASE_DIR if not already absolute."""
    p = Path(path_str)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


def _normalize_name(name: str) -> str:
    """Normalize a name for dedup: lowercase, strip punctuation/whitespace."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _dedup_perspectives(perspectives: list[dict]) -> list[dict]:
    """Merge perspective name variants (e.g. 'Sebastian' + 'Sebastian Michaelis')."""
    items: list[dict] = [dict(p) for p in perspectives]
    merged: list[dict] = []

    while items:
        current = items.pop(0)
        cur_norm = _normalize_name(current["name"])
        i = 0
        while i < len(items):
            other = items[i]
            other_norm = _normalize_name(other["name"])
            if cur_norm in other_norm or other_norm in cur_norm:
                if len(other["name"]) > len(current["name"]):
                    current["name"] = other["name"]
                if other["pov"] == "primary":
                    current["pov"] = "primary"
                current["discrepancy"] = current["discrepancy"] or other["discrepancy"]
                cur_norm = _normalize_name(current["name"])
                items.pop(i)
            else:
                i += 1
        merged.append(current)

    return merged


def _label_key(label: str) -> str:
    """Normalize a node label for dedup comparison."""
    return re.sub(r"[^a-z0-9]", "", label.lower())


def _fuzzy_dedup_nodes(nodes: list[dict]) -> list[dict]:
    """Merge nodes with near-identical normalized labels."""
    merged: list[dict] = []
    seen_labels: dict[str, int] = {}

    for n in nodes:
        key = _label_key(n["label"])
        if key in seen_labels:
            existing = merged[seen_labels[key]]
            if n.get("act") and not existing.get("act"):
                existing["act"] = n["act"]
            continue
        seen_labels[key] = len(merged)
        merged.append(dict(n))
    return merged


def _infer_acts(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Assign acts by narrative position when the LLM omits them."""
    has_act = sum(1 for n in nodes if n.get("act"))
    if has_act > len(nodes) * 0.5:
        return nodes

    total = len(nodes)
    third = total // 3
    for i, node in enumerate(nodes):
        if node.get("act"):
            continue
        if i < third:
            node["act"] = 1
        elif i < 2 * third:
            node["act"] = 2
        else:
            node["act"] = 3

    return nodes


def _resolve_pov_from_nodes(nodes: list[dict], raw_perspectives: list[dict]) -> list[dict]:
    """Determine primary/secondary POV from node coverage counts."""
    pov_counts: dict[str, int] = {}
    for n in nodes:
        pov = n.get("pov")
        if pov:
            norm = _normalize_name(pov)
            pov_counts[norm] = pov_counts.get(norm, 0) + 1

    if not pov_counts:
        return _dedup_perspectives(raw_perspectives)

    total_tagged = sum(pov_counts.values())

    name_to_norm: dict[str, str] = {}
    for p in raw_perspectives:
        name_to_norm[_normalize_name(p["name"])] = p["name"]

    result: list[dict] = []
    for norm, name in name_to_norm.items():
        count = pov_counts.get(norm, 0)
        ratio = count / total_tagged if total_tagged > 0 else 0
        if ratio >= 0.4:
            pov = "primary"
        elif ratio >= 0.15:
            pov = "secondary"
        elif count > 0:
            pov = "tertiary"
        else:
            pov = "observer"
        originals = [p for p in raw_perspectives if _normalize_name(p["name"]) == norm]
        discrepancy = any(p["discrepancy"] for p in originals)
        result.append({"name": name, "pov": pov, "discrepancy": discrepancy})

    result.sort(key=lambda p: (p["pov"] != "primary", p["pov"] != "secondary", p["name"]))
    return result


def _compute_narrator_position(nodes: list[dict]) -> float:
    """Compute narrator position on the omniscient-to-character-bound spectrum.

    0.0 = pure omniscient (no POV tags, narrator outside the story)
    10.0 = deep character-bound (heavy POV tagging with rotation between characters)
    """
    if not nodes:
        return 0.0

    tagged = [n for n in nodes if n.get("pov")]
    if not tagged:
        return 0.0

    tagged_ratio = len(tagged) / len(nodes)
    unique_povs = len(set(_normalize_name(n["pov"]) for n in tagged))
    rotation = min(unique_povs / 5.0, 1.0)

    position = (tagged_ratio * 5.0) + (rotation * 5.0)
    return round(min(max(position, 0.0), 10.0), 2)


def merge_structures(structures: list[NarrativeStructure], name: str) -> NarrativeStructure:
    """Merge multiple chunk extractions into one NarrativeStructure."""
    all_nodes: dict[str, dict] = {}
    all_edges: dict[tuple, float] = {}
    all_worlds: dict[str, dict] = {}
    all_cross_refs: dict[tuple, dict] = {}
    raw_perspectives: list[dict] = []

    for s in structures:
        for n in s.nodes:
            if n.id not in all_nodes:
                all_nodes[n.id] = {"id": n.id, "label": n.label, "act": n.act, "pov": n.pov}
        for e in s.edges:
            key = (e.source, e.target)
            if key not in all_edges:
                all_edges[key] = e.weight
        raw_perspectives.extend([{"name": p.name, "pov": p.pov, "discrepancy": p.discrepancy} for p in s.perspectives])
        for w in s.parallel_worlds:
            if w.id not in all_worlds:
                all_worlds[w.id] = {"id": w.id, "label": w.label}
        for c in s.cross_references:
            key = (c.source, c.target)
            if key not in all_cross_refs:
                all_cross_refs[key] = {"source": c.source, "target": c.target, "type": c.type}

    # 1. Dedup nodes by normalized label (preserving POV tags)
    deduped_nodes = _fuzzy_dedup_nodes(list(all_nodes.values()))

    # 2. Infer acts from topology when LLM omits them
    edges_list = [{"source": k[0], "target": k[1], "weight": v} for k, v in all_edges.items()]
    nodes_with_acts = _infer_acts(deduped_nodes, edges_list)

    # 3. Resolve POV dominance from node coverage
    resolved_perspectives = _resolve_pov_from_nodes(nodes_with_acts, raw_perspectives)

    narrator_position = _compute_narrator_position(nodes_with_acts)

    return NarrativeStructure(
        name=name,
        nodes=nodes_with_acts,
        edges=edges_list,
        perspectives=resolved_perspectives,
        parallel_worlds=list(all_worlds.values()),
        cross_references=[{"source": k[0], "target": k[1], "type": v["type"]} for k, v in all_cross_refs.items()],
        narrator_position=narrator_position,
    )


def extract_structure(text: str, system_prompt: str, provider, chunk_limit: int = 8000) -> NarrativeStructure:
    """Chunk the text, send each to the LLM, merge results."""
    chunks = semantic_chunker(text, chunk_char_limit=chunk_limit)
    print(f"  📊 Split into {len(chunks)} chunk(s) for analysis")

    structures: list[NarrativeStructure] = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  🔍 Analyzing chunk {i}/{len(chunks)}...", end="", flush=True)
        raw = generate_retry_wrapper(chunk, system_prompt, provider)
        struct = validate_chunk(raw)
        print(f" nodes={len(struct.nodes)} edges={len(struct.edges)}")
        structures.append(struct)

    return merge_structures(structures, name="Extracted Narrative")


def generate_retry_wrapper(chunk: str, system_prompt: str, provider) -> str:
    """Call LLM with retry, return cleaned response."""
    raw = generate_with_retry(
        active_ai=provider,
        system_prompt=system_prompt,
        user_prompt=f"[NARRATIVE CHUNK]\n{chunk}",
        response_format=NarrativeStructure,
    )
    return clean_reasoning_response(raw)


def validate_chunk(raw: str) -> NarrativeStructure:
    """Validate LLM output against NarrativeStructure model."""
    try:
        data = json.loads(raw)
        return NarrativeStructure(**data)
    except json.JSONDecodeError:
        match = re.search(r"[\{\[][\s\S]*[\}\]]", raw)
        if match:
            data = json.loads(match.group())
            return NarrativeStructure(**data)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Lore Matrix — Narrative Structure Extractor"
    )
    parser.add_argument("--input", required=True, help="Path to prose narrative file (.txt/.md)")
    parser.add_argument(
        "--engine",
        choices=["local", "gemini", "featherless"],
        default="local",
        help="AI provider engine",
    )
    parser.add_argument("--model", default=None, help="Model name (overrides default)")
    parser.add_argument(
        "--host",
        default=None,
        help="Ollama base URL (default: http://localhost:11434 or OLLAMA_BASE_URL env)",
    )
    parser.add_argument("--output", default=None, help="Output filename (default: <input-stem>.json)")
    parser.add_argument(
        "--emit-to-nme",
        default=None,
        metavar="NME_VAULT_PATH",
        help="Also write output directly to NME narrative vault (skips manual copy)",
    )
    parser.add_argument(
        "--chunk-limit",
        type=int,
        default=8000,
        help="Max characters per chunk (default: 8000)",
    )
    args = parser.parse_args()

    # 1. Resolve and read input
    input_path = resolve_path(args.input)
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print("🚀 Narrative Structure Extractor")
    print(f"📂 Input: {input_path}")
    text = input_path.read_text(encoding="utf-8-sig")

    # 2. Initialize provider
    provider = get_ai_provider(engine_name=args.engine, model_name=args.model)
    if args.engine == "local" and args.host:
        provider.base_url = args.host
    print(f"🤖 Engine: {provider.__class__.__name__}")
    if hasattr(provider, "base_url"):
        print(f"🌐 Host: {provider.base_url}")

    # 3. Load system prompt
    system_prompt = load_prompt("narrative-extractor-prompt.md")
    if not system_prompt:
        print("❌ Failed to load narrative-extractor-prompt.md", file=sys.stderr)
        sys.exit(1)

    # 4. Extract structure
    print("🔍 Extracting narrative structure...")
    result = extract_structure(text, system_prompt, provider, chunk_limit=args.chunk_limit)

    # 5. Write output to staging
    out_name = args.output or f"{input_path.stem}.json"
    out_dir = BASE_DIR / "output" / "json_staging" / "narrative"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / out_name

    out_path.write_text(
        json.dumps(result.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 6. Optionally emit directly to NME vault
    nme_path = None
    if args.emit_to_nme:
        nme_vault = resolve_path(args.emit_to_nme)
        nme_vault.mkdir(parents=True, exist_ok=True)
        nme_path = nme_vault / out_name
        nme_path.write_text(
            json.dumps(result.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # 7. Confirmation ledger
    print(f"\n{'=' * 55}")
    print("  ✅ Narrative structure extracted")
    print(f"{'=' * 55}")
    print(f"  Name: {result.name}")
    print(f"  Nodes: {len(result.nodes)}")
    print(f"  Edges: {len(result.edges)}")
    print(f"  Perspectives: {len(result.perspectives)}")
    print(f"  Parallel Worlds: {len(result.parallel_worlds)}")
    print(f"  Cross-References: {len(result.cross_references)}")
    print(f"{'=' * 55}")
    print(f"  Output: {out_path}")
    if nme_path:
        print(f"  NME vault: {nme_path}")
    else:
        print("\n  Copy to NME narrative vault and run: nme.py db build")


if __name__ == "__main__":
    main()
