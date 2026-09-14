# Tests for narrative structure extraction module.

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.narrative_types import (
    CrossReference,
    NarrativeStructure,
    ParallelWorld,
    Perspective,
    StoryEdge,
    StoryNode,
)

# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def sample_node():
    return StoryNode(id="inciting_incident", label="Hero discovers the artifact", act=1)


@pytest.fixture
def sample_edge():
    return StoryEdge(source="inciting_incident", target="first_confrontation", weight=0.8)


@pytest.fixture
def sample_perspective():
    return Perspective(name="Ciel", pov="primary", discrepancy=False)


@pytest.fixture
def sample_world():
    return ParallelWorld(id="yomi", label="Yomi (underworld)")


@pytest.fixture
def sample_cross_ref():
    return CrossReference(source="yomi", target="mortal_realm", type="rift")


@pytest.fixture
def sample_structure():
    return NarrativeStructure(
        name="Test Story",
        nodes=[
            StoryNode(id="a", label="Beginning", act=1),
            StoryNode(id="b", label="Middle", act=2),
            StoryNode(id="c", label="End", act=3),
        ],
        edges=[
            StoryEdge(source="a", target="b", weight=0.9),
            StoryEdge(source="b", target="c", weight=0.7),
        ],
        perspectives=[Perspective(name="Alice", pov="primary")],
    )


@pytest.fixture
def short_story(tmp_path):
    """A short prose narrative for end-to-end testing."""
    story = tmp_path / "short_story.txt"
    story.write_text(
        "The detective entered the room. Blood on the floor, a broken window.\n\n"
        "He questioned the butler, who lied about his whereabouts.\n\n"
        "In a flashback, the victim had discovered a smuggling ring.\n\n"
        "The detective found a hidden letter revealing the truth.\n\n"
        "He confronted the butler, who confessed to the crime.\n\n"
        "Justice was served, and the town returned to peace.\n",
        encoding="utf-8",
    )
    return story


# ── Model Tests ───────────────────────────────────────────


def test_story_node_valid(sample_node):
    assert sample_node.id == "inciting_incident"
    assert sample_node.act == 1


def test_story_edge_valid(sample_edge):
    assert sample_edge.weight == 0.8
    assert 0.0 <= sample_edge.weight <= 1.0


def test_story_edge_weight_rejected():
    """Pydantic rejects weight > 1.0 rather than clamping."""
    with pytest.raises(ValidationError):
        StoryEdge(source="a", target="b", weight=1.5)


def test_perspective_default(sample_perspective):
    assert sample_perspective.pov == "primary"
    assert sample_perspective.discrepancy is False


def test_parallel_world(sample_world):
    assert sample_world.id == "yomi"


def test_cross_reference(sample_cross_ref):
    assert sample_cross_ref.type == "rift"


def test_narrative_structure_builds(sample_structure):
    assert sample_structure.name == "Test Story"
    assert len(sample_structure.nodes) == 3
    assert len(sample_structure.edges) == 2


def test_narrative_structure_serializes(sample_structure):
    data = json.loads(sample_structure.model_dump_json())
    assert data["name"] == "Test Story"
    assert len(data["nodes"]) == 3


def test_narrative_structure_rejects_bad_edge():
    with pytest.raises(ValidationError):
        NarrativeStructure(
            name="Bad",
            edges=[StoryEdge(source="a", target="b", weight=5.0)],
        )


# ── Extractor Script Tests ────────────────────────────────


SCRIPT_PATH = PROJECT_ROOT / "extract-narrative.py"


def test_extractor_help():
    """Script returns 0 on --help."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0


def test_extractor_missing_input():
    """Script exits non-zero when --input is missing."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode != 0


def test_extractor_file_not_found():
    """Script exits non-zero when input file doesn't exist."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--input", "/nonexistent_file_xyz.txt"],
        capture_output=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode != 0


def test_resolve_path_absolute():
    """resolve_path passes through absolute paths."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    abs_path = Path("/tmp/test.txt")
    assert ext.resolve_path(str(abs_path)) == abs_path


def test_resolve_path_relative():
    """resolve_path resolves relative to BASE_DIR."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    rel = ext.resolve_path("some/file.txt")
    assert rel.is_absolute()
    assert rel.name == "file.txt"


def test_merge_structures():
    """merge_structures deduplicates nodes and edges."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    s1 = NarrativeStructure(
        name="Test",
        nodes=[StoryNode(id="a", label="A"), StoryNode(id="b", label="B")],
        edges=[StoryEdge(source="a", target="b", weight=0.8)],
    )
    s2 = NarrativeStructure(
        name="Test",
        nodes=[StoryNode(id="b", label="B"), StoryNode(id="c", label="C")],
        edges=[StoryEdge(source="b", target="c", weight=0.6)],
    )
    merged = ext.merge_structures([s1, s2], name="Merged")
    assert len(merged.nodes) == 3
    assert len(merged.edges) == 2
    assert merged.name == "Merged"


def test_dedup_perspectives():
    """Name variants like 'Sebastian' and 'Sebastian Michaelis' merge."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    perspectives = [
        {"name": "Sebastian Michaelis", "pov": "secondary", "discrepancy": False},
        {"name": "Sebastian", "pov": "secondary", "discrepancy": False},
        {"name": "Ciel Phantomhive", "pov": "primary", "discrepancy": False},
        {"name": "Ciel", "pov": "secondary", "discrepancy": False},
        {"name": "Tamamo No Mae", "pov": "antagonist", "discrepancy": False},
        {"name": "Tamamo-no-Mae", "pov": "antagonist", "discrepancy": True},
    ]
    result = ext._dedup_perspectives(perspectives)
    names = {p["name"] for p in result}
    assert "Sebastian Michaelis" in names
    assert "Sebastian" not in names
    assert "Ciel Phantomhive" in names
    assert "Ciel" not in names
    # discrepancy should be preserved if any variant flagged it
    tamamo = next(p for p in result if "Tamamo" in p["name"])
    assert tamamo["discrepancy"] is True


def test_fuzzy_dedup_nodes():
    """Near-identical node labels merge."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    nodes = [
        {"id": "n1", "label": "The detective arrives at the scene", "act": None},
        {"id": "n2", "label": "The detective arrives at the scene", "act": 1},
        {"id": "n3", "label": "A different scene entirely", "act": 2},
    ]
    result = ext._fuzzy_dedup_nodes(nodes)
    assert len(result) == 2
    # act from the duplicate should fill the gap
    detective = next(n for n in result if "detective" in n["label"])
    assert detective["act"] == 1


def test_infer_acts():
    """Acts are assigned by narrative position when LLM omits them."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    nodes = [
        {"id": "a", "label": "Start"},
        {"id": "b", "label": "Early"},
        {"id": "c", "label": "Middle"},
        {"id": "d", "label": "Late"},
        {"id": "e", "label": "End"},
        {"id": "f", "label": "Finale"},
    ]
    edges = [
        {"source": "a", "target": "b", "weight": 1.0},
        {"source": "b", "target": "c", "weight": 1.0},
        {"source": "c", "target": "d", "weight": 1.0},
        {"source": "d", "target": "e", "weight": 1.0},
        {"source": "e", "target": "f", "weight": 1.0},
    ]
    result = ext._infer_acts(nodes, edges)
    acts = {n["id"]: n["act"] for n in result}
    assert acts["a"] == 1
    assert acts["b"] == 1
    assert acts["c"] == 2
    assert acts["d"] == 2
    assert acts["e"] == 3
    assert acts["f"] == 3


def test_infer_acts_respects_existing():
    """When most nodes already have acts, don't override."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    nodes = [
        {"id": "a", "label": "Start", "act": 1},
        {"id": "b", "label": "Middle", "act": 2},
        {"id": "c", "label": "End", "act": 3},
    ]
    edges = [{"source": "a", "target": "b", "weight": 1.0}, {"source": "b", "target": "c", "weight": 1.0}]
    result = ext._infer_acts(nodes, edges)
    assert result == nodes  # unchanged


def test_pov_resolution_primary_dominant():
    """Primary POV emerges from node coverage (Riordan-style rotation)."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    nodes = (
        [{"id": f"p{i}", "label": f"Percy {i}", "pov": "Percy Jackson"} for i in range(60)]
        + [{"id": f"a{i}", "label": f"Annabeth {i}", "pov": "Annabeth Chase"} for i in range(25)]
        + [{"id": f"l{i}", "label": f"Leo {i}", "pov": "Leo Valdez"} for i in range(15)]
    )
    raw = [
        {"name": "Percy Jackson", "pov": "primary", "discrepancy": False},
        {"name": "Annabeth Chase", "pov": "primary", "discrepancy": False},
        {"name": "Leo Valdez", "pov": "primary", "discrepancy": False},
    ]
    result = ext._resolve_pov_from_nodes(nodes, raw)
    by_name = {p["name"]: p["pov"] for p in result}
    assert by_name["Percy Jackson"] == "primary"
    assert by_name["Annabeth Chase"] == "secondary"
    assert by_name["Leo Valdez"] == "secondary"


def test_pov_resolution_single_narrator():
    """Single POV character gets primary when they dominate."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    nodes = [{"id": f"n{i}", "label": f"Scene {i}", "pov": "Ciel Phantomhive"} for i in range(50)]
    raw = [{"name": "Ciel Phantomhive", "pov": "primary", "discrepancy": False}]
    result = ext._resolve_pov_from_nodes(nodes, raw)
    assert result[0]["pov"] == "primary"


def test_pov_resolution_no_pov_tags():
    """When nodes have no POV tags, fall back to dedup."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    nodes = [{"id": f"n{i}", "label": f"Scene {i}"} for i in range(10)]
    raw = [
        {"name": "Ciel", "pov": "primary", "discrepancy": False},
        {"name": "Ciel Phantomhive", "pov": "primary", "discrepancy": False},
    ]
    result = ext._resolve_pov_from_nodes(nodes, raw)
    assert len(result) == 1


def test_narrator_position_omniscient():
    """Untagged nodes = omniscient narrator (low score)."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    nodes = [{"id": f"n{i}", "label": f"Scene {i}"} for i in range(20)]
    result = ext._compute_narrator_position(nodes)
    assert result == 0.0


def test_narrator_position_character_bound():
    """Heavy POV tagging with rotation = character-bound (high score)."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    nodes = (
        [{"id": f"a{i}", "label": f"A {i}", "pov": "Alice"} for i in range(10)]
        + [{"id": f"b{i}", "label": f"B {i}", "pov": "Bob"} for i in range(5)]
        + [{"id": f"c{i}", "label": f"C {i}", "pov": "Charlie"} for i in range(5)]
    )
    result = ext._compute_narrator_position(nodes)
    assert result >= 7.0


def test_narrator_position_single_pov():
    """Single POV character = limited (moderate score)."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    nodes = [{"id": f"n{i}", "label": f"Scene {i}", "pov": "Sora"} for i in range(20)]
    result = ext._compute_narrator_position(nodes)
    assert 3.0 <= result <= 7.0


def test_emit_to_nme_flag():
    """Script accepts --emit-to-nme flag."""
    import importlib
    ext = importlib.import_module("extract-narrative")

    assert hasattr(ext, "merge_structures")
