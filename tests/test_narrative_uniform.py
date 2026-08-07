import json
import os
import sys

import pytest
from pydantic import ValidationError

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.utils import LorebookLog, NarrativeLog


def test_narrative_serializes_scene_with_space_alias():
    """by_alias=True must emit the canonical 'Scene Description' key."""
    log = NarrativeLog(entries=[{"Speaker": "A", "Dialogue": "hi", "Scene Description": "cafe"}])
    entry = log.model_dump(by_alias=True)["entries"][0]
    assert "Scene Description" in entry
    assert entry["Scene Description"] == "cafe"


def test_narrative_chunk_roundtrip_revalidates():
    """A chunk written with by_alias=True must reload cleanly (the observed bug)."""
    log = NarrativeLog(entries=[{"Speaker": "A", "Dialogue": "hi", "Scene Description": "cafe"}])
    on_disk = json.dumps(log.model_dump(by_alias=True))
    reloaded = NarrativeLog.model_validate_json(on_disk)
    assert reloaded.entries[0].Scene_Description == "cafe"


def test_underscore_scene_key_is_rejected():
    """Legacy underscore-form chunks do NOT validate — which is why the old
    plain-model_dump output silently failed downstream compilation."""
    with pytest.raises(ValidationError):
        NarrativeLog(entries=[{"Speaker": "A", "Dialogue": "hi", "Scene_Description": "x"}])


def test_plain_vs_aliased_same_for_lorebook():
    """LorebookLog defines no aliases, so by_alias=True must not change output."""
    log = LorebookLog(
        entries=[{"id": 1, "name": "X", "keys": ["k"], "content": "c", "insertion_order": 50, "priority": 50}]
    )
    assert log.model_dump() == log.model_dump(by_alias=True)