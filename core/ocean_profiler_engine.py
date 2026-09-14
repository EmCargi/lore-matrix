"""core/ocean_profiler_engine.py — Pure OCEAN profiling function, importable by both
the extract-ocean CLI and vspe-cli's ocean_profiler wrapper. No argparse, no CLI glue."""

from core.ocean_scalpel import extract_json_scalpel
from core.ocean_types import OceanProfile
from core.utils import clean_reasoning_response, generate_with_retry


def profile_text(text: str, system_prompt: str, provider) -> OceanProfile:
    """Call LLM to score OCEAN from text, return validated OceanProfile."""
    raw = generate_with_retry(
        active_ai=provider,
        system_prompt=system_prompt,
        user_prompt=f"[SUBJECT TEXT]\n{text}",
        response_format=OceanProfile,
    )
    cleaned = clean_reasoning_response(raw)
    json_str = extract_json_scalpel(cleaned)
    return OceanProfile.model_validate_json(json_str)
