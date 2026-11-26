import tempfile
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import torch
from PIL import Image

from ml.mobility_profile import MobilityProfile
from ml.mobility_rules import assess_transitability
from ml.pipeline import apply_profile, infer_transitability


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.image_path = Path(self.temp.name) / "scene.png"
        Image.new("RGB", (24, 16), (120, 120, 120)).save(self.image_path)
        self.profile = MobilityProfile("adequate", "minor_problems", "minor", True)
        self.features = {"passage_width": "adequate", "obstruction": "none", "surface_condition": "regular",
                         "level_change": "none", "path_continuity": "continuous", "obstacle_type": ["pole"], "surface_obstacle": []}

    def run_pipeline(self, features):
        predictions = {head: {"predictions" if isinstance(value, list) else "prediction": value} for head, value in features.items()}
        mask = np.ones((16, 24), dtype=np.uint8)
        components = (object(), SimpleNamespace(classes={}), object(), {}, torch.device("cpu"), {"obstacle_type": {"stairs": {"reason": "insufficient_support"}}})
        with patch("ml.pipeline._load_components", return_value=components), \
             patch("ml.pipeline.predict_circulation_path", return_value=SimpleNamespace(mask=mask)) as segment, \
             patch("ml.pipeline.predict_image", return_value=predictions) as dino, \
             patch("ml.pipeline.assess_transitability", wraps=assess_transitability) as engine:
            result = infer_transitability(self.image_path, self.profile,
                                         observation={"source": "test", "observed_at": "2026-11-26T10:00:00Z"},
                                         evaluated_at=datetime(2026, 11, 26, 11, tzinfo=timezone.utc))
            engine.assert_called_once_with(features, self.profile)
            segment.assert_called_once()
            dino.assert_called_once()
            self.assertEqual(dino.call_args.args[-1].size, (24, 16))
        np.testing.assert_array_equal(result["mask"], mask)
        self.assertEqual(result["predictions"], predictions)
        self.assertIn("stairs", result["not_modeled"]["obstacle_type"])
        self.assertIn("slope", result["inactive_features"])
        self.assertEqual(result["reasons"], asdict(assess_transitability(features, self.profile))["reasons"])
        return result

    def test_transitable(self):
        result = self.run_pipeline(self.features)
        self.assertEqual(result["classification"], "transitable")
        self.assertEqual(result["severity"], "none")

    def test_critical(self):
        result = self.run_pipeline({**self.features, "passage_width": "narrow"})
        self.assertEqual(result["classification"], "non_transitable")
        self.assertEqual(result["severity"], "critical")

    def test_moderate_and_reasons_preserved(self):
        result = self.run_pipeline({**self.features, "obstruction": "partial"})
        self.assertEqual(result["classification"], "partially_transitable")
        self.assertIn("poste", result["reasons"][0]["message"])

    def test_undetermined_on_missing_feature(self):
        features = dict(self.features)
        del features["level_change"]
        result = self.run_pipeline(features)
        self.assertEqual(result["classification"], "undetermined")
        self.assertTrue(result["requires_review"])
        self.assertEqual(result["unassessed_features"], ["level_change"])

    def test_reapply_profile_without_visual_inference(self):
        with patch("ml.pipeline.observe_scene") as vision:
            result = apply_profile({"features": self.features, "observation": {"source": "test", "observed_at": "2026-11-26T10:00:00Z"}},
                                   MobilityProfile("wide", "regular_only", "none", False), evaluated_at=datetime(2026, 11, 26, 11, tzinfo=timezone.utc))
        vision.assert_not_called()
        self.assertEqual(result["classification"], "non_transitable")


if __name__ == "__main__":
    unittest.main()
