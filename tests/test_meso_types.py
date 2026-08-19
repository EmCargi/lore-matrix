#!/usr/bin/env python3
"""tests/test_meso_types.py — MesoTierLLM unit tests + to_fixture_dict contract validation."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.meso_types import MesoTierLLM, ScheinAudit


class TestMesoTierLLMModel(unittest.TestCase):
    """Validation + contract roundtrip for the LLM-scored meso model."""

    def test_valid_full(self):
        m = MesoTierLLM(
            BehaviorRegulation=5.0,
            InformationRouting=5.5,
            IdeologicalNormalization=4.0,
            SomaticInsulation=5.5,
            HeadQuadrant="Open Society",
            Schein=ScheinAudit(
                artifacts="drill, rotation",
                espoused_values="glory",
                basic_assumptions="survival",
            ),
        )
        d = m.to_fixture_dict("Theban Wolf")
        self.assertEqual(d["head_quadrant"], "Open Society")
        self.assertEqual(d["institutional_index"]["behavior_regulation"], 5.0)
        self.assertEqual(d["schein_levels"]["artifacts"], "drill, rotation")

    def test_valid_no_schein(self):
        m = MesoTierLLM(
            BehaviorRegulation=8.5,
            InformationRouting=3.0,
            IdeologicalNormalization=7.5,
            SomaticInsulation=9.5,
            HeadQuadrant="Predatory State",
        )
        d = m.to_fixture_dict()
        self.assertNotIn("schein_levels", d)

    def test_out_of_range_float_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            MesoTierLLM(
                BehaviorRegulation=15.0, InformationRouting=5.0,
                IdeologicalNormalization=5.0, SomaticInsulation=5.0,
                HeadQuadrant="Open Society",
            )

    def test_negative_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            MesoTierLLM(
                BehaviorRegulation=-1.0, InformationRouting=5.0,
                IdeologicalNormalization=5.0, SomaticInsulation=5.0,
                HeadQuadrant="Open Society",
            )

    def test_bad_quadrant_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            MesoTierLLM(
                BehaviorRegulation=5.0, InformationRouting=5.0,
                IdeologicalNormalization=5.0, SomaticInsulation=5.0,
                HeadQuadrant="Banana Republic",
            )

    def test_json_roundtrip(self):
        j = {
            "BehaviorRegulation": 5.0,
            "InformationRouting": 5.5,
            "IdeologicalNormalization": 4.0,
            "SomaticInsulation": 5.5,
            "HeadQuadrant": "Open Society",
        }
        m = MesoTierLLM.model_validate_json(json.dumps(j))
        self.assertEqual(m.HeadQuadrant, "Open Society")

    def test_all_quadrants_accepted(self):
        for q in ["Closed Society", "Open Society", "Predatory State",
                   "Social Democratic Corporatist State"]:
            m = MesoTierLLM(
                BehaviorRegulation=5, InformationRouting=5,
                IdeologicalNormalization=5, SomaticInsulation=5,
                HeadQuadrant=q,
            )
            self.assertEqual(m.HeadQuadrant, q)

    def test_rounding_in_fixture_dict(self):
        m = MesoTierLLM(
            BehaviorRegulation=5.55,
            InformationRouting=4.44,
            IdeologicalNormalization=6.66,
            SomaticInsulation=7.77,
            HeadQuadrant="Open Society",
        )
        d = m.to_fixture_dict()
        idx = d["institutional_index"]
        self.assertEqual(idx["behavior_regulation"], 5.5)
        self.assertEqual(idx["information_routing"], 4.4)
        self.assertEqual(idx["ideological_normalization"], 6.7)
        self.assertEqual(idx["somatic_insulation"], 7.8)

    def test_schein_strips_whitespace(self):
        m = MesoTierLLM(
            BehaviorRegulation=5, InformationRouting=5,
            IdeologicalNormalization=5, SomaticInsulation=5,
            HeadQuadrant="Open Society",
            Schein=ScheinAudit(
                artifacts="  padded  \n",
                espoused_values="\ttabbed\t",
                basic_assumptions="\n\n\nunwritten\n\n\n",
            ),
        )
        d = m.to_fixture_dict()
        self.assertEqual(d["schein_levels"]["artifacts"], "padded")
        self.assertEqual(d["schein_levels"]["espoused_values"], "tabbed")
        self.assertEqual(d["schein_levels"]["basic_assumptions"], "unwritten")


if __name__ == "__main__":
    unittest.main()