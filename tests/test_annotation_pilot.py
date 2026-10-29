"""Testes do piloto assistido e das regras de coerência."""

from __future__ import annotations

import csv
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.dataset.build_annotation_pilot import (
    PilotBuildError,
    build_pilot,
    read_directory_subset,
    read_zip_subset,
)
from tools.annotation_app.coherence import find_coherence_warnings
from tools.annotation_app.original_metadata import (
    find_pilot_manifest,
    load_pilot_manifest,
)


class CoherenceWarningTests(unittest.TestCase):
    def test_detects_only_the_six_requested_cross_field_patterns(self) -> None:
        cases = (
            ({"obstruction": "none", "obstacle_type": ["pole"]}, "obstruction_none_with_obstacles"),
            ({"obstruction": "full", "path_continuity": "continuous"}, "full_obstruction_with_continuous_path"),
            ({"passage_width": "blocked", "path_continuity": "continuous"}, "blocked_width_with_continuous_path"),
            ({"curb_access": "raised_no_ramp", "ramp_condition": "not_applicable"}, "raised_curb_without_ramp_assessment"),
            ({"curb_access": "ramp", "ramp_condition": "not_applicable"}, "ramp_with_not_applicable_condition"),
            ({"surface_condition": "regular", "surface_obstacle": ["cracks"]}, "regular_surface_with_problem"),
        )
        for values, expected_code in cases:
            with self.subTest(expected_code):
                self.assertIn(expected_code, {item.code for item in find_coherence_warnings(values)})

        self.assertEqual(find_coherence_warnings({"obstruction": "partial", "obstacle_type": ["pole"]}), ())

    def test_warning_does_not_reject_or_mutate_input(self) -> None:
        values = {"obstruction": "none", "obstacle_type": ["pole"]}
        original = {"obstruction": "none", "obstacle_type": ["pole"]}
        self.assertTrue(find_coherence_warnings(values))
        self.assertEqual(values, original)


class PilotBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.obstacle = self.root / "obstacle"
        self.surface_zip = self.root / "surface.zip"
        self.curb_zip = self.root / "curb.zip"
        self.annotations = self.root / "annotations.csv"
        self._make_directory_subset()
        self._make_zip_subset(self.surface_zip, "SurfaceProblem", ("cracks", "bumpy"))
        self._make_zip_subset(self.curb_zip, "CurbRamp", ("steep", "surface-problem"))
        self.annotations.write_text("filename\nshared-Obstacle.png\n", encoding="utf-8")

    @staticmethod
    def _csv_text(subset: str, labels: tuple[str, ...], indices: range) -> str:
        rows = [["filename", "normalized_x", "normalized_y", *labels]]
        for index in indices:
            filename = "shared-Obstacle.png" if subset == "Obstacle" and index == 0 else f"gsv-city-{index}-{subset}.png"
            positives = ["1" if (index + label_index) % 3 == 0 else "0" for label_index, _ in enumerate(labels)]
            rows.append([filename, "0.25", "0.75", *positives])
        return "\n".join(",".join(row) for row in rows) + "\n"

    def _make_directory_subset(self) -> None:
        (self.obstacle / "crops").mkdir(parents=True)
        labels = ("pole", "vegetation")
        for split, indices in (("train", range(0, 6)), ("test", range(6, 10))):
            text = self._csv_text("Obstacle", labels, indices)
            (self.obstacle / f"{split}.csv").write_text(text, encoding="utf-8")
            for row in list(csv.DictReader(text.splitlines())):
                (self.obstacle / "crops" / row["filename"]).write_bytes(b"obstacle")

    def _make_zip_subset(self, path: Path, subset: str, labels: tuple[str, ...]) -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zipped:
            for split, indices in (("train", range(0, 6)), ("test", range(6, 10))):
                text = self._csv_text(subset, labels, indices)
                zipped.writestr(f"{subset}/csv/{split}.csv", text)
                for row in csv.DictReader(text.splitlines()):
                    zipped.writestr(f"{subset}/crops/{row['filename']}", subset.encode())

    def test_parses_directory_and_zip_csvs_using_real_labels_and_splits(self) -> None:
        obstacle = read_directory_subset(self.obstacle)
        surface = read_zip_subset(self.surface_zip, "SurfaceProblem")
        curb = read_zip_subset(self.curb_zip, "CurbRamp")
        self.assertEqual({record.split for record in obstacle}, {"train", "test"})
        self.assertTrue(any("cracks" in record.labels for record in surface))
        self.assertTrue(any("steep" in record.labels for record in curb))

    def test_build_is_deterministic_preserves_annotations_and_extracts_only_selection(self) -> None:
        outputs = (self.root / "pilot-a", self.root / "pilot-b")
        for output in outputs:
            counts = build_pilot(
                obstacle=self.obstacle,
                surface_problem=self.surface_zip,
                curb_ramp=self.curb_zip,
                annotations=self.annotations,
                output=output,
                size=6,
                seed=42,
            )
            self.assertEqual(counts, {"Obstacle": 2, "SurfaceProblem": 2, "CurbRamp": 2})

        manifests = [(output / "pilot_manifest.csv").read_text(encoding="utf-8") for output in outputs]
        self.assertEqual(manifests[0], manifests[1])
        rows = list(csv.DictReader(manifests[0].splitlines()))
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({row["local_filename"] for row in rows}), 6)
        self.assertEqual(len(list((outputs[0] / "images").rglob("*.png"))), 6)
        human = next(row for row in rows if row["original_filename"] == "shared-Obstacle.png")
        self.assertEqual(human["annotation_status"], "annotated")
        self.assertEqual(human["annotation_filename"], "shared-Obstacle.png")
        self.assertTrue((outputs[0] / "pilot_summary.md").is_file())

        manifest_path = find_pilot_manifest(outputs[0] / "images")
        metadata = load_pilot_manifest(manifest_path, outputs[0] / "images")
        self.assertEqual(metadata[human["local_filename"]].annotation_filename, "shared-Obstacle.png")

    def test_filename_conflicts_between_subsets_do_not_overwrite(self) -> None:
        output = self.root / "pilot-conflicts"
        build_pilot(
            obstacle=self.obstacle,
            surface_problem=self.surface_zip,
            curb_ramp=self.curb_zip,
            annotations=self.annotations,
            output=output,
            size=6,
            seed=3,
        )
        local_names = [row["local_filename"] for row in csv.DictReader((output / "pilot_manifest.csv").read_text(encoding="utf-8").splitlines())]
        self.assertTrue(all(name.split("/", 1)[0] in {"obstacle", "surface_problem", "curb_ramp"} for name in local_names))

    def test_missing_zip_fails_without_creating_partial_output(self) -> None:
        output = self.root / "not-created"
        with self.assertRaisesRegex(PilotBuildError, "ausente"):
            build_pilot(
                obstacle=self.obstacle,
                surface_problem=self.root / "missing.zip",
                curb_ramp=self.curb_zip,
                annotations=self.annotations,
                output=output,
                size=6,
                seed=42,
            )
        self.assertFalse(output.exists())

    def test_sparse_categories_do_not_prevent_selection(self) -> None:
        records = read_zip_subset(self.surface_zip, "SurfaceProblem")
        self.assertTrue(any(not record.labels for record in records))
        output = self.root / "pilot-sparse"
        build_pilot(
            obstacle=self.obstacle,
            surface_problem=self.surface_zip,
            curb_ramp=self.curb_zip,
            annotations=self.annotations,
            output=output,
            size=3,
            seed=9,
        )
        self.assertEqual(len(list((output / "images").rglob("*.png"))), 3)


if __name__ == "__main__":
    unittest.main()
