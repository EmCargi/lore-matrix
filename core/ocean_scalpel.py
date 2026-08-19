#!/usr/bin/env python3
"""core/ocean_scalpel.py — JSON extraction scalpel for reasoning model output."""

from __future__ import annotations

import json


def extract_json_scalpel(raw: str) -> str:
    """Clamp outermost JSON braces, ignoring surrounding commentary.

    Handles reasoning models that emit prose before/after the JSON block.
    Finds first { and last }, validates with json.loads(), returns clean JSON.

    Raises ValueError if no valid JSON object found.
    """
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")

    if first_brace == -1 or last_brace == -1 or last_brace < first_brace:
        raise ValueError("No JSON object found in response")

    candidate = raw[first_brace:last_brace + 1]

    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        pass

    depth = 0
    start = first_brace
    for i in range(first_brace, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start:i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    break

    for start_idx in range(first_brace + 1, len(raw)):
        if raw[start_idx] != "{":
            continue
        depth = 0
        for i in range(start_idx, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start_idx:i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break

    raise ValueError("No valid JSON object found in response")
