#!/usr/bin/env python3
"""tests/test_launchpad_types.py — LaunchpadFeatures model tests (Lore Matrix side)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.launchpad_types import LaunchpadFeatures


class TestLaunchpadFeatures(unittest.TestCase):
    """Test LaunchpadFeatures Pydantic model."""

    def test_valid_features(self):
        features = LaunchpadFeatures(
            Faults=["debt spiral", "gatekeeping failure"],
            Levers=["emerging platform", "regulatory gap"],
            Scarcities=["limited attention"],
            Guard_Pressure=0.65,
        )
        self.assertEqual(len(features.faults), 2)
        self.assertAlmostEqual(features.guard_pressure, 0.65)

    def test_default_guard_pressure(self):
        features = LaunchpadFeatures()
        self.assertEqual(features.guard_pressure, 0.5)

    def test_guard_pressure_out_of_range(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            LaunchpadFeatures(Guard_Pressure=1.5)

    def test_guard_pressure_negative(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            LaunchpadFeatures(Guard_Pressure=-0.1)

    def test_json_roundtrip(self):
        features = LaunchpadFeatures(
            Faults=["fault1"], Levers=["lever1"], Scarcities=[], Guard_Pressure=0.7
        )
        json_str = features.model_dump_json()
        parsed = LaunchpadFeatures.model_validate_json(json_str)
        self.assertEqual(parsed.Guard_Pressure, 0.7)


if __name__ == "__main__":
    unittest.main()
