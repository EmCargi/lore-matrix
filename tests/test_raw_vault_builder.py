# Tests for the pure JSON → raw markdown unwrapper (core/raw_vault_builder.py).
# These tests must never require an LLM provider.

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def beastiary_json(tmp_path):
    data = {
        "entries": [
            {
                "name": "Elves",
                "keys": ["elf", "elfin", "sylvan"],
                "content": "Ancient fey-blooded race. [Type: Species] [Tier: 3] [Origin: Feywild]",
            },
            {
                "name": "Goblins",
                "keys": ["goblin"],
                "content": "Cunning green-skinned raiders. [Type: Species] [Tier: 1]",
            },
            {
                "name": "Dwarves/Gnomes",
                "keys": ["dwarf", "gnome"],
                "content": "Stout subterranean crafters. [Type: Species]",
            },
        ]
    }
    p = tmp_path / "creatures.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_no_provider_instantiation(monkeypatch):
    """Importing the pure module and unwrapping must never construct an LLM provider."""
    import config.settings

    def boom(*args, **kwargs):
        raise RuntimeError("LLM stack touched!")

    monkeypatch.setattr(config.settings, "get_ai_provider", boom)

    # If importing config.settings triggered provider construction, this would raise.
    import core.raw_vault_builder as rvb  # noqa: F401

    # And a real unwrap must not construct one either.
    title, folder, md = rvb.build_raw_markdown_in_memory(
        {"name": "Elves", "keys": ["elf"], "content": "Text. [Type: Species]"}, "beastiary"
    )
    assert title == "Elves"
    assert folder == "Species"
    assert "type: Species" in md


def test_sillytavern_unwrap(beastiary_json):
    from core.raw_vault_builder import extract_entries_from_json, write_raw_vault

    data = json.loads(beastiary_json.read_text(encoding="utf-8"))
    entries = extract_entries_from_json(data)
    out = beastiary_json.parent / "raw"
    written = write_raw_vault(entries, "beastiary", out)

    assert written == 3
    elves = out / "beastiary" / "Species" / "Elves.md"
    assert elves.exists()
    content = elves.read_text(encoding="utf-8")
    assert 'aliases: ["elf", "elfin", "sylvan"]' in content
    assert "tier: 3" in content
    assert "origin: Feywild" in content
    # Bracket metadata is moved into frontmatter and stripped from the body
    assert "[Type: Species]" not in content


def test_path_sanitization(beastiary_json):
    from core.raw_vault_builder import extract_entries_from_json, write_raw_vault

    data = json.loads(beastiary_json.read_text(encoding="utf-8"))
    out = beastiary_json.parent / "raw2"
    write_raw_vault(extract_entries_from_json(data), "beastiary", out)

    # 'Dwarves/Gnomes' must not create nested directories
    safe = out / "beastiary" / "Species" / "Dwarves-Gnomes.md"
    assert safe.exists()
    assert not (out / "beastiary" / "Species" / "Dwarves").exists()


def test_extract_entries_shapes():
    from core.raw_vault_builder import extract_entries_from_json

    assert len(extract_entries_from_json([{"name": "A"}, {"name": "B"}])) == 2
    # entries as an id-keyed dict
    assert len(extract_entries_from_json({"entries": {"1": {"name": "A"}, "2": {"name": "B"}}})) == 2
    # numeric-keyed top-level dict
    assert len(extract_entries_from_json({"1": {"name": "A"}, "2": {"name": "B"}})) == 2
    # nested entry detection
    assert len(extract_entries_from_json({"universe": {"name": "A", "content": "x"}})) == 1
    # nothing usable
    assert extract_entries_from_json({"foo": "bar"}) == []


def test_narrative_entries(tmp_path):
    from core.raw_vault_builder import write_raw_vault

    entries = [
        {"Speaker": "Elara", "Dialogue": "Welcome.", "Scene Description": "A moonlit glade."}
    ]
    out = tmp_path / "raw"
    write_raw_vault(entries, "story", out)

    note = out / "story" / "Narrative" / "Elara.md"
    assert note.exists()
    content = note.read_text(encoding="utf-8")
    assert "type: Narrative" in content
    assert "Dialogue: Welcome." in content


def test_empty_string_alias_filtering(tmp_path):
    """Empty-string aliases like ['', 'kid', 'child'] must not appear in YAML frontmatter."""
    from core.raw_vault_builder import write_raw_vault

    entries = [
        {"name": "Child", "keys": ["", "kid", "child"], "content": "A young one."}
    ]
    out = tmp_path / "raw"
    write_raw_vault(entries, "slang", out)

    note = out / "slang" / "Converted JSON" / "Child.md"
    assert note.exists()
    content = note.read_text(encoding="utf-8")
    assert 'aliases: ["kid", "child"]' in content, f"Empty string should be filtered: {content}"
    assert 'aliases: [""]' not in content


def test_filename_starts_with_dash(tmp_path):
    """Filenames like '-Cut your stick-' must not start with a dash or dot."""
    from core.raw_vault_builder import write_raw_vault

    entries = [
        {"name": "-Cut your stick-", "keys": ["stick"], "content": "A sharp thing."}
    ]
    out = tmp_path / "raw"
    write_raw_vault(entries, "slang", out)

    # File must not start with '-' or '.'
    note = out / "slang" / "Converted JSON" / "Cut your stick-.md"
    assert note.exists()
    # Also verify no file with leading dash exists
    dash_files = list((out / "slang" / "Converted JSON").glob("-*.md"))
    assert len(dash_files) == 0, f"Files must not start with dash: {dash_files}"