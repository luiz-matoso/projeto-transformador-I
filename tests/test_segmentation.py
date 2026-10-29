"""Testes unitários do pipeline de segmentação sem usar o dataset real."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

import torch
from PIL import Image

from ml.segmentation.dataset import (
    CirculationPathDataset,
    SegmentationRecord,
    audit_segmentation_annotations,
    create_grouped_split,
    normalized_point_to_pixel,
    parse_polygons,
    rasterize_polygons,
    resize_binary_mask,
)


class SegmentationDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def test_normalized_coordinates_map_to_image_edges(self) -> None:
        self.assertEqual(normalized_point_to_pixel((0, 0), 11, 21), (0, 0))
        self.assertEqual(normalized_point_to_pixel((1, 1), 11, 21), (10, 20))
        self.assertEqual(normalized_point_to_pixel((0.5, 0.5), 11, 21), (5, 10))

    def test_rasterization_is_binary_and_fills_polygon(self) -> None:
        polygon = (((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)),)
        mask = rasterize_polygons(polygon, 10, 10)
        self.assertEqual(mask.getpixel((5, 5)), 1)
        self.assertEqual(mask.getpixel((0, 0)), 0)
        self.assertLessEqual(set(mask.tobytes()), {0, 1})

    def test_resize_uses_nearest_and_remains_binary(self) -> None:
        mask = Image.new("L", (2, 2), 0)
        mask.putpixel((1, 1), 1)
        resized = resize_binary_mask(mask, (17, 19))
        self.assertEqual(resized.size, (17, 19))
        self.assertLessEqual(set(resized.tobytes()), {0, 1})

    def test_polygon_parser_rejects_missing_points_and_out_of_range(self) -> None:
        self.assertEqual(len(parse_polygons("[[[0,0],[1,0],[0,1]]]")), 1)
        with self.assertRaisesRegex(ValueError, "3 pontos"):
            parse_polygons("[[[0,0],[1,0]]]" )
        with self.assertRaisesRegex(ValueError, r"\[0, 1\]"):
            parse_polygons("[[[0,0],[1.1,0],[0,1]]]" )

    def _record(self, index: int, panorama: str | None = None) -> SegmentationRecord:
        subsets = ("Obstacle", "CurbRamp", "SurfaceProblem")
        return SegmentationRecord(
            filename=f"{index}.png",
            local_filename=f"subset/{index}.png",
            image_path=self.root / f"{index}.png",
            subset=subsets[index % 3],
            panorama_id=panorama or f"panorama-{index}",
            polygons=(((0.1, 0.1), (0.9, 0.1), (0.5, 0.9)),),
            image_width=32,
            image_height=24,
        )

    def test_split_is_deterministic_exact_and_disjoint(self) -> None:
        records = [self._record(index) for index in range(105)]
        first = create_grouped_split(records, seed=42)
        second = create_grouped_split(records, seed=42)
        self.assertEqual(first, second)
        self.assertEqual(Counter(first.values()), {"train": 75, "validation": 15, "test": 15})
        split_sets = {split: {name for name, value in first.items() if value == split} for split in set(first.values())}
        self.assertFalse(split_sets["train"] & split_sets["validation"])
        self.assertFalse(split_sets["train"] & split_sets["test"])
        self.assertFalse(split_sets["validation"] & split_sets["test"])

    def test_same_panorama_never_crosses_splits(self) -> None:
        records = [self._record(index, "shared" if index in {0, 1} else None) for index in range(105)]
        assignments = create_grouped_split(records, seed=42)
        by_panorama: dict[str, set[str]] = defaultdict(set)
        for record in records:
            by_panorama[record.panorama_id].add(assignments[record.filename])
        self.assertTrue(all(len(splits) == 1 for splits in by_panorama.values()))

    def test_audit_parses_annotation_and_dataset_loads_example(self) -> None:
        pilot = self.root / "pilot"
        image_path = pilot / "images" / "obstacle" / "example.png"
        image_path.parent.mkdir(parents=True)
        Image.new("RGB", (32, 24), "white").save(image_path)
        with (pilot / "pilot_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("annotation_filename", "local_filename", "subset", "panorama_id"),
            )
            writer.writeheader()
            writer.writerow(
                {
                    "annotation_filename": "example.png",
                    "local_filename": "obstacle/example.png",
                    "subset": "Obstacle",
                    "panorama_id": "gsv-city-1",
                }
            )
        annotations = self.root / "annotations.csv"
        with annotations.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("filename", "circulation_path_status", "circulation_path", "image_width", "image_height"),
            )
            writer.writeheader()
            writer.writerow(
                {
                    "filename": "example.png",
                    "circulation_path_status": "annotated",
                    "circulation_path": json.dumps([[[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]]]),
                    "image_width": 32,
                    "image_height": 24,
                }
            )
        records, issues = audit_segmentation_annotations(annotations, pilot)
        self.assertEqual(issues, [])
        self.assertEqual(len(records), 1)
        sample = CirculationPathDataset(records, image_size=16)[0]
        self.assertEqual(tuple(sample["pixel_values"].shape), (3, 16, 16))
        self.assertEqual(tuple(sample["labels"].shape), (16, 16))
        self.assertEqual(sample["labels"].dtype, torch.long)
        self.assertLessEqual(set(torch.unique(sample["labels"]).tolist()), {0, 1})


if __name__ == "__main__":
    unittest.main()
