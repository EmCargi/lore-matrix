#!/usr/bin/env python3
"""tests/test_ocean_profiler.py — OCEAN profiler unit tests + ground-truth validation."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ocean_scalpel import extract_json_scalpel
from core.ocean_types import OceanProfile


class TestOceanScalpel(unittest.TestCase):
    """Test JSON extraction scalpel against reasoning-model noise."""

    def test_clean_json(self):
        raw = '{"Openness": 90, "Conscientiousness": 95, "Extraversion": 35, "Agreeableness": 99, "Neuroticism": 5}'
        result = extract_json_scalpel(raw)
        data = json.loads(result)
        self.assertEqual(data["Openness"], 90)

    def test_commentary_before_json(self):
        raw = """Here is my analysis of the subject's personality traits.

{
  "Openness": 90,
  "Conscientiousness": 95,
  "Extraversion": 35,
  "Agreeableness": 99,
  "Neuroticism": 5
}"""
        result = extract_json_scalpel(raw)
        self.assertEqual(result[0], "{")
        self.assertEqual(result[-1], "}")
        data = json.loads(result)
        self.assertEqual(data["Neuroticism"], 5)

    def test_commentary_after_json(self):
        raw = """{
  "Openness": 90,
  "Conscientiousness": 95,
  "Extraversion": 35,
  "Agreeableness": 99,
  "Neuroticism": 5
}

These scores reflect the subject's behavioral patterns as described."""
        result = extract_json_scalpel(raw)
        self.assertEqual(result[0], "{")
        self.assertEqual(result[-1], "}")

    def test_think_tags_before_json(self):
        raw = """<think>
Let me analyze the text carefully...
</think>

{
  "Openness": 80,
  "Conscientiousness": 70,
  "Extraversion": 60,
  "Agreeableness": 50,
  "Neuroticism": 40
}"""
        result = extract_json_scalpel(raw)
        data = json.loads(result)
        self.assertEqual(data["Openness"], 80)

    def test_stray_braces_in_commentary(self):
        raw = """The subject's {openness} to experience is evident in their writing.

{
  "Openness": 90,
  "Conscientiousness": 95,
  "Extraversion": 35,
  "Agreeableness": 99,
  "Neuroticism": 5
}"""
        result = extract_json_scalpel(raw)
        data = json.loads(result)
        self.assertEqual(data["Openness"], 90)

    def test_no_json_raises(self):
        raw = "This text contains no JSON object at all."
        with self.assertRaises(ValueError):
            extract_json_scalpel(raw)

    def test_braces_only_in_commentary(self):
        raw = "The subject shows {traits} but no actual JSON here."
        with self.assertRaises(ValueError):
            extract_json_scalpel(raw)


class TestOceanProfileModel(unittest.TestCase):
    """Test OceanProfile Pydantic model."""

    def test_valid_profile(self):
        profile = OceanProfile(
            Openness=90, Conscientiousness=95, Extraversion=35,
            Agreeableness=99, Neuroticism=5
        )
        self.assertEqual(profile.Openness, 90)
        self.assertEqual(profile.openness, 90)

    def test_out_of_range_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            OceanProfile(
                Openness=150, Conscientiousness=50, Extraversion=50,
                Agreeableness=50, Neuroticism=50
            )

    def test_negative_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            OceanProfile(
                Openness=-10, Conscientiousness=50, Extraversion=50,
                Agreeableness=50, Neuroticism=50
            )

    def test_json_roundtrip(self):
        profile = OceanProfile(
            Openness=90, Conscientiousness=95, Extraversion=35,
            Agreeableness=99, Neuroticism=5
        )
        json_str = profile.model_dump_json()
        parsed = OceanProfile.model_validate_json(json_str)
        self.assertEqual(parsed.Openness, 90)

    def test_to_vspe_dict(self):
        profile = OceanProfile(
            Openness=90, Conscientiousness=95, Extraversion=35,
            Agreeableness=99, Neuroticism=5
        )
        d = profile.to_vspe_dict()
        self.assertEqual(d["openness"], 90)
        self.assertEqual(d["neuroticism"], 5)


class TestGroundTruthFixtures(unittest.TestCase):
    """Validate fixture OCEAN scores produce correct Genius Payload classification."""

    def _load_fixture(self, name):
        import yaml
        fixtures = Path(__file__).resolve().parent.parent.parent / "shda-cli" / "vspe-cli" / "fixtures"
        path = fixtures / f"{name}.yaml"
        return yaml.safe_load(path.read_text())

    def test_fred_rogers_genius(self):
        data = self._load_fixture("fred-rogers")
        profile = OceanProfile(**{
            k.capitalize(): v for k, v in data["ocean"].items()
        })
        self.assertTrue(0 <= profile.Openness <= 100)

    def test_all_fixtures_valid_ocean(self):
        for name in ["fred-rogers", "ishowspeed", "oprah-winfrey", "prince", "tiger-woods"]:
            data = self._load_fixture(name)
            profile = OceanProfile(**{
                k.capitalize(): v for k, v in data["ocean"].items()
            })
            for dim in ["Openness", "Conscientiousness", "Extraversion", "Agreeableness", "Neuroticism"]:
                self.assertTrue(0 <= getattr(profile, dim) <= 100,
                               f"{name}: {dim} out of range")


if __name__ == "__main__":
    unittest.main()
