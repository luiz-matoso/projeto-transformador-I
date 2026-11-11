import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
from PIL import Image
from torch import nn

from ml.dinov2 import ALL_HEADS, CATEGORICAL_HEADS, MULTILABEL_HEADS
from ml.dinov2.dataset import (
    DinoRecord,
    TransitabilityDinoDataset,
    create_grouped_multitask_split,
    emphasize_circulation_path,
    load_dinov2_records,
    load_head_classes,
)
from ml.dinov2.losses import multitask_loss
from ml.dinov2.metrics import select_multilabel_thresholds
from ml.dinov2.model import DinoV2MultiTask
from ml.dinov2.predict import predict_image


class FakeProcessor:
    def __call__(self, *, images, return_tensors):
        self.last_image = images
        self.return_tensors = return_tensors
        return {"pixel_values": torch.ones((1, 3, 16, 16), dtype=torch.float32)}


class FakeBackbone(nn.Module):
    def __init__(self, hidden_size: int = 8) -> None:
        super().__init__()
        self.config = SimpleNamespace(hidden_size=hidden_size)
        self.projection = nn.Linear(3, hidden_size)

    def forward(self, *, pixel_values):
        pooled = pixel_values.mean(dim=(2, 3))
        cls = self.projection(pooled).unsqueeze(1)
        patches = torch.zeros((pixel_values.size(0), 2, cls.size(-1)), device=cls.device)
        return SimpleNamespace(last_hidden_state=torch.cat((cls, patches), dim=1))


class DinoV2PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.classes = load_head_classes("annotations/annotation-schema.yaml")

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _record(self, index: int, panorama: str | None = None) -> DinoRecord:
        categorical = {
            "passage_width": "narrow",
            "obstruction": "partial",
            "surface_condition": "regular",
            "level_change": None if index == 0 else "none",
            "path_continuity": "continuous",
        }
        multilabel = {"obstacle_type": ("pole",), "surface_obstacle": ()}
        image_path = self.root / f"{index}.png"
        Image.new("RGB", (32, 24), (100, 120, 140)).save(image_path)
        return DinoRecord(
            filename=f"{index}.png",
            image_path=image_path,
            subset="Obstacle",
            panorama_id=panorama or f"p-{index}",
            polygons=(((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)),),
            image_width=32,
            image_height=24,
            categorical=categorical,
            multilabel=multilabel,
        )

    def test_parses_csv_and_excludes_non_annotated_rows(self) -> None:
        pilot = self.root / "pilot"
        image_path = pilot / "images" / "obstacle" / "sample.png"
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
                    "annotation_filename": "sample.png",
                    "local_filename": "obstacle/sample.png",
                    "subset": "Obstacle",
                    "panorama_id": "p-1",
                }
            )
        annotation = {
            "filename": "sample.png",
            "circulation_path_status": "annotated",
            "circulation_path": "[[[0.1,0.1],[0.9,0.1],[0.5,0.9]]]",
            "image_width": "32",
            "image_height": "24",
            "passage_width": "narrow",
            "obstruction": "partial",
            "surface_condition": "regular",
            "level_change": "unknown",
            "path_continuity": "continuous",
            "obstacle_type": '["pole"]',
            "surface_obstacle": "[]",
        }
        annotations = self.root / "annotations.csv"
        with annotations.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=annotation)
            writer.writeheader()
            writer.writerow(annotation)
        records, classes, statuses = load_dinov2_records(
            annotations, pilot, "annotations/annotation-schema.yaml"
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(statuses["annotated"], 1)
        self.assertIsNone(records[0].categorical["level_change"])
        self.assertEqual(records[0].multilabel["obstacle_type"], ("pole",))
        self.assertNotIn("unknown", classes["level_change"])

    def test_preprocessing_preserves_inside_and_attenuates_outside(self) -> None:
        image = Image.new("RGB", (20, 20), (200, 100, 50))
        polygon = (((0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)),)
        focused = emphasize_circulation_path(image, polygon, blur_radius=0)
        self.assertEqual(focused.getpixel((10, 10)), image.getpixel((10, 10)))
        self.assertNotEqual(focused.getpixel((0, 0)), image.getpixel((0, 0)))

    def test_dataset_encodes_unknown_and_multilabel(self) -> None:
        dataset = TransitabilityDinoDataset(
            [self._record(0)], self.classes, FakeProcessor()
        )
        sample = dataset[0]
        self.assertEqual(tuple(sample["pixel_values"].shape), (3, 16, 16))
        self.assertFalse(sample["categorical_masks"]["level_change"])
        self.assertEqual(int(sample["categorical_targets"]["level_change"]), -100)
        pole_index = self.classes["obstacle_type"].index("pole")
        self.assertEqual(float(sample["multilabel_targets"]["obstacle_type"][pole_index]), 1.0)
        self.assertEqual(float(sample["multilabel_targets"]["surface_obstacle"].sum()), 0.0)

    def test_forward_has_all_independent_head_shapes(self) -> None:
        model = DinoV2MultiTask(self.classes, backbone=FakeBackbone(), freeze_backbone=True)
        outputs = model(torch.ones((2, 3, 16, 16)))
        self.assertEqual(set(outputs), set(ALL_HEADS))
        for head in ALL_HEADS:
            self.assertEqual(tuple(outputs[head].shape), (2, len(self.classes[head])))
        self.assertFalse(any(parameter.requires_grad for parameter in model.backbone.parameters()))
        self.assertTrue(all(parameter.requires_grad for parameter in model.heads.parameters()))

    def _loss_batch(self) -> dict:
        return {
            "categorical_targets": {
                head: torch.tensor([0, 0], dtype=torch.long) for head in CATEGORICAL_HEADS
            },
            "categorical_masks": {
                head: torch.tensor([head != "level_change", head != "level_change"])
                for head in CATEGORICAL_HEADS
            },
            "multilabel_targets": {
                head: torch.zeros((2, len(self.classes[head]))) for head in MULTILABEL_HEADS
            },
        }

    def test_loss_ignores_unknown_head_and_averages_heads(self) -> None:
        outputs = {
            head: torch.zeros((2, len(self.classes[head])), requires_grad=True)
            for head in ALL_HEADS
        }
        first, losses = multitask_loss(outputs, self._loss_batch())
        changed = dict(outputs)
        changed["level_change"] = torch.full_like(outputs["level_change"], 1000)
        second, _ = multitask_loss(changed, self._loss_batch())
        self.assertTrue(torch.isfinite(first))
        self.assertAlmostEqual(float(first.detach()), float(second.detach()), places=6)
        self.assertNotIn("level_change", losses)

    def test_split_is_deterministic_disjoint_and_panorama_isolated(self) -> None:
        records = [self._record(index) for index in range(20)]
        first = create_grouped_multitask_split(records, seed=42)
        second = create_grouped_multitask_split(records, seed=42)
        self.assertEqual(first, second)
        self.assertEqual(Counter(first.values()), {"train": 14, "validation": 3, "test": 3})
        sets = {split: {name for name, value in first.items() if value == split} for split in set(first.values())}
        self.assertFalse(sets["train"] & sets["validation"])
        self.assertFalse(sets["train"] & sets["test"])
        self.assertFalse(sets["validation"] & sets["test"])

    def test_multilabel_thresholds_use_validation_f1(self) -> None:
        targets = np.array([[1, 0], [1, 0], [0, 1], [0, 1]])
        probabilities = np.array([[0.45, 0.1], [0.4, 0.2], [0.3, 0.65], [0.2, 0.6]])
        self.assertEqual(select_multilabel_thresholds(targets, probabilities), (0.4, 0.5))

    def test_cpu_inference_with_fake_backbone(self) -> None:
        model = DinoV2MultiTask(self.classes, backbone=FakeBackbone(), freeze_backbone=True)
        thresholds = {head: (0.5,) * len(self.classes[head]) for head in MULTILABEL_HEADS}
        result = predict_image(
            model,
            FakeProcessor(),
            self.classes,
            thresholds,
            torch.device("cpu"),
            Image.new("RGB", (32, 24), "white"),
        )
        self.assertEqual(set(result), set(ALL_HEADS))
        self.assertIn(result["passage_width"]["prediction"], self.classes["passage_width"])


if __name__ == "__main__":
    unittest.main()
