import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from dataclasses import asdict

from ml.mobility_profile import MobilityProfile
from ml.mobility_rules import assess_transitability
from ml.observation import evaluate_observation
from ml.pipeline import apply_profile


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
        self.profile = MobilityProfile("adequate", "minor_problems", "minor", True)
        self.features = {"passage_width": "adequate", "obstruction": "none", "surface_condition": "regular",
                         "level_change": "none", "path_continuity": "continuous"}

    def observation(self, date):
        return {"source": "demo", "observed_at": date}

    def test_inside_validity_and_motor_preserved(self):
        for features in (self.features, {**self.features, "obstruction": "partial"}, {**self.features, "passage_width": "blocked"}):
            scene = {"features": features, "observation": self.observation(self.now - timedelta(hours=1))}
            result = apply_profile(scene, self.profile, evaluated_at=self.now)
            expected = asdict(assess_transitability(features, self.profile))
            for key, value in expected.items():
                self.assertEqual(result[key], value)
            self.assertTrue(result["observation"]["is_valid"])
            self.assertEqual(result["observation"]["source"], "demo")

    def test_expired_blocks_even_critical(self):
        with patch("ml.pipeline.assess_transitability") as motor:
            result = apply_profile({"features": {**self.features, "passage_width": "blocked"},
                                    "observation": self.observation(self.now - timedelta(days=2))}, self.profile, evaluated_at=self.now)
        motor.assert_not_called()
        self.assertEqual(result["classification"], "undetermined")
        self.assertEqual(result["reasons"][0]["code"], "observation_expired")

    def test_exact_expiration_and_before_boundary(self):
        date = self.now - timedelta(days=1)
        self.assertFalse(evaluate_observation(self.observation(date), evaluated_at=self.now)["is_valid"])
        self.assertTrue(evaluate_observation(self.observation(date), evaluated_at=self.now - timedelta(microseconds=1))["is_valid"])

    def test_missing_invalid_future(self):
        for date, code in ((None, "observation_date_missing"), ("bad", "observation_date_invalid"),
                           ("2026-11-26T10:00:00", "observation_date_invalid"),
                           (self.now + timedelta(seconds=1), "observation_date_future")):
            with self.subTest(date=date):
                result = apply_profile({"features": self.features, "observation": self.observation(date)}, self.profile, evaluated_at=self.now)
                self.assertEqual(result["classification"], "undetermined")
                self.assertEqual(result["reasons"][0]["code"], code)
        self.assertEqual(apply_profile({"features": self.features}, self.profile, evaluated_at=self.now)["classification"], "undetermined")

    def test_configurable_period_and_timezone(self):
        metadata = self.observation("2026-11-26T06:00:00-03:00")
        self.assertTrue(evaluate_observation(metadata, evaluated_at=self.now, validity_period=timedelta(hours=4))["is_valid"])
        self.assertFalse(evaluate_observation(metadata, evaluated_at=self.now, validity_period=timedelta(hours=2))["is_valid"])
        with self.assertRaises(ValueError):
            evaluate_observation(metadata, evaluated_at=self.now, validity_period=timedelta(0))

    def test_missing_source(self):
        self.assertEqual(evaluate_observation({"observed_at": self.now}, evaluated_at=self.now)["code"], "observation_source_missing")


if __name__ == "__main__":
    unittest.main()
