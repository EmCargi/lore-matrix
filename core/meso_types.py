#!/usr/bin/env python3
"""core/meso_types.py — Pydantic model for LLM-scored meso-tier institutions.

CamelCase fields mirror the LLM JSON keys per AGENTS.md. The four 0–10 sliders
plus the declared quadrant are the hard-required core (what the calibration
gate scores); the Schein audit is best-effort prose that must never be able to
jeopardize the sliders, so it stays optional and separable via --schein-only.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ScheinAudit(BaseModel):
    """Organizational culture in Schein's three concentric layers."""
    artifacts: str = Field(..., description="Visible customs, iconography, rituals, material culture")
    espoused_values: str = Field(..., description="Stated values, moral codes, foundational myths, charters")
    basic_assumptions: str = Field(..., description="Unwritten, taken-for-granted survival and power scripts")


class MesoTierLLM(BaseModel):
    """Four meso sliders + declared macro quadrant (+ optional Schein audit)."""
    BehaviorRegulation: float = Field(..., ge=0, le=10, description="BRC — Weber: variance-restriction / codification density")
    InformationRouting: float = Field(..., ge=0, le=10, description="IRT — diffusion of innovations: transparency of communication streams")
    IdeologicalNormalization: float = Field(..., ge=0, le=10, description="IND — Althusser: dogma density / orthodoxy rigidity")
    SomaticInsulation: float = Field(..., ge=0, le=10, description="SRI — French & Raven: boundary-wall permeability")
    HeadQuadrant: Literal[
        "Closed Society",
        "Open Society",
        "Predatory State",
        "Social Democratic Corporatist State",
    ] = Field(..., description="Declared macro quadrant")

    Schein: ScheinAudit | None = Field(
        None,
        description="Optional Schein cultural audit. Score it only if requested; never let it fail the sliders.",
    )

    def to_fixture_dict(self, faction_name: str = "Unnamed Institution") -> dict:
        """Serialize into the exact head-cli fixture shape (contract-restrained)."""
        d = {
            "faction_name": faction_name,
            "head_quadrant": self.HeadQuadrant,
            "institutional_index": {
                "behavior_regulation": round(self.BehaviorRegulation, 1),
                "information_routing": round(self.InformationRouting, 1),
                "ideological_normalization": round(self.IdeologicalNormalization, 1),
                "somatic_insulation": round(self.SomaticInsulation, 1),
            },
        }
        if self.Schein is not None:
            d["schein_levels"] = {
                "artifacts": self.Schein.artifacts.strip(),
                "espoused_values": self.Schein.espoused_values.strip(),
                "basic_assumptions": self.Schein.basic_assumptions.strip(),
            }
        return d


class ScheinOnly(BaseModel):
    """Response payload for the optional --schein-only second pass (sliders already locked)."""
    Schein: ScheinAudit = Field(..., description="Schein audit only, when re-auditing culture without re-scoring sliders")