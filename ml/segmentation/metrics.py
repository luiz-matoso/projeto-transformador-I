"""Loss e métricas foreground para segmentação binária."""

from __future__ import annotations

import torch
import torch.nn.functional as F


def dice_loss(logits: torch.Tensor, targets: torch.Tensor, epsilon: float = 1e-6) -> torch.Tensor:
    probabilities = torch.softmax(logits, dim=1)[:, 1]
    foreground = (targets == 1).float()
    intersection = (probabilities * foreground).sum(dim=(1, 2))
    denominator = probabilities.sum(dim=(1, 2)) + foreground.sum(dim=(1, 2))
    return (1 - (2 * intersection + epsilon) / (denominator + epsilon)).mean()


def combined_segmentation_loss(logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    """Cross Entropy estabiliza pixels; Dice reduz domínio do background."""

    return F.cross_entropy(logits, targets) + dice_loss(logits, targets)


def binary_segmentation_counts(predictions: torch.Tensor, targets: torch.Tensor) -> tuple[int, int, int, int]:
    predicted = predictions.bool()
    actual = targets.bool()
    return (
        int((predicted & actual).sum().item()),
        int((predicted & ~actual).sum().item()),
        int((~predicted & actual).sum().item()),
        int((~predicted & ~actual).sum().item()),
    )


def metrics_from_counts(tp: int, fp: int, fn: int, tn: int) -> dict[str, float]:
    def safe(numerator: float, denominator: float) -> float:
        return numerator / denominator if denominator else 0.0

    return {
        "foreground_iou": safe(tp, tp + fp + fn),
        "dice": safe(2 * tp, 2 * tp + fp + fn),
        "precision": safe(tp, tp + fp),
        "recall": safe(tp, tp + fn),
        "pixel_accuracy": safe(tp + tn, tp + fp + fn + tn),
    }
