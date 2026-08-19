#!/usr/bin/env python3
"""core/launchpad_types.py — Pydantic model for institutional features."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LaunchpadFeatures(BaseModel):
    """Structural features of an institution, extracted from text.

    CamelCase field names mirror LLM JSON keys per AGENTS.md convention.
    """
    Faults: list[str] = Field(default_factory=list, description="Structural faults and systemic weaknesses")
    Levers: list[str] = Field(default_factory=list, description="Kinetic levers available for exploitation")
    Scarcities: list[str] = Field(default_factory=list, description="Terminal scarcities and resource constraints")
    Guard_Pressure: float = Field(default=0.5, ge=0.0, le=1.0, description="Sixth guard pressure (0.0 weak, 1.0 rigid)")

    @property
    def faults(self) -> list[str]:
        return self.Faults

    @property
    def levers(self) -> list[str]:
        return self.Levers

    @property
    def scarcities(self) -> list[str]:
        return self.Scarcities

    @property
    def guard_pressure(self) -> float:
        return self.Guard_Pressure
