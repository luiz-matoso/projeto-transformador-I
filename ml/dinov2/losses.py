"""Loss balanceada entre heads categóricas e multilabel."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import torch
import torch.nn.functional as F

from ml.dinov2 import CATEGORICAL_HEADS, MULTILABEL_HEADS
from ml.dinov2.dataset import DinoRecord


def compute_train_weights(
    records: Sequence[DinoRecord],
    classes: Mapping[str, Sequence[str]],
    *,
    max_pos_weight: float = 20.0,
) -> tuple[dict[str, torch.Tensor], dict[str, torch.Tensor]]:
    """Calcula pesos exclusivamente no train, limitando extremos de classes raras."""

    categorical: dict[str, torch.Tensor] = {}
    for head in CATEGORICAL_HEADS:
        counts = torch.tensor(
            [sum(record.categorical[head] == value for record in records) for value in classes[head]],
            dtype=torch.float32,
        )
        valid_total = counts.sum()
        weights = torch.where(
            counts > 0,
            valid_total / (len(classes[head]) * counts),
            torch.zeros_like(counts),
        )
        categorical[head] = weights
    multilabel: dict[str, torch.Tensor] = {}
    total = float(len(records))
    for head in MULTILABEL_HEADS:
        positives = torch.tensor(
            [sum(value in record.multilabel[head] for record in records) for value in classes[head]],
            dtype=torch.float32,
        )
        weights = torch.where(
            positives > 0,
            (total - positives) / positives,
            torch.ones_like(positives),
        ).clamp(max=max_pos_weight)
        multilabel[head] = weights
    return categorical, multilabel


def multitask_loss(
    outputs: Mapping[str, torch.Tensor],
    batch: Mapping,
    *,
    categorical_weights: Mapping[str, torch.Tensor] | None = None,
    multilabel_pos_weights: Mapping[str, torch.Tensor] | None = None,
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """Média uma loss por head para que heads largas não dominem o total."""

    head_losses: dict[str, torch.Tensor] = {}
    for head in CATEGORICAL_HEADS:
        mask = batch["categorical_masks"][head].bool()
        if not mask.any():
            continue
        weight = categorical_weights.get(head) if categorical_weights else None
        if weight is not None:
            weight = weight.to(outputs[head].device)
        head_losses[head] = F.cross_entropy(
            outputs[head][mask],
            batch["categorical_targets"][head][mask],
            weight=weight,
        )
    for head in MULTILABEL_HEADS:
        pos_weight = multilabel_pos_weights.get(head) if multilabel_pos_weights else None
        if pos_weight is not None:
            pos_weight = pos_weight.to(outputs[head].device)
        elementwise = F.binary_cross_entropy_with_logits(
            outputs[head],
            batch["multilabel_targets"][head],
            pos_weight=pos_weight,
            reduction="none",
        )
        head_losses[head] = elementwise.mean(dim=1).mean()
    if not head_losses:
        raise ValueError("Batch sem nenhuma head válida")
    return torch.stack(tuple(head_losses.values())).mean(), head_losses
