"""Testes da camada de carregamento PyTorch."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import torch
from PIL import Image

from ml.data import (
    TARGET_LABELS,
    ObstacleDataset,
    build_image_transform,
    create_obstacle_dataloaders,
    create_training_dataloaders,
    validate_batch,
)


class ObstacleDatasetTests(unittest.TestCase):
    def _temporary_path(self, suffix: str) -> Path:
        temporary_file = tempfile.NamedTemporaryFile(
            suffix=suffix, dir=Path.cwd(), delete=False
        )
        temporary_file.close()
        path = Path(temporary_file.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def _create_image(self, color: tuple[int, int, int] = (40, 80, 120)) -> Path:
        path = self._temporary_path(".png")
        Image.new("RGB", (40, 30), color=color).save(path)
        return path

    def _create_csv(self, rows: list[tuple[str, tuple[int, ...]]]) -> Path:
        path = self._temporary_path(".csv")
        header = "filename," + ",".join(TARGET_LABELS) + "\n"
        content = header + "".join(
            f"{filename},{','.join(str(value) for value in labels)}\n"
            for filename, labels in rows
        )
        path.write_text(content, encoding="utf-8")
        return path

    def test_returns_normalized_image_and_ordered_float_labels(self) -> None:
        image = self._create_image()
        expected = (1, 0, 1, 0, 1, 0, 1)
        csv_path = self._create_csv([(image.name, expected)])
        dataset = ObstacleDataset(
            csv_path,
            Path.cwd(),
            transform=build_image_transform(train=False, image_size=64),
        )

        transformed_image, labels = dataset[0]

        self.assertEqual(len(dataset), 1)
        self.assertEqual(transformed_image.shape, (3, 64, 64))
        self.assertEqual(transformed_image.dtype, torch.float32)
        self.assertEqual(labels.dtype, torch.float32)
        self.assertEqual(labels.tolist(), list(expected))

    def test_rejects_invalid_binary_label(self) -> None:
        image = self._create_image()
        csv_path = self._create_csv([(image.name, (1, 0, 2, 0, 1, 0, 1))])

        with self.assertRaisesRegex(ValueError, "parked-car"):
            ObstacleDataset(csv_path, Path.cwd())

    def test_rejects_missing_image(self) -> None:
        csv_path = self._create_csv(
            [("missing.png", (1, 0, 0, 0, 0, 0, 0))]
        )

        with self.assertRaises(FileNotFoundError):
            ObstacleDataset(csv_path, Path.cwd())

    def test_creates_and_validates_train_and_test_batches(self) -> None:
        first_image = self._create_image()
        second_image = self._create_image(color=(120, 80, 40))
        rows = [
            (first_image.name, (1, 0, 0, 1, 0, 0, 1)),
            (second_image.name, (0, 1, 1, 0, 1, 1, 0)),
        ]
        train_csv = self._create_csv(rows)
        test_csv = self._create_csv(rows[:1])

        loaders = create_obstacle_dataloaders(
            train_csv=train_csv,
            test_csv=test_csv,
            image_directory=Path.cwd(),
            batch_size=2,
            image_size=32,
            pin_memory=False,
        )
        train_summary = validate_batch(loaders.train)
        test_summary = validate_batch(loaders.test)

        self.assertEqual(train_summary.image_shape, (2, 3, 32, 32))
        self.assertEqual(train_summary.label_shape, (2, 7))
        self.assertEqual(test_summary.image_shape, (1, 3, 32, 32))
        self.assertEqual(test_summary.label_shape, (1, 7))

    def test_train_validation_split_is_distinct_and_reproducible(self) -> None:
        image = self._create_image()
        labels = (1, 0, 0, 1, 0, 0, 1)
        csv_path = self._create_csv([(image.name, labels)] * 10)

        first = create_training_dataloaders(
            train_csv=csv_path,
            image_directory=Path.cwd(),
            batch_size=2,
            image_size=32,
            pin_memory=False,
            validation_fraction=0.2,
            seed=42,
        )
        second = create_training_dataloaders(
            train_csv=csv_path,
            image_directory=Path.cwd(),
            batch_size=2,
            image_size=32,
            pin_memory=False,
            validation_fraction=0.2,
            seed=42,
        )

        first_train = tuple(first.train.dataset.indices)
        first_validation = tuple(first.validation.dataset.indices)
        second_train = tuple(second.train.dataset.indices)
        second_validation = tuple(second.validation.dataset.indices)

        self.assertEqual(len(first_train), 8)
        self.assertEqual(len(first_validation), 2)
        self.assertTrue(set(first_train).isdisjoint(first_validation))
        self.assertEqual(set(first_train) | set(first_validation), set(range(10)))
        self.assertEqual(first_train, second_train)
        self.assertEqual(first_validation, second_validation)


if __name__ == "__main__":
    unittest.main()

