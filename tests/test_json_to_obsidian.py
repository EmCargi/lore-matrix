# Tests for the unified Obsidian forge phase flags (src/transformers/json_to_obsidian.py).
# Phase functions are exercised in-process against tmp dirs; providers are faked.

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "src" / "transformers" / "json_to_obsidian.py"

BEASTIARY_JSON = {
    "entries": [
        {
            "name": "Elves",
            "keys": ["elf", "elfin", "sylvan"],
            "content": "Fey race of the deep forests. [Type: Species] [Tier: 3]",
        },
        {
            "name": "Goblins",
            "keys": ["goblin"],
            "content": "Green-skinned raiders. [Type: Species] [Tier: 1]",
        },
    ]
}


class FakeAI:
    """Identity compiler — returns the raw content unchanged."""

    def __init__(self):
        self.model_name = "fake"

    def generate(self, system_prompt, user_content, response_format=None):
        return user_content


def _fresh_module(monkeypatch, tmp_path, tag):
    """Patch settings to tmp dirs, then import json_to_obsidian fresh (unique name)."""
    from config import settings

    monkeypatch.setattr(settings, "OUTPUT_CHUNKS_DIR", tmp_path / "staging")
    monkeypatch.setattr(settings, "RAW_VAULT_DIR", tmp_path / "TTRPG_Vault")
    monkeypatch.setattr(settings, "COMPILED_VAULT_DIR", tmp_path / "vault")
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)

    spec = importlib.util.spec_from_file_location(f"jto_{tag}", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def staged_beastiary(tmp_path):
    chunk_dir = tmp_path / "staging" / "beastiary"
    chunk_dir.mkdir(parents=True)
    chunk = chunk_dir / "creatures.json"
    chunk.write_text(json.dumps(BEASTIARY_JSON), encoding="utf-8")
    return tmp_path


def _namespace(**kw):
    defaults = {"workers": 1, "rate_limit": 0.0, "phase": None, "engine": None, "model": None}
    defaults.update(kw)
    return argparse.Namespace(**defaults)


def test_phase_raw_no_provider(monkeypatch, staged_beastiary):
    """--phase raw writes split markdown and never constructs a provider."""
    from config import settings

    def boom(*args, **kwargs):
        raise RuntimeError("LLM stack touched!")

    monkeypatch.setattr(settings, "get_ai_provider", boom)

    mod = _fresh_module(monkeypatch, staged_beastiary, "raw")
    mod.run_raw_phase()

    raw_vault = staged_beastiary / "TTRPG_Vault"
    elves = raw_vault / "beastiary" / "Species" / "Elves.md"
    goblins = raw_vault / "beastiary" / "Species" / "Goblins.md"
    assert elves.exists()
    assert goblins.exists()
    assert "tier: 3" in elves.read_text(encoding="utf-8")


def _main_via_argv(mod, argv):
    import sys as _sys

    _sys.argv = argv
    mod.main()


def test_phase_compile_empty_guard(monkeypatch, staged_beastiary):
    """Compile with nothing in the raw vault prints a warning and exits 0."""
    mod = _fresh_module(monkeypatch, staged_beastiary, "compile_guard")
    with pytest.raises(SystemExit) as excinfo:
        _main_via_argv(mod, ["json_to_obsidian.py", "--phase", "compile"])
    assert excinfo.value.code == 0


def test_parity_raw_then_compile_matches_one_shot(monkeypatch, staged_beastiary):
    """--phase raw + --phase compile == default one-shot, byte-for-byte."""
    # Phase A: raw unwrap
    mod_raw = _fresh_module(monkeypatch, staged_beastiary, "p_raw")
    mod_raw.run_raw_phase()

    # Phase B: compile the raw vault
    mod_compile = _fresh_module(monkeypatch, staged_beastiary, "p_compile")
    mod_compile.run_compile_phase(FakeAI(), _namespace())
    compiled_two_phase = {
        p.relative_to(staged_beastiary / "vault").as_posix(): p.read_text(encoding="utf-8")
        for p in (staged_beastiary / "vault").rglob("*.md")
    }

    # One-shot: straight from JSON
    mod_one_shot = _fresh_module(monkeypatch, staged_beastiary, "p_one")
    mod_one_shot.run_one_shot(FakeAI(), _namespace())
    compiled_one_shot = {
        p.relative_to(staged_beastiary / "vault").as_posix(): p.read_text(encoding="utf-8")
        for p in (staged_beastiary / "vault").rglob("*.md")
    }

    assert set(compiled_two_phase) == set(compiled_one_shot)
    for key in compiled_one_shot:
        assert compiled_two_phase[key] == compiled_one_shot[key], f"parity drift in {key}"


def test_help_exits_zero():
    """Script returns 0 on --help."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0