#!/usr/bin/env python3
"""
Lore Matrix — Institutional Launchpad Scorer
Reads text describing an institution, calls an LLM to extract structural features,
and outputs JSON for VSPE launchpad scoring.

Includes: reasoning-model noise defense via JSON scalpel, tenacity retries,
provider factory (local/gemini/featherless), and optional VSPE handoff.
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name != "lore-matrix" else SCRIPT_DIR
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import BASE_DIR, get_ai_provider, load_prompt
from core.launchpad_scorer_engine import score_text


def resolve_path(path_str: str) -> Path:
    """Resolve a path relative to BASE_DIR if not already absolute."""
    p = Path(path_str)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


def cmd_score(args) -> None:
    """Score an institution from a text file."""
    text = resolve_path(args.input).read_text(encoding="utf-8")
    provider = get_ai_provider(engine_name=args.engine, model_name=args.model)
    system_prompt = load_prompt("launchpad-scorer-prompt.md")

    print(f"  Scoring: {resolve_path(args.input).name}")
    print(f"  Engine: {args.engine}" + (f" ({args.model})" if args.model else ""))

    features = score_text(text, system_prompt, provider)

    print("\n  Institutional Features:")
    print(f"  Faults ({len(features.faults)}): {', '.join(features.faults[:3])}{'...' if len(features.faults) > 3 else ''}")
    print(f"  Levers ({len(features.levers)}): {', '.join(features.levers[:3])}{'...' if len(features.levers) > 3 else ''}")
    print(f"  Scarcities ({len(features.scarcities)}): {', '.join(features.scarcities[:3])}{'...' if len(features.scarcities) > 3 else ''}")
    print(f"  Guard Pressure: {features.guard_pressure:.2f}")

    out_data = features.model_dump()

    if args.output:
        out_path = resolve_path(args.output)
        out_path.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
        print(f"\n  Saved: {out_path}")

    if args.emit_to_vspe:
        print(f"\n  VSPE features: {json.dumps(out_data)}")


def cmd_scan(args) -> None:
    """List available prompt files."""
    config_dir = BASE_DIR / "config"
    prompts = sorted(config_dir.glob("*-prompt.md"))
    print("\n  Available prompts:\n")
    for p in prompts:
        print(f"    {p.name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="launchpad-scorer", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="List available prompts")

    p_score = sub.add_parser("score", help="Score an institution from text")
    p_score.add_argument("--input", "-i", required=True, help="Path to text file")
    p_score.add_argument("--engine", "-e", choices=["local", "gemini", "featherless"],
                        default="local", help="AI provider engine")
    p_score.add_argument("--model", "-m", default=None, help="Model name override")
    p_score.add_argument("--output", "-o", default=None, help="Output JSON path")
    p_score.add_argument("--emit-to-vspe", action="store_true",
                        help="Print VSPE-compatible dict")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    cmds = {
        "scan": cmd_scan,
        "score": cmd_score,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
