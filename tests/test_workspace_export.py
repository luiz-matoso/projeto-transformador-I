import hashlib
import json
import unittest
from pathlib import Path

from scripts.export_workspace_data import build_payload, ROOT
from tools.annotation_app.core import load_schema


class WorkspaceExportTests(unittest.TestCase):
    def test_snapshot_is_reproducible_and_matches_authoritative_schema(self):
        first = build_payload()
        self.assertEqual(first, build_payload())
        schema = load_schema(ROOT / "annotations/annotation-schema.yaml")
        self.assertEqual(tuple(first["schema"]["columns"]), schema.csv_columns)
        self.assertEqual(first["dataset"]["total"], 200)
        self.assertEqual(first["dataset"]["statuses"], {"annotated": 192, "unknown": 8})
        self.assertEqual(len(first["schema"]["fields"]), 12)
        self.assertEqual(first["dataset"]["subsets"], {"Obstacle": 80, "SurfaceProblem": 70, "CurbRamp": 50})
        for path, digest in first["sources"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
        for experiment in first["experiments"]:
            if "DINO" in experiment["name"] or "comum" in experiment["name"]:
                self.assertEqual(experiment["split"], [134, 29, 29])
        self.assertNotIn("JWT_SECRET", json.dumps(first))
        saved = json.loads((ROOT / "frontend/src/generated/workspace.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json.dumps(first)), saved)
