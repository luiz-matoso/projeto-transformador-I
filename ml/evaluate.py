"""Avaliação multilabel do checkpoint produzido pelo MVP0."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader

from ml.data.obstacles import TARGET_LABELS, create_test_dataloader
from ml.model import create_model

DEFAULT_CHECKPOINT = Path("best_model.pt")


@dataclass(frozen=True)
class LabelMetrics:
    """Métricas binárias de uma label."""

    label: str
    threshold: float
    precision: float
    recall: float
    f1: float


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def calculate_metrics(
    true_positives: Tensor,
    false_positives: Tensor,
    false_negatives: Tensor,
    thresholds: Sequence[float],
) -> tuple[LabelMetrics, ...]:
    """Calcula precision, recall e F1 por label a partir das contagens."""

    expected_shape = (len(TARGET_LABELS),)
    if len(thresholds) != len(TARGET_LABELS):
        raise ValueError(
            f"Esperados {len(TARGET_LABELS)} thresholds, "
            f"recebidos {len(thresholds)}"
        )
    for name, values in (
        ("true_positives", true_positives),
        ("false_positives", false_positives),
        ("false_negatives", false_negatives),
    ):
        if tuple(values.shape) != expected_shape:
            raise ValueError(
                f"{name} deve ter shape {expected_shape}, recebido "
                f"{tuple(values.shape)}"
            )

    metrics: list[LabelMetrics] = []
    for index, label in enumerate(TARGET_LABELS):
        tp = int(true_positives[index].item())
        fp = int(false_positives[index].item())
        fn = int(false_negatives[index].item())
        precision = _safe_ratio(tp, tp + fp)
        recall = _safe_ratio(tp, tp + fn)
        f1 = _safe_ratio(2 * precision * recall, precision + recall)
        metrics.append(
            LabelMetrics(label, float(thresholds[index]), precision, recall, f1)
        )
    return tuple(metrics)


def load_trained_model(
    checkpoint_path: str | Path,
    device: torch.device,
) -> tuple[nn.Module, tuple[float, ...]]:
    """Carrega o modelo e os thresholds associados às labels."""

    checkpoint = torch.load(
        Path(checkpoint_path),
        map_location=device,
        weights_only=True,
    )
    checkpoint_labels = tuple(checkpoint.get("labels", ()))
    if checkpoint_labels != TARGET_LABELS:
        raise ValueError(
            "Ordem de labels incompatível no checkpoint. "
            f"Esperado {TARGET_LABELS}, recebido {checkpoint_labels}"
        )

    saved_thresholds = checkpoint.get("thresholds")
    if not isinstance(saved_thresholds, dict):
        raise ValueError("O checkpoint não contém thresholds por label")
    if tuple(saved_thresholds) != TARGET_LABELS:
        raise ValueError(
            "Ordem de thresholds incompatível no checkpoint. "
            f"Esperado {TARGET_LABELS}, recebido {tuple(saved_thresholds)}"
        )
    thresholds = tuple(float(saved_thresholds[label]) for label in TARGET_LABELS)
    if any(not 0.0 < threshold < 1.0 for threshold in thresholds):
        raise ValueError("Todos os thresholds devem estar entre 0 e 1")

    model = create_model(pretrained=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    return model.to(device), thresholds


def evaluate_model(
    model: nn.Module,
    loader: DataLoader[tuple[Tensor, Tensor]],
    device: torch.device,
    thresholds: Sequence[float],
) -> tuple[LabelMetrics, ...]:
    """Avalia no teste usando um threshold específico para cada label."""

    if len(thresholds) != len(TARGET_LABELS):
        raise ValueError(f"Esperados {len(TARGET_LABELS)} thresholds")
    if any(not 0.0 < threshold < 1.0 for threshold in thresholds):
        raise ValueError("Todos os thresholds devem estar entre 0 e 1")

    label_count = len(TARGET_LABELS)
    threshold_tensor = torch.tensor(
        thresholds,
        dtype=torch.float32,
        device=device,
    ).unsqueeze(0)
    true_positives = torch.zeros(label_count, dtype=torch.long, device=device)
    false_positives = torch.zeros(label_count, dtype=torch.long, device=device)
    false_negatives = torch.zeros(label_count, dtype=torch.long, device=device)

    model.eval()
    with torch.inference_mode():
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            targets = labels.to(device, non_blocking=True) >= 0.5
            predictions = torch.sigmoid(model(images)) >= threshold_tensor

            true_positives += (predictions & targets).sum(dim=0)
            false_positives += (predictions & ~targets).sum(dim=0)
            false_negatives += (~predictions & targets).sum(dim=0)

    return calculate_metrics(
        true_positives.cpu(),
        false_positives.cpu(),
        false_negatives.cpu(),
        thresholds,
    )


def print_metrics(metrics: Sequence[LabelMetrics]) -> None:
    """Exibe métricas por label e macro F1."""

    print(
        f"{'Label':<24} {'Threshold':>10} {'Precision':>10} "
        f"{'Recall':>10} {'F1':>10}"
    )
    for item in metrics:
        print(
            f"{item.label:<24} {item.threshold:>10.1f} "
            f"{item.precision:>10.4f} "
            f"{item.recall:>10.4f} {item.f1:>10.4f}"
        )
    macro_f1 = sum(item.f1 for item in metrics) / len(metrics) if metrics else 0.0
    print(f"\nMacro F1: {macro_f1:.4f}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Avalia o melhor checkpoint.")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--num-workers", type=int, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    test_loader = create_test_dataloader(
        batch_size=args.batch_size,
        num_workers=args.num_workers,
    )
    model, thresholds = load_trained_model(args.checkpoint, device)
    metrics = evaluate_model(
        model,
        test_loader,
        device,
        thresholds,
    )
    print_metrics(metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

