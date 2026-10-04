"""Testes rápidos do modelo, treino e métricas do MVP0."""

from __future__ import annotations

import io
import math
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch
from torch import nn
from torch.optim import AdamW
from torch.utils.data import DataLoader, TensorDataset

from ml.data.obstacles import TARGET_LABELS
from ml.evaluate import calculate_metrics, evaluate_model, load_trained_model
from ml.model import create_model
from ml.predict import build_predictions, load_image_tensor
from ml.train import select_label_thresholds, train_model, train_one_epoch


class Mvp0TrainingTests(unittest.TestCase):
    def test_resnet18_has_one_output_per_target_label(self) -> None:
        model = create_model(pretrained=False)

        output = model(torch.randn(2, 3, 64, 64))

        self.assertEqual(output.shape, (2, len(TARGET_LABELS)))

    def test_train_one_epoch_returns_finite_loss(self) -> None:
        images = torch.randn(4, 3, 4, 4)
        labels = torch.randint(0, 2, (4, len(TARGET_LABELS))).float()
        loader = DataLoader(TensorDataset(images, labels), batch_size=2)
        model = nn.Sequential(
            nn.Flatten(),
            nn.Linear(3 * 4 * 4, len(TARGET_LABELS)),
        )
        criterion = nn.BCEWithLogitsLoss()
        optimizer = AdamW(model.parameters(), lr=1e-3)

        loss = train_one_epoch(
            model,
            loader,
            criterion,
            optimizer,
            torch.device("cpu"),
        )

        self.assertTrue(math.isfinite(loss))
        self.assertGreater(loss, 0)

    def test_calculates_metrics_per_label(self) -> None:
        true_positives = torch.tensor([2, 0, 1, 1, 1, 1, 1])
        false_positives = torch.tensor([1, 0, 0, 0, 0, 0, 0])
        false_negatives = torch.tensor([2, 0, 0, 0, 0, 0, 0])

        metrics = calculate_metrics(
            true_positives,
            false_positives,
            false_negatives,
            (0.5,) * len(TARGET_LABELS),
        )

        self.assertEqual(tuple(item.label for item in metrics), TARGET_LABELS)
        self.assertAlmostEqual(metrics[0].precision, 2 / 3)
        self.assertAlmostEqual(metrics[0].recall, 1 / 2)
        self.assertAlmostEqual(metrics[0].f1, 4 / 7)
        self.assertEqual(metrics[1].f1, 0.0)

    def test_checkpoint_preserves_label_order(self) -> None:
        model = create_model(pretrained=False)
        temporary_file = tempfile.NamedTemporaryFile(
            suffix=".pt",
            dir=Path.cwd(),
            delete=False,
        )
        temporary_file.close()
        checkpoint_path = Path(temporary_file.name)
        self.addCleanup(checkpoint_path.unlink, missing_ok=True)
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "labels": TARGET_LABELS,
                "epoch": 1,
                "train_loss": 0.5,
                "validation_loss": 0.6,
                "thresholds": {label: 0.5 for label in TARGET_LABELS},
            },
            checkpoint_path,
        )

        loaded_model, thresholds = load_trained_model(
            checkpoint_path,
            torch.device("cpu"),
        )

        self.assertEqual(loaded_model.fc.out_features, len(TARGET_LABELS))
        self.assertEqual(thresholds, (0.5,) * len(TARGET_LABELS))

    def test_checkpoint_is_selected_by_validation_loss_without_test_csv(self) -> None:
        checkpoint_file = tempfile.NamedTemporaryFile(
            suffix=".pt",
            dir=Path.cwd(),
            delete=False,
        )
        checkpoint_file.close()
        checkpoint_path = Path(checkpoint_file.name)
        self.addCleanup(checkpoint_path.unlink, missing_ok=True)

        tiny_model = nn.Linear(1, 1)
        loaders = SimpleNamespace(train=object(), validation=object())
        train_csv = Path("train-only.csv")

        with (
            patch("ml.train.torch.cuda.is_available", return_value=False),
            patch("ml.train.create_model", return_value=tiny_model),
            patch(
                "ml.train.create_training_dataloaders",
                return_value=loaders,
            ) as create_loaders,
            patch("ml.train.train_one_epoch", side_effect=[0.4, 0.3, 0.2]),
            patch(
                "ml.train.calculate_validation_loss",
                side_effect=[0.5, 0.6, 0.4],
            ),
            patch(
                "ml.train.calibrate_checkpoint_thresholds",
                return_value={label: 0.5 for label in TARGET_LABELS},
            ) as calibrate,
            patch("ml.train.print_thresholds"),
        ):
            with redirect_stdout(io.StringIO()):
                train_model(
                    epochs=3,
                    checkpoint_path=checkpoint_path,
                    train_csv=train_csv,
                    image_directory=Path("images"),
                )

        checkpoint = torch.load(
            checkpoint_path,
            map_location="cpu",
            weights_only=True,
        )
        self.assertEqual(checkpoint["epoch"], 3)
        self.assertEqual(checkpoint["train_loss"], 0.2)
        self.assertEqual(checkpoint["validation_loss"], 0.4)
        calibrate.assert_called_once_with(
            checkpoint_path,
            loaders.validation,
            torch.device("cpu"),
        )
        create_loaders.assert_called_once_with(
            train_csv=train_csv,
            image_directory=Path("images"),
            batch_size=32,
            num_workers=0,
            validation_fraction=0.2,
            seed=42,
        )

    def test_selects_thresholds_per_label_and_preserves_order(self) -> None:
        probabilities = torch.tensor(
            [
                [0.9, 0.65, 0.45, 0.25, 0.35, 0.55, 0.65],
                [0.8, 0.61, 0.42, 0.22, 0.32, 0.52, 0.61],
                [0.7, 0.59, 0.35, 0.19, 0.29, 0.49, 0.59],
                [0.6, 0.58, 0.10, 0.10, 0.10, 0.10, 0.58],
            ]
        )
        targets = torch.tensor(
            [
                [0, 1, 1, 1, 1, 1, 1],
                [0, 1, 1, 1, 1, 1, 1],
                [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0],
            ],
            dtype=torch.float32,
        )

        thresholds = select_label_thresholds(probabilities, targets)

        self.assertEqual(tuple(thresholds), TARGET_LABELS)
        self.assertEqual(
            tuple(thresholds.values()),
            (0.5, 0.6, 0.4, 0.2, 0.3, 0.5, 0.6),
        )

    def test_evaluation_applies_saved_threshold_order(self) -> None:
        probabilities = torch.tensor(
            [[0.3, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]],
            dtype=torch.float32,
        )
        logits = torch.logit(probabilities)

        class FixedModel(nn.Module):
            def forward(self, images: torch.Tensor) -> torch.Tensor:
                return logits.expand(images.shape[0], -1)

        images = torch.zeros(1, 3, 4, 4)
        labels = torch.tensor([[1, 0, 0, 0, 0, 0, 0]], dtype=torch.float32)
        loader = DataLoader(TensorDataset(images, labels), batch_size=1)
        thresholds = (0.2, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6)

        metrics = evaluate_model(
            FixedModel(),
            loader,
            torch.device("cpu"),
            thresholds,
        )

        self.assertEqual(tuple(item.threshold for item in metrics), thresholds)
        self.assertEqual(metrics[0].f1, 1.0)
        self.assertTrue(all(item.f1 == 0.0 for item in metrics[1:]))

    def test_prediction_applies_each_threshold_in_target_label_order(self) -> None:
        probabilities = (0.3, 0.19, 0.4, 0.21, 0.29, 0.2, 0.31)
        thresholds = (0.3, 0.2, 0.4, 0.2, 0.3, 0.2, 0.3)

        predictions = build_predictions(probabilities, thresholds)

        self.assertEqual(tuple(item.label for item in predictions), TARGET_LABELS)
        self.assertEqual(
            tuple(item.threshold for item in predictions),
            thresholds,
        )
        self.assertEqual(
            tuple(item.detected for item in predictions),
            (True, False, True, True, False, True, True),
        )

    def test_prediction_rejects_invalid_image(self) -> None:
        temporary_file = tempfile.NamedTemporaryFile(
            suffix=".jpg",
            dir=Path.cwd(),
            delete=False,
        )
        invalid_image_path = Path(temporary_file.name)
        temporary_file.write(b"not an image")
        temporary_file.close()

        try:
            with self.assertRaisesRegex(ValueError, "imagem válida"):
                load_image_tensor(invalid_image_path)
        finally:
            invalid_image_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

