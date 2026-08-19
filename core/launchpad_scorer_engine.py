"""core/launchpad_scorer_engine.py — Pure launchpad scoring function, importable by
both the extract-launchpad CLI and vspe-cli's launchpad_profiler wrapper."""

from core.launchpad_types import LaunchpadFeatures
from core.ocean_scalpel import extract_json_scalpel
from core.utils import clean_reasoning_response, generate_with_retry


def score_text(text: str, system_prompt: str, provider) -> LaunchpadFeatures:
    """Call LLM to extract institutional features, return validated LaunchpadFeatures."""
    raw = generate_with_retry(
        active_ai=provider,
        system_prompt=system_prompt,
        user_prompt=f"[INSTITUTION TEXT]\n{text}",
        response_format=LaunchpadFeatures,
    )
    cleaned = clean_reasoning_response(raw)
    json_str = extract_json_scalpel(cleaned)
    return LaunchpadFeatures.model_validate_json(json_str)
