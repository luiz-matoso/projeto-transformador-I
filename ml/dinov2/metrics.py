"""Métricas transparentes por head sem dependência de scikit-learn."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np


def _safe(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def categorical_metrics(
    targets: np.ndarray,
    predictions: np.ndarray,
    classes: Sequence[str],
) -> dict:
    count = len(classes)
    confusion = np.zeros((count, count), dtype=np.int64)
    for target, prediction in zip(targets.astype(int), predictions.astype(int)):
        confusion[target, prediction] += 1
    per_class: dict[str, dict[str, float | int]] = {}
    f1_values: list[float] = []
    supports: list[int] = []
    for index, label in enumerate(classes):
        tp = int(confusion[index, index])
        fp = int(confusion[:, index].sum() - tp)
        fn = int(confusion[index, :].sum() - tp)
        support = int(confusion[index, :].sum())
        precision = _safe(tp, tp + fp)
        recall = _safe(tp, tp + fn)
        f1 = _safe(2 * precision * recall, precision + recall)
        per_class[label] = {
            "support": support,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
        f1_values.append(f1)
        supports.append(support)
    total = sum(supports)
    return {
        "macro_f1": float(np.mean(f1_values)),
        "weighted_f1": _safe(sum(f1 * support for f1, support in zip(f1_values, supports)), total),
        "accuracy": _safe(int(np.trace(confusion)), total),
        "per_class": per_class,
        "confusion_matrix": confusion.tolist(),
        "class_order": list(classes),
        "valid_samples": total,
    }


def multilabel_metrics(
    targets: np.ndarray,
    probabilities: np.ndarray,
    classes: Sequence[str],
    thresholds: Sequence[float],
) -> dict:
    predicted = probabilities >= np.asarray(thresholds)[None, :]
    actual = targets.astype(bool)
    per_label: dict[str, dict[str, float | int]] = {}
    f1_values: list[float] = []
    total_tp = total_fp = total_fn = 0
    for index, label in enumerate(classes):
        tp = int(np.logical_and(predicted[:, index], actual[:, index]).sum())
        fp = int(np.logical_and(predicted[:, index], ~actual[:, index]).sum())
        fn = int(np.logical_and(~predicted[:, index], actual[:, index]).sum())
        support = int(actual[:, index].sum())
        precision = _safe(tp, tp + fp)
        recall = _safe(tp, tp + fn)
        f1 = _safe(2 * precision * recall, precision + recall)
        per_label[label] = {
            "support": support,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "threshold": float(thresholds[index]),
        }
        f1_values.append(f1)
        total_tp += tp
        total_fp += fp
        total_fn += fn
    micro_precision = _safe(total_tp, total_tp + total_fp)
    micro_recall = _safe(total_tp, total_tp + total_fn)
    return {
        "macro_f1": float(np.mean(f1_values)),
        "micro_f1": _safe(2 * micro_precision * micro_recall, micro_precision + micro_recall),
        "precision": micro_precision,
        "recall": micro_recall,
        "per_label": per_label,
        "thresholds": {label: float(value) for label, value in zip(classes, thresholds)},
        "samples": int(targets.shape[0]),
    }


def select_multilabel_thresholds(
    targets: np.ndarray,
    probabilities: np.ndarray,
    *,
    candidates: Sequence[float] = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8),
) -> tuple[float, ...]:
    """Seleciona por F1 somente na validação; empate prefere proximidade de 0.5."""

    thresholds: list[float] = []
    for index in range(targets.shape[1]):
        actual = targets[:, index].astype(bool)
        scored: list[tuple[float, float]] = []
        for threshold in candidates:
            predicted = probabilities[:, index] >= threshold
            tp = int(np.logical_and(predicted, actual).sum())
            fp = int(np.logical_and(predicted, ~actual).sum())
            fn = int(np.logical_and(~predicted, actual).sum())
            precision = _safe(tp, tp + fp)
            recall = _safe(tp, tp + fn)
            f1 = _safe(2 * precision * recall, precision + recall)
            scored.append((f1, float(threshold)))
        best_f1 = max(score for score, _ in scored)
        tied = [threshold for score, threshold in scored if score == best_f1]
        thresholds.append(min(tied, key=lambda value: (abs(value - 0.5), value)))
    return tuple(thresholds)


def aggregate_macro_f1(metrics: Mapping[str, Mapping]) -> float:
    return float(np.mean([float(item["macro_f1"]) for item in metrics.values()]))
