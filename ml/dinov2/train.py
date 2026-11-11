import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from ml.dinov2 import ALL_HEADS, CATEGORICAL_HEADS, MODEL_NAME, MULTILABEL_HEADS
from ml.dinov2.dataset import (
    DinoRecord,
    TransitabilityDinoDataset,
    create_grouped_multitask_split,
    load_dinov2_records,
    write_splits,
)
from ml.dinov2.losses import compute_train_weights, multitask_loss
from ml.dinov2.metrics import (
    aggregate_macro_f1,
    categorical_metrics,
    multilabel_metrics,
    select_multilabel_thresholds,
)
from ml.dinov2.model import DinoV2MultiTask


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def split_records(
    records: list[DinoRecord], assignments: dict[str, str]
) -> dict[str, list[DinoRecord]]:
    return {
        split: [record for record in records if assignments[record.filename] == split]
        for split in ("train", "validation", "test")
    }


def _categorical_counts(records: list[DinoRecord], head: str) -> tuple[Counter[str], int]:
    counts = Counter(
        record.categorical[head]
        for record in records
        if record.categorical[head] is not None
    )
    unknown = sum(record.categorical[head] is None for record in records)
    return counts, unknown


def _multilabel_counts(records: list[DinoRecord], head: str) -> Counter[str]:
    return Counter(value for record in records for value in record.multilabel[head])


def write_dataset_analysis(
    path: Path,
    records: list[DinoRecord],
    classes: dict[str, tuple[str, ...]],
    statuses: Counter[str],
    assignments: dict[str, str],
) -> None:
    splits = split_records(records, assignments)
    lines = [
        "# Análise do dataset DINOv2 v1",
        "",
        f"- Anotações totais: **{sum(statuses.values())}**",
        f"- Utilizáveis (`circulation_path_status=annotated`): **{len(records)}**",
        f"- Excluídas por `circulation_path_status`: **{sum(statuses.values()) - len(records)}**",
        f"- Split: **{len(splits['train'])} train / {len(splits['validation'])} validation / {len(splits['test'])} test**",
        "- Unidade de isolamento: **panorama**",
        "- Classes com menos de 10 exemplos são marcadas como raras; menos de 5, como insuficientes para avaliação sólida.",
        "",
    ]
    for head in CATEGORICAL_HEADS:
        counts, unknown = _categorical_counts(records, head)
        lines.extend(
            [
                f"## `{head}` (categórica)",
                "",
                f"Unknown mascarado na loss: **{unknown}**",
                "",
                "| Classe | Total | Train | Validation | Test | Situação |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for label in classes[head]:
            split_counts = [
                sum(record.categorical[head] == label for record in splits[split])
                for split in ("train", "validation", "test")
            ]
            total = counts[label]
            situation = "insuficiente" if total < 5 else "rara" if total < 10 else "ok"
            lines.append(
                f"| {label} | {total} | {split_counts[0]} | {split_counts[1]} | {split_counts[2]} | {situation} |"
            )
        lines.append("")
    for head in MULTILABEL_HEADS:
        counts = _multilabel_counts(records, head)
        empty_count = sum(not record.multilabel[head] for record in records)
        lines.extend(
            [
                f"## `{head}` (multilabel)",
                "",
                f"Listas vazias (nenhuma classe positiva): **{empty_count}**",
                "",
                "| Label | Total | Train | Validation | Test | Situação |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for label in classes[head]:
            split_counts = [
                sum(label in record.multilabel[head] for record in splits[split])
                for split in ("train", "validation", "test")
            ]
            total = counts[label]
            situation = "insuficiente" if total < 5 else "rara" if total < 10 else "ok"
            lines.append(
                f"| {label} | {total} | {split_counts[0]} | {split_counts[1]} | {split_counts[2]} | {situation} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Limitações do split",
            "",
            "A estratificação é aproximada e considera simultaneamente categorias, multilabels e subset, sem quebrar panoramas. Classes com 1–2 exemplos não podem aparecer de forma representativa nos três splits; métricas dessas classes devem ser interpretadas apenas como evidência exploratória.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _move_batch(batch: dict, device: torch.device) -> dict:
    return {
        "pixel_values": batch["pixel_values"].to(device, non_blocking=True),
        "categorical_targets": {
            key: value.to(device, non_blocking=True)
            for key, value in batch["categorical_targets"].items()
        },
        "categorical_masks": {
            key: value.to(device, non_blocking=True)
            for key, value in batch["categorical_masks"].items()
        },
        "multilabel_targets": {
            key: value.to(device, non_blocking=True)
            for key, value in batch["multilabel_targets"].items()
        },
        "filename": batch["filename"],
    }


def train_epoch(
    model,
    loader,
    optimizer,
    scaler,
    device,
    categorical_weights,
    multilabel_weights,
) -> float:
    model.train()
    total = 0.0
    for raw_batch in loader:
        batch = _move_batch(raw_batch, device)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            outputs = model(batch["pixel_values"])
            loss, _ = multitask_loss(
                outputs,
                batch,
                categorical_weights=categorical_weights,
                multilabel_pos_weights=multilabel_weights,
            )
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        total += float(loss.detach()) * batch["pixel_values"].size(0)
    return total / len(loader.dataset)


@torch.no_grad()
def evaluate_model(
    model,
    loader,
    device,
    classes,
    categorical_weights,
    multilabel_weights,
    thresholds: dict[str, tuple[float, ...]] | None = None,
) -> tuple[float, dict[str, dict], dict[str, Any]]:
    model.eval()
    loss_total = 0.0
    raw: dict[str, Any] = {
        "filenames": [],
        "categorical_targets": {head: [] for head in CATEGORICAL_HEADS},
        "categorical_probabilities": {head: [] for head in CATEGORICAL_HEADS},
        "multilabel_targets": {head: [] for head in MULTILABEL_HEADS},
        "multilabel_probabilities": {head: [] for head in MULTILABEL_HEADS},
    }
    for raw_batch in loader:
        batch = _move_batch(raw_batch, device)
        with torch.autocast(device_type="cuda", dtype=torch.float16):
            outputs = model(batch["pixel_values"])
            loss, _ = multitask_loss(
                outputs,
                batch,
                categorical_weights=categorical_weights,
                multilabel_pos_weights=multilabel_weights,
            )
        loss_total += float(loss) * batch["pixel_values"].size(0)
        raw["filenames"].extend(batch["filename"])
        for head in CATEGORICAL_HEADS:
            mask = batch["categorical_masks"][head].bool()
            raw["categorical_targets"][head].extend(
                batch["categorical_targets"][head][mask].cpu().tolist()
            )
            raw["categorical_probabilities"][head].extend(
                torch.softmax(outputs[head][mask], dim=1).float().cpu().tolist()
            )
        for head in MULTILABEL_HEADS:
            raw["multilabel_targets"][head].extend(
                batch["multilabel_targets"][head].cpu().tolist()
            )
            raw["multilabel_probabilities"][head].extend(
                torch.sigmoid(outputs[head]).float().cpu().tolist()
            )
    metrics: dict[str, dict] = {}
    for head in CATEGORICAL_HEADS:
        targets = np.asarray(raw["categorical_targets"][head], dtype=np.int64)
        probabilities = np.asarray(raw["categorical_probabilities"][head], dtype=np.float64)
        metrics[head] = categorical_metrics(
            targets, probabilities.argmax(axis=1), classes[head]
        )
    for head in MULTILABEL_HEADS:
        targets = np.asarray(raw["multilabel_targets"][head], dtype=np.float64)
        probabilities = np.asarray(raw["multilabel_probabilities"][head], dtype=np.float64)
        selected = thresholds[head] if thresholds else (0.5,) * len(classes[head])
        metrics[head] = multilabel_metrics(
            targets, probabilities, classes[head], selected
        )
    return loss_total / len(loader.dataset), metrics, raw


def _write_history(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = (
        "epoch",
        "train_loss",
        "validation_loss",
        "validation_macro_f1",
        *(f"{head}_macro_f1" for head in ALL_HEADS),
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_per_head_metrics(path: Path, metrics: dict[str, dict]) -> None:
    fields = (
        "head",
        "type",
        "class",
        "support",
        "precision",
        "recall",
        "f1",
        "threshold",
        "macro_f1",
        "weighted_f1",
        "micro_f1",
        "accuracy",
    )
    rows: list[dict[str, Any]] = []
    for head in CATEGORICAL_HEADS:
        item = metrics[head]
        for label, values in item["per_class"].items():
            rows.append(
                {
                    "head": head,
                    "type": "categorical",
                    "class": label,
                    **values,
                    "threshold": "",
                    "macro_f1": item["macro_f1"],
                    "weighted_f1": item["weighted_f1"],
                    "micro_f1": "",
                    "accuracy": item["accuracy"],
                }
            )
    for head in MULTILABEL_HEADS:
        item = metrics[head]
        for label, values in item["per_label"].items():
            rows.append(
                {
                    "head": head,
                    "type": "multilabel",
                    "class": label,
                    **values,
                    "macro_f1": item["macro_f1"],
                    "weighted_f1": "",
                    "micro_f1": item["micro_f1"],
                    "accuracy": "",
                }
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_predictions(
    path: Path,
    raw: dict[str, Any],
    classes: dict[str, tuple[str, ...]],
    thresholds: dict[str, tuple[float, ...]],
) -> None:
    fields = ["filename"]
    for head in ALL_HEADS:
        fields.extend((f"{head}_ground_truth", f"{head}_prediction", f"{head}_confidence"))
    rows = [{"filename": filename} for filename in raw["filenames"]]
    # Categóricas possuem máscara de unknown, portanto reconstruímos pelo dataset
    # na mesma ordem usando um cursor apenas sobre amostras válidas.
    for head in CATEGORICAL_HEADS:
        cursor = 0
        expected_predictions = len(raw["categorical_targets"][head])
        # O test usado nesta versão pode conter unknown; marcação explícita evita
        # fabricar ground truth. A ordem válida é preenchida pelo mapa auxiliar.
        for row in rows:
            row[f"{head}_ground_truth"] = "<unknown-masked>"
            row[f"{head}_prediction"] = "<not-scored>"
            row[f"{head}_confidence"] = ""
        valid_by_filename = raw.get("categorical_by_filename", {}).get(head, {})
        for row in rows:
            if row["filename"] not in valid_by_filename:
                continue
            target, probs = valid_by_filename[row["filename"]]
            prediction = int(np.argmax(probs))
            row[f"{head}_ground_truth"] = classes[head][target]
            row[f"{head}_prediction"] = classes[head][prediction]
            row[f"{head}_confidence"] = f"{float(probs[prediction]):.8f}"
            cursor += 1
        if cursor != expected_predictions:
            raise RuntimeError(f"Falha ao alinhar predições categóricas de {head}")
    for head in MULTILABEL_HEADS:
        for index, row in enumerate(rows):
            target = np.asarray(raw["multilabel_targets"][head][index])
            probs = np.asarray(raw["multilabel_probabilities"][head][index])
            selected = probs >= np.asarray(thresholds[head])
            row[f"{head}_ground_truth"] = json.dumps(
                [label for label, value in zip(classes[head], target) if value],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            row[f"{head}_prediction"] = json.dumps(
                [label for label, value in zip(classes[head], selected) if value],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            row[f"{head}_confidence"] = json.dumps(
                {label: round(float(value), 8) for label, value in zip(classes[head], probs)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_error_analysis(
    path: Path,
    metrics: dict[str, dict],
    classes: dict[str, tuple[str, ...]],
    records: list[DinoRecord],
    history: list[dict[str, Any]],
    best_epoch: int,
) -> None:
    ranked = sorted(
        ((head, float(metrics[head]["macro_f1"])) for head in ALL_HEADS),
        key=lambda item: item[1],
        reverse=True,
    )
    rare: list[str] = []
    for head in CATEGORICAL_HEADS:
        counts, _ = _categorical_counts(records, head)
        rare.extend(f"{head}/{label} ({counts[label]})" for label in classes[head] if counts[label] < 5)
    for head in MULTILABEL_HEADS:
        counts = _multilabel_counts(records, head)
        rare.extend(f"{head}/{label} ({counts[label]})" for label in classes[head] if counts[label] < 5)
    best_row = next(row for row in history if row["epoch"] == best_epoch)
    final = history[-1]
    overfit = (
        float(final["train_loss"]) < float(best_row["train_loss"])
        and float(final["validation_macro_f1"]) < float(best_row["validation_macro_f1"])
    )
    confusions: list[str] = []
    for head in CATEGORICAL_HEADS:
        matrix = np.asarray(metrics[head]["confusion_matrix"])
        off_diagonal = matrix.copy()
        np.fill_diagonal(off_diagonal, 0)
        if off_diagonal.max() == 0:
            confusions.append(f"`{head}`: nenhuma confusão observada no test")
            continue
        target_index, predicted_index = np.unravel_index(
            int(off_diagonal.argmax()), off_diagonal.shape
        )
        confusions.append(
            f"`{head}`: `{classes[head][target_index]}` → `{classes[head][predicted_index]}` "
            f"({int(off_diagonal[target_index, predicted_index])} caso(s))"
        )
    lines = [
        "# Análise de erros DINOv2 v1",
        "",
        "## Desempenho por head no test",
        "",
        *[f"- `{head}`: macro F1 **{score:.4f}**" for head, score in ranked],
        "",
        f"- Heads relativamente mais fortes: {', '.join(f'`{head}`' for head, _ in ranked[:2])}.",
        f"- Heads relativamente mais fracas: {', '.join(f'`{head}`' for head, _ in ranked[-2:])}.",
        "",
        "## Confusões categóricas mais frequentes",
        "",
        *(f"- {item}" for item in confusions),
        "",
        "## Classes sem amostras suficientes",
        "",
        *(f"- {item}" for item in rare),
        "",
        "## Overfitting",
        "",
        (
            f"- Há sinal após a época {best_epoch}: train loss continuou caindo enquanto a métrica agregada de validação terminou menor."
            if overfit
            else "- O histórico não mostrou o padrão simples de train loss menor acompanhado por queda da métrica agregada após o melhor checkpoint."
        ),
        "",
        "## Limitação principal",
        "",
        "Com apenas 192 imagens utilizáveis e classes multilabel com 1–2 positivos, confusões e F1 zero podem refletir falta de suporte, não somente incapacidade visual do backbone.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def prepare_dataset(args) -> tuple[list[DinoRecord], dict, dict]:
    records, classes, statuses = load_dinov2_records(
        args.annotations, args.pilot_root, args.schema
    )
    assignments = create_grouped_multitask_split(records, args.seed)
    splits = split_records(records, assignments)
    args.output.mkdir(parents=True, exist_ok=True)
    write_splits(args.output / "splits.csv", records, assignments)
    write_dataset_analysis(
        args.output / "dataset_analysis.md", records, classes, statuses, assignments
    )
    return records, classes, splits


def main() -> int:
    from transformers import AutoImageProcessor

    parser = argparse.ArgumentParser(
        description="Treina o baseline DINOv2 multitarefa."
    )
    parser.add_argument("--annotations", type=Path, default=Path("annotations/transitability_annotations.csv"))
    parser.add_argument("--pilot-root", type=Path, default=Path("data/annotation-pilot"))
    parser.add_argument("--schema", type=Path, default=Path("annotations/annotation-schema.yaml"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/dinov2/v1"))
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    records, classes, splits = prepare_dataset(args)
    print(
        f"Dataset: {len(records)} utilizáveis | train={len(splits['train'])} "
        f"validation={len(splits['validation'])} test={len(splits['test'])}",
        flush=True,
    )
    if args.prepare_only:
        return 0
    if not torch.cuda.is_available():
        raise SystemExit("CUDA é obrigatória para treinar este baseline")
    set_seed(args.seed)
    processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    processor.save_pretrained(args.output / "image_processor")
    datasets = {
        split: TransitabilityDinoDataset(
            split_records_list,
            classes,
            processor,
            augment=split == "train",
        )
        for split, split_records_list in splits.items()
    }
    loaders = {
        split: DataLoader(
            dataset,
            batch_size=args.batch_size,
            shuffle=split == "train",
            num_workers=0,
            pin_memory=True,
        )
        for split, dataset in datasets.items()
    }
    device = torch.device("cuda")
    model = DinoV2MultiTask(classes, freeze_backbone=True).to(device)
    categorical_weights, multilabel_weights = compute_train_weights(
        splits["train"], classes
    )
    optimizer = torch.optim.AdamW(
        model.heads.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    scaler = torch.amp.GradScaler("cuda")
    config = {
        "model_name": MODEL_NAME,
        "embedding_size": model.embedding_size,
        "backbone_frozen": True,
        "representation": "CLS token",
        "classes": {head: list(values) for head, values in classes.items()},
        "preprocessing": {
            "inside_region": "100% original",
            "outside_brightness": 0.45,
            "outside_saturation": 0.20,
            "outside_gaussian_blur_radius": 1.2,
            "processor": MODEL_NAME,
        },
        "loss": "mean of per-head CE/BCE losses",
        "categorical_class_weights_from_train": {
            head: weights.tolist() for head, weights in categorical_weights.items()
        },
        "multilabel_pos_weights_from_train_capped_at_20": {
            head: weights.tolist() for head, weights in multilabel_weights.items()
        },
        "hyperparameters": {
            "epochs": args.epochs,
            "patience": args.patience,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "weight_decay": args.weight_decay,
            "optimizer": "AdamW",
            "amp": True,
            "seed": args.seed,
        },
    }
    (args.output / "training_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    history: list[dict[str, Any]] = []
    best_metric = -1.0
    best_loss = float("inf")
    without_improvement = 0
    checkpoint_path = args.output / "best_dinov2_multitask.pt"
    for epoch in range(1, args.epochs + 1):
        train_loss = train_epoch(
            model,
            loaders["train"],
            optimizer,
            scaler,
            device,
            categorical_weights,
            multilabel_weights,
        )
        validation_loss, validation_metrics, _ = evaluate_model(
            model,
            loaders["validation"],
            device,
            classes,
            categorical_weights,
            multilabel_weights,
        )
        aggregate = aggregate_macro_f1(validation_metrics)
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "validation_loss": validation_loss,
            "validation_macro_f1": aggregate,
            **{
                f"{head}_macro_f1": validation_metrics[head]["macro_f1"]
                for head in ALL_HEADS
            },
        }
        history.append(row)
        _write_history(args.output / "training_history.csv", history)
        print(
            f"Epoch {epoch}/{args.epochs} | train_loss={train_loss:.5f} | "
            f"val_loss={validation_loss:.5f} | val_macro_f1={aggregate:.4f}",
            flush=True,
        )
        improved = aggregate > best_metric or (
            aggregate == best_metric and validation_loss < best_loss
        )
        if improved:
            best_metric = aggregate
            best_loss = validation_loss
            without_improvement = 0
            torch.save(
                {
                    "heads_state_dict": model.heads.state_dict(),
                    "model_name": MODEL_NAME,
                    "classes": config["classes"],
                    "embedding_size": model.embedding_size,
                    "backbone_frozen": True,
                    "epoch": epoch,
                    "validation_macro_f1": aggregate,
                    "validation_metrics_fixed_0_5": validation_metrics,
                    "hyperparameters": config["hyperparameters"],
                    "preprocessing": config["preprocessing"],
                },
                checkpoint_path,
            )
        else:
            without_improvement += 1
            if without_improvement >= args.patience:
                print(f"Early stopping após {epoch} épocas.", flush=True)
                break

    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.heads.load_state_dict(checkpoint["heads_state_dict"])
    _, _, validation_raw = evaluate_model(
        model,
        loaders["validation"],
        device,
        classes,
        categorical_weights,
        multilabel_weights,
    )
    thresholds: dict[str, tuple[float, ...]] = {}
    for head in MULTILABEL_HEADS:
        thresholds[head] = select_multilabel_thresholds(
            np.asarray(validation_raw["multilabel_targets"][head]),
            np.asarray(validation_raw["multilabel_probabilities"][head]),
        )
    checkpoint["multilabel_thresholds"] = {
        head: {label: value for label, value in zip(classes[head], thresholds[head])}
        for head in MULTILABEL_HEADS
    }
    torch.save(checkpoint, checkpoint_path)

    # O test é tocado pela primeira vez somente após checkpoint e thresholds congelados.
    test_loss, test_metrics, test_raw = evaluate_model(
        model,
        loaders["test"],
        device,
        classes,
        categorical_weights,
        multilabel_weights,
        thresholds,
    )
    test_metrics_payload = {
        "aggregate_macro_f1": aggregate_macro_f1(test_metrics),
        "loss": test_loss,
        "heads": test_metrics,
        "threshold_source": "validation only",
    }
    (args.output / "test_metrics.json").write_text(
        json.dumps(test_metrics_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_per_head_metrics(args.output / "per_head_metrics.csv", test_metrics)
    test_raw["categorical_by_filename"] = {head: {} for head in CATEGORICAL_HEADS}
    for head in CATEGORICAL_HEADS:
        position = 0
        for record in splits["test"]:
            value = record.categorical[head]
            if value is None:
                continue
            test_raw["categorical_by_filename"][head][record.filename] = (
                classes[head].index(value),
                test_raw["categorical_probabilities"][head][position],
            )
            position += 1
    _write_predictions(
        args.output / "test_predictions.csv", test_raw, classes, thresholds
    )
    _write_error_analysis(
        args.output / "error_analysis.md",
        test_metrics,
        classes,
        records,
        history,
        int(checkpoint["epoch"]),
    )
    print(
        f"Best epoch={checkpoint['epoch']} | val_macro_f1={checkpoint['validation_macro_f1']:.4f} | "
        f"test_macro_f1={test_metrics_payload['aggregate_macro_f1']:.4f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
