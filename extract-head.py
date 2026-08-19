#!/usr/bin/env python3
"""
Lore Matrix — Meso-Tier Institutional Profiler (extract-head).
Reads unstructured text about an institution, calls an LLM to score the
four H.E.A.D. meso sliders (BRC/IRT/IND/SRI) + the macro quadrant,
validates against the MesoTierLLM Pydantic model, and writes a head-cli
compatible fixture YAML.

Includes: tenacity retries, big-rig-first Ollama fallback chain,
response_format via JSON schema, --overwrite with .bak archival,
optional --schein-only second pass, and atomic tempfile writes.
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name != "lore-matrix" else SCRIPT_DIR
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from config.settings import BASE_DIR, get_ai_provider, load_prompt
from core.meso_types import MesoTierLLM, ScheinOnly
from core.ocean_scalpel import extract_json_scalpel
from core.utils import clean_reasoning_response, generate_with_retry


MESO_PROMPT_FILENAME = "meso-profiler-prompt.md"


def resolve_path(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


def default_fixtures_dir() -> Path:
    candidate = BASE_DIR.parent / "shda-cli" / "head-cli" / "fixtures"
    if candidate.is_dir():
        return candidate
    local = BASE_DIR / "fixtures"
    local.mkdir(parents=True, exist_ok=True)
    return local


def _safe_yaml(value: str) -> str:
    """Keep long prose blocks readable: strip trailing whitespace, preserve newlines."""
    return value.strip()


def score_institution(text: str, system_prompt: str, provider, schein_only: bool = False) -> MesoTierLLM:
    """Call LLM to score meso sliders + quadrant (+ optional Schein), return validated MesoTierLLM."""
    response_format = ScheinOnly if schein_only else MesoTierLLM
    try:
        raw = generate_with_retry(
            active_ai=provider,
            system_prompt=system_prompt,
            user_prompt=f"[INSTITUTION TEXT]\n{text}",
            response_format=response_format,
        )
    except Exception as e:
        raise RuntimeError(f"[ENGINE-FAILURE] meso extraction: LLM call failed — {e}") from e

    cleaned = clean_reasoning_response(raw)
    try:
        json_str = extract_json_scalpel(cleaned)
    except ValueError as e:
        raise RuntimeError(
            f"[PARSE-FAILURE] meso extraction: could not extract JSON from model output. "
            f"Raw start: {cleaned[:300]!r}"
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"[PARSE-FAILURE] meso extraction: unexpected scalpel error — {e}. "
            f"Raw start: {cleaned[:300]!r}"
        ) from e

    try:
        return MesoTierLLM.model_validate_json(json_str)
    except Exception as e:
        raise RuntimeError(
            f"[VALIDATION-FAILURE] meso extraction: model output failed MesoTierLLM validation. "
            f"JSON: {json_str[:400]!r}"
        ) from e


def atomic_write_yaml(path: Path, data: dict) -> None:
    tmp = tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, suffix=".tmp", encoding="utf-8"
    )
    try:
        yaml.safe_dump(data, tmp, sort_keys=False, allow_unicode=True)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, path)
    except BaseException:
        Path(tmp.name).unlink(missing_ok=True)
        raise


def cmd_profile(args) -> None:
    text = resolve_path(args.input).read_text(encoding="utf-8")
    provider = get_ai_provider(engine_name=args.engine, model_name=args.model)
    system_prompt = load_prompt(MESO_PROMPT_FILENAME)
    if not system_prompt:
        print(f"[FATAL] Could not load meso-profiler-prompt from config/")
        sys.exit(1)

    out_stem = args.out or Path(args.input).stem
    dest_dir = resolve_path(args.dir) if args.dir else default_fixtures_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / f"{out_stem}.yaml"

    print(f"  Scanning institution: {Path(args.input).name}")
    print(f"  Engine: {args.engine}" + (f" ({args.model})" if args.model else ""))
    print(f"  Output: {out_path}")

    if args.schein_only:
        if not out_path.exists():
            print(f"\n  [FATAL] --schein-only requires an existing fixture at {out_path}")
            sys.exit(1)
        existing = yaml.safe_load(out_path.read_text())
        if "institutional_index" not in existing:
            print("[FATAL] Existing fixture missing institutional_index — cannot attach Schein audit")
            sys.exit(1)

        print(f"  Mode: Schein-only audit (sliders preserved)")
        scored = score_institution(text, system_prompt, provider, schein_only=True)
        if scored.Schein is None:
            print("\n  [ERROR] Schein-only pass returned no Schein block.")
            sys.exit(1)
        existing["schein_levels"] = {
            "artifacts": _safe_yaml(scored.Schein.artifacts),
            "espoused_values": _safe_yaml(scored.Schein.espoused_values),
            "basic_assumptions": _safe_yaml(scored.Schein.basic_assumptions),
        }
        if args.overwrite or not out_path.exists():
            if out_path.exists():
                bak = out_path.with_suffix(".yaml.bak")
                out_path.rename(bak)
                print(f"  Archived: {bak}")
            atomic_write_yaml(out_path, existing)
            print(f"  Updated: {out_path}")
        else:
            print(f"  Skipped — fixture exists. Use --overwrite to replace.")
        return

    scored = score_institution(text, system_prompt, provider, schein_only=False)
    faction_name = args.name or out_stem.replace("-", " ").replace("_", " ").title()
    fixture = scored.to_fixture_dict(faction_name=faction_name)

    if args.overwrite or not out_path.exists():
        if out_path.exists():
            bak = out_path.with_suffix(".yaml.bak")
            out_path.rename(bak)
            print(f"  Archived: {bak}")
        atomic_write_yaml(out_path, fixture)
        print(f"  Saved: {out_path}")
    else:
        print(f"  Skipped — fixture exists. Use --overwrite to replace (previous archived to .bak).")

    print(f"\n  Meso Sliders:")
    idx = fixture["institutional_index"]
    print(f"    BRC: {idx['behavior_regulation']:.1f}")
    print(f"    IRT: {idx['information_routing']:.1f}")
    print(f"    IND: {idx['ideological_normalization']:.1f}")
    print(f"    SRI: {idx['somatic_insulation']:.1f}")
    print(f"    Quadrant: {fixture['head_quadrant']}")
    if fixture.get("schein_levels"):
        print(f"    Schein: 3-layer cultural audit attached")


def cmd_scan(args) -> None:
    config_dir = BASE_DIR / "config"
    prompts = sorted(config_dir.glob("*-prompt.md"))
    print(f"\n  Available profiler prompts:\n")
    for p in prompts:
        marker = " ← meso" if MESO_PROMPT_FILENAME in p.name else ""
        print(f"    {p.name}{marker}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="extract-head", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="List available profiler prompts")

    p_profile = sub.add_parser("profile", help="Score an institution from text")
    p_profile.add_argument("--input", "-i", required=True, help="Path to institution text file")
    p_profile.add_argument("--engine", "-e", choices=["local", "gemini", "featherless"],
                           default="local", help="AI provider engine")
    p_profile.add_argument("--model", "-m", default=None, help="Model name for thin-client fallback")
    p_profile.add_argument("--out", "-o", default=None, help="Fixture stem (without .yaml)")
    p_profile.add_argument("--name", "-n", default=None, help="Faction display name")
    p_profile.add_argument("--dir", "-d", default=None, help="Output directory for fixture YAML")
    p_profile.add_argument("--overwrite", action="store_true",
                           help="Re-extract and replace existing fixture (archives prior to .yaml.bak)")
    p_profile.add_argument("--schein-only", action="store_true",
                           help="Schein audit only — reads existing fixture, scores only Schein, merges in")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    cmds = {
        "scan": cmd_scan,
        "profile": cmd_profile,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()