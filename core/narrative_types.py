"""
Lore Matrix — Narrative Structure Types
Pydantic models for NME-compatible narrative graph extraction.
CamelCase fields mirror LLM JSON keys.
"""

from pydantic import BaseModel, Field


class StoryNode(BaseModel):
    """A single story beat, scene, or major event."""
    id: str
    label: str
    act: int | None = None
    pov: str | None = None


class StoryEdge(BaseModel):
    """A causal or temporal transition between two nodes."""
    source: str
    target: str
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class Perspective(BaseModel):
    """A narrative viewpoint character."""
    name: str
    pov: str = "secondary"
    discrepancy: bool = False


class ParallelWorld(BaseModel):
    """An alternate timeline, realm, or plane."""
    id: str
    label: str


class CrossReference(BaseModel):
    """A connection between parallel worlds."""
    source: str
    target: str
    type: str = "reference"


class NarrativeStructure(BaseModel):
    """Full narrative graph — NME-compatible."""
    name: str = "Untitled Narrative"
    nodes: list[StoryNode] = []
    edges: list[StoryEdge] = []
    perspectives: list[Perspective] = []
    parallel_worlds: list[ParallelWorld] = []
    cross_references: list[CrossReference] = []
    narrator_position: float = Field(default=0.0, ge=0.0, le=10.0)
