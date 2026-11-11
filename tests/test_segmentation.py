"""Testes unitários do pipeline de segmentação sem usar o dataset real."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
from PIL import Image

from ml.segmentation.dataset import (
    CirculationPathDataset,
    SegmentationRecord,
    audit_segmentation_annotations,
    create_expanded_split,
    create_grouped_split,
    normalized_point_to_pixel,
    parse_polygons,
    rasterize_polygons,
    resize_binary_mask,
)
from ml.segmentation.train_v2 import _v1_hashes, validate_v2_output_path
from ml.segmentation.predict import (
    SegformerPredictor,
    mask_to_normalized_polygons,
    predict_circulation_path,
    read_segformer_checkpoint,
    remove_small_components,
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

    def test_real_checkpoint_metadata_can_be_loaded_on_cpu(self) -> None:
        checkpoint = read_segformer_checkpoint(
            Path("artifacts/segmentation/best_segformer.pt"), map_location="cpu"
        )
        self.assertEqual(checkpoint["image_size"], 512)
        self.assertEqual(checkpoint["id2label"][1], "circulation_path")

    def test_small_component_is_removed_but_relevant_components_are_preserved(self) -> None:
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[10:40, 10:40] = 1
        mask[55:85, 55:90] = 1
        mask[2:4, 2:4] = 1
        cleaned = remove_small_components(mask, min_area_pixels=20, min_area_ratio=0)
        self.assertEqual(int(cleaned[2:4, 2:4].sum()), 0)
        self.assertGreater(int(cleaned[10:40, 10:40].sum()), 0)
        self.assertGreater(int(cleaned[55:85, 55:90].sum()), 0)

    def test_mask_becomes_simplified_normalized_polygons(self) -> None:
        mask = np.zeros((120, 160), dtype=np.uint8)
        cv_points = np.array([[10, 110], [30, 20], [80, 8], [145, 30], [150, 112]])
        import cv2

        cv2.fillPoly(mask, [cv_points], 1)
        polygons = mask_to_normalized_polygons(mask, min_area_pixels=1)
        self.assertEqual(len(polygons), 1)
        self.assertGreaterEqual(len(polygons[0]), 3)
        self.assertLess(len(polygons[0]), 30)
        self.assertTrue(
            all(0 <= coordinate <= 1 for point in polygons[0] for coordinate in point)
        )

    def test_mocked_cpu_inference_returns_editable_polygon(self) -> None:
        class Processor:
            def __call__(self, **kwargs):
                del kwargs
                return {"pixel_values": torch.zeros((1, 3, 16, 16))}

        class Model:
            def __call__(self, *, pixel_values):
                del pixel_values
                logits = torch.full((1, 2, 16, 16), -4.0)
                logits[:, 0] = 4.0
                logits[:, 0, 4:14, 3:13] = -4.0
                logits[:, 1, 4:14, 3:13] = 4.0
                return SimpleNamespace(logits=logits)

        predictor = SegformerPredictor(
            model=Model(),
            processor=Processor(),
            device=torch.device("cpu"),
            image_size=16,
            checkpoint_path=Path("fixture.pt"),
        )
        suggestion = predict_circulation_path(
            predictor, Image.new("RGB", (64, 48), "white")
        )
        self.assertEqual(suggestion.mask.shape, (48, 64))
        self.assertTrue(suggestion.polygons)
        self.assertTrue(
            all(
                0 <= coordinate <= 1
                for polygon in suggestion.polygons
                for point in polygon
                for coordinate in point
            )
        )

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

    def test_expanded_split_preserves_holdouts_and_uses_all_remaining_for_train(self) -> None:
        records = [self._record(index) for index in range(192)]
        frozen = self.root / "splits.csv"
        with frozen.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("filename", "split"))
            writer.writeheader()
            for index in range(105):
                split = "train" if index < 75 else "validation" if index < 90 else "test"
                writer.writerow({"filename": f"{index}.png", "split": split})

        first = create_expanded_split(records, frozen)
        second = create_expanded_split(records, frozen)

        self.assertEqual(first, second)
        self.assertEqual(Counter(first.values()), {"train": 162, "validation": 15, "test": 15})
        self.assertEqual(
            {name for name, split in first.items() if split == "validation"},
            {f"{index}.png" for index in range(75, 90)},
        )
        self.assertEqual(
            {name for name, split in first.items() if split == "test"},
            {f"{index}.png" for index in range(90, 105)},
        )
        split_sets = {
            split: {name for name, value in first.items() if value == split}
            for split in ("train", "validation", "test")
        }
        self.assertFalse(split_sets["train"] & split_sets["validation"])
        self.assertFalse(split_sets["train"] & split_sets["test"])
        self.assertFalse(split_sets["validation"] & split_sets["test"])

    def test_expanded_split_rejects_panorama_crossing_frozen_holdout(self) -> None:
        records = [self._record(index) for index in range(192)]
        records[106] = self._record(106, panorama=records[75].panorama_id)
        frozen = self.root / "splits.csv"
        with frozen.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("filename", "split"))
            writer.writeheader()
            for index in range(105):
                split = "train" if index < 75 else "validation" if index < 90 else "test"
                writer.writerow({"filename": f"{index}.png", "split": split})
        with self.assertRaisesRegex(ValueError, "Panoramas atravessam splits"):
            create_expanded_split(records, frozen)

    def test_v2_output_isolated_from_v1_artifacts(self) -> None:
        v1 = self.root / "segmentation"
        v2 = v1 / "v2"
        v1.mkdir()
        for name in (
            "best_segformer.pt",
            "splits.csv",
            "training_history.csv",
            "test_metrics.json",
        ):
            (v1 / name).write_bytes(f"v1-{name}".encode())
        before = _v1_hashes(v1)
        validate_v2_output_path(v2, v1)
        v2.mkdir()
        (v2 / "splits.csv").write_text("v2", encoding="utf-8")
        self.assertEqual(_v1_hashes(v1), before)
        with self.assertRaisesRegex(ValueError, "não pode ser"):
            validate_v2_output_path(v1, v1)

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

    def test_audit_excludes_unknown_without_treating_it_as_training_error(self) -> None:
        pilot = self.root / "pilot-unknown"
        image_path = pilot / "images" / "obstacle" / "unknown.png"
        image_path.parent.mkdir(parents=True)
        Image.new("RGB", (32, 24), "white").save(image_path)
        with (pilot / "pilot_manifest.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("annotation_filename", "local_filename", "subset", "panorama_id"),
            )
            writer.writeheader()
            writer.writerow(
                {
                    "annotation_filename": "unknown.png",
                    "local_filename": "obstacle/unknown.png",
                    "subset": "Obstacle",
                    "panorama_id": "panorama-unknown",
                }
            )
        annotations = self.root / "unknown.csv"
        with annotations.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "filename",
                    "circulation_path_status",
                    "circulation_path",
                    "image_width",
                    "image_height",
                ),
            )
            writer.writeheader()
            writer.writerow(
                {
                    "filename": "unknown.png",
                    "circulation_path_status": "unknown",
                    "circulation_path": "[]",
                    "image_width": 32,
                    "image_height": 24,
                }
            )
        records, issues = audit_segmentation_annotations(
            annotations, pilot, excluded_statuses={"unknown"}
        )
        self.assertEqual(records, [])
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
