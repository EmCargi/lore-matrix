#!/usr/bin/env python3
"""core/ocean_types.py — Pydantic model for OCEAN personality profiles."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OceanProfile(BaseModel):
    """Big Five personality coordinates as percentiles (0-100).

    CamelCase field names mirror LLM JSON keys per AGENTS.md convention.
    snake_case aliases provided for Python-side access.
    """
    Openness: float = Field(..., ge=0, le=100, description="Cognitive/spatial fluidity percentile")
    Conscientiousness: float = Field(..., ge=0, le=100, description="Operational hygiene percentile")
    Extraversion: float = Field(..., ge=0, le=100, description="Performative visibility percentile")
    Agreeableness: float = Field(..., ge=0, le=100, description="Relational boundary enforcement percentile")
    Neuroticism: float = Field(..., ge=0, le=100, description="Threat perception percentile")

    @property
    def openness(self) -> float:
        return self.Openness

    @property
    def conscientiousness(self) -> float:
        return self.Conscientiousness

    @property
    def extraversion(self) -> float:
        return self.Extraversion

    @property
    def agreeableness(self) -> float:
        return self.Agreeableness

    @property
    def neuroticism(self) -> float:
        return self.Neuroticism

    def to_vspe_dict(self) -> dict:
        """Convert to VSPE's OCEANProfile dict format."""
        return {
            "openness": self.Openness,
            "conscientiousness": self.Conscientiousness,
            "extraversion": self.Extraversion,
            "agreeableness": self.Agreeableness,
            "neuroticism": self.Neuroticism,
        }
