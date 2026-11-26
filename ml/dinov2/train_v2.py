import csv
import argparse
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

import torch
import numpy as np
from torch import nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

from ml.dinov2 import ALL_HEADS, CATEGORICAL_HEADS, MODEL_NAME, MULTILABEL_HEADS
from ml.dinov2.dataset import TransitabilityDinoDataset, load_dinov2_records
from ml.dinov2.metrics import aggregate_macro_f1, categorical_metrics, multilabel_metrics
from ml.dinov2.train import _move_batch, set_seed
from ml.dinov2.model import DinoV2MultiTask


FROZEN_SPLIT = Path("artifacts/dinov2/v1/splits.csv")
SPLIT_SIZES = {"train": 134, "validation": 29, "test": 29}
MULTILABEL_TARGETS = {
    "obstacle_type": ("pole", "sign", "tree", "vegetation", "construction", "litter_debris", "utility"),
    "surface_obstacle": ("cracks", "bumpy", "uneven_slanted", "height_difference", "very_broken", "grass", "sand_gravel"),
}
TRAINING_CONFIG = {
    "heads_lr": 1e-4, "backbone_lr": 1e-5,
    "heads_weight_decay": 0.01, "backbone_weight_decay": 0.05,
    "batch_size": 8, "max_epochs": 30, "early_stopping_patience": 5,
    "gradient_clip": 1.0, "amp": True, "seed": 42,
    "warmup_epochs": 2, "scheduler": "cosine", "dropout": 0.30,
    "label_smoothing": 0.05, "max_pos_weight": 8.0,
}


def select_targets(classes: Mapping[str, Sequence[str]], train_records: Sequence) -> tuple[dict, dict]:
    """Seleciona apenas labels multilabel com suporte mínimo no treino."""
    selected = {head: tuple(classes[head]) for head in CATEGORICAL_HEADS}
    excluded = {}
    for head in MULTILABEL_HEADS:
        expected = MULTILABEL_TARGETS[head]
        if not set(expected) <= set(classes[head]):
            raise ValueError(f"Schema incompatível com targets v2: {head}")
        counts = Counter(value for record in train_records for value in record.multilabel[head])
        if any(counts[label] < 10 for label in expected):
            raise ValueError(f"Suporte insuficiente no treino para targets v2: {head}")
        selected[head] = expected
        excluded[head] = {label: {"positive_train": counts[label], "reason": "insufficient_support"}
                          for label in classes[head] if label not in expected}
        if any(item["positive_train"] >= 10 for item in excluded[head].values()):
            raise ValueError(f"Targets v2 não refletem o suporte do treino: {head}")
    return selected, excluded


def compute_weights(records: Sequence, classes: Mapping[str, Sequence[str]]) -> tuple[dict, dict]:
    if not records:
        raise ValueError("Treino vazio")
    categorical, multilabel = {}, {}
    for head in CATEGORICAL_HEADS:
        counts = torch.tensor([sum(record.categorical[head] == label for record in records)
                               for label in classes[head]], dtype=torch.float32)
        if (counts == 0).any():
            raise ValueError(f"Classe sem exemplos no treino: {head}")
        categorical[head] = torch.sqrt(counts.sum() / (len(counts) * counts))
    for head in MULTILABEL_HEADS:
        positives = torch.tensor([sum(label in record.multilabel[head] for record in records)
                                  for label in classes[head]], dtype=torch.float32)
        if (positives == 0).any():
            raise ValueError(f"Label sem positivos no treino: {head}")
        multilabel[head] = torch.sqrt((len(records) - positives) / positives).clamp(max=8.0)
    return categorical, multilabel


def calculate_loss(outputs: Mapping, batch: Mapping, categorical_weights: Mapping, multilabel_weights: Mapping) -> tuple[torch.Tensor, dict]:
    losses = {}
    for head in CATEGORICAL_HEADS:
        mask = batch["categorical_masks"][head].bool()
        if mask.any():
            losses[head] = F.cross_entropy(outputs[head][mask], batch["categorical_targets"][head][mask],
                                           weight=categorical_weights[head].to(outputs[head].device), label_smoothing=0.05)
    for head in MULTILABEL_HEADS:
        losses[head] = F.binary_cross_entropy_with_logits(outputs[head], batch["multilabel_targets"][head],
                                                          pos_weight=multilabel_weights[head].to(outputs[head].device))
    return torch.stack(tuple(losses.values())).mean(), losses


def configure_backbone(model: DinoV2MultiTask, mode: str, *, warmup: bool = False) -> None:
    if mode not in {"frozen", "partial"}:
        raise ValueError(f"Modo inválido: {mode}")
    for parameter in model.backbone.parameters():
        parameter.requires_grad = False
    model.freeze_backbone = True
    if mode == "partial" and not warmup:
        blocks = model.backbone.encoder.layer
        if len(blocks) < 2:
            raise ValueError("O backbone precisa ter pelo menos dois blocos")
        for module in (*blocks[-2:], model.backbone.layernorm):
            for parameter in module.parameters():
                parameter.requires_grad = True
        model.freeze_backbone = False
    if model.freeze_backbone:
        model.backbone.eval()


def build_optimizer(model: DinoV2MultiTask, mode: str) -> torch.optim.AdamW:
    if mode not in {"frozen", "partial"}:
        raise ValueError(f"Modo inválido: {mode}")
    groups = [{"params": list(model.heads.parameters()), "lr": 1e-4, "weight_decay": 0.01}]
    if mode == "partial":
        blocks = model.backbone.encoder.layer
        if len(blocks) < 2:
            raise ValueError("O backbone precisa ter pelo menos dois blocos")
        params = [parameter for module in (*blocks[-2:], model.backbone.layernorm) for parameter in module.parameters()]
        groups.append({"params": params, "lr": 1e-5, "weight_decay": 0.05})
    return torch.optim.AdamW(groups)


def load_frozen_split(path: str | Path = FROZEN_SPLIT) -> dict[str, str]:
    """Carrega as atribuições v1 e rejeita duplicatas e tamanhos incorretos."""
    assignments = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"filename", "split"} <= set(reader.fieldnames):
            raise ValueError("CSV de split deve conter filename e split")
        for row in reader:
            filename, split = row["filename"].strip(), row["split"].strip()
            if not filename or split not in SPLIT_SIZES:
                raise ValueError("Filename vazio ou split inválido")
            if filename in assignments:
                raise ValueError(f"Imagem duplicada no split: {filename}")
            assignments[filename] = split
    if Counter(assignments.values()) != Counter(SPLIT_SIZES):
        raise ValueError(f"Tamanhos de split incorretos: {dict(Counter(assignments.values()))}")
    return assignments


def build_model(
    classes: Mapping[str, Sequence[str]],
    mode: str,
    *,
    backbone: nn.Module | None = None,
    model_name: str = MODEL_NAME,
) -> DinoV2MultiTask:
    if mode not in {"frozen", "partial"}:
        raise ValueError(f"Modo inválido: {mode}")
    model = DinoV2MultiTask(classes, backbone=backbone, model_name=model_name, freeze_backbone=True)
    model.heads = nn.ModuleDict({head: nn.Sequential(nn.Dropout(0.30), nn.Linear(model.embedding_size, len(values)))
                                 for head, values in model.classes.items()})
    configure_backbone(model, mode, warmup=mode == "partial")
    return model


def save_checkpoint(path: str | Path, model: DinoV2MultiTask, config: dict, epoch: int, best_validation_metric: float) -> None:
    if config.get("mode") not in {"frozen", "partial"}:
        raise ValueError("Configuração deve incluir mode frozen ou partial")
    torch.save({
        "format_version": 2,
        "model_name": model.model_name,
        "classes": {name: list(values) for name, values in model.classes.items()},
        "heads_state_dict": model.heads.state_dict(),
        "backbone_state_dict": model.backbone.state_dict(),
        "config": {**config, "backbone_warmup": model.freeze_backbone},
        "epoch": epoch,
        "best_validation_metric": best_validation_metric,
    }, Path(path))


def load_checkpoint(path: str | Path, *, device: str | torch.device = "cpu", backbone: nn.Module | None = None) -> tuple[DinoV2MultiTask, dict]:
    checkpoint = torch.load(Path(path), map_location=device, weights_only=True)
    if checkpoint.get("format_version") != 2:
        raise ValueError("Checkpoint não é da infraestrutura DINOv2 v2")
    model = build_model(checkpoint["classes"], checkpoint["config"]["mode"], backbone=backbone, model_name=checkpoint["model_name"])
    model.backbone.load_state_dict(checkpoint["backbone_state_dict"])
    model.heads.load_state_dict(checkpoint["heads_state_dict"])
    configure_backbone(model, checkpoint["config"]["mode"], warmup=checkpoint["config"].get("backbone_warmup", False))
    return model.to(device), checkpoint


def run_epoch(model, loader, device, categorical_weights, multilabel_weights, optimizer=None, scaler=None):
    training = optimizer is not None
    model.train(training)
    totals = Counter()
    denominators = Counter()
    raw = {"categorical_targets": {h: [] for h in CATEGORICAL_HEADS},
           "categorical_predictions": {h: [] for h in CATEGORICAL_HEADS},
           "multilabel_targets": {h: [] for h in MULTILABEL_HEADS},
           "multilabel_probabilities": {h: [] for h in MULTILABEL_HEADS}}
    with torch.set_grad_enabled(training):
        for source in loader:
            batch = _move_batch(source, device)
            if training:
                optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
                outputs = model(batch["pixel_values"])
                loss, individual = calculate_loss(outputs, batch, categorical_weights, multilabel_weights)
            if training:
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], TRAINING_CONFIG["gradient_clip"])
                scaler.step(optimizer)
                scaler.update()
            size = batch["pixel_values"].size(0)
            totals["loss"] += float(loss.detach()) * size
            denominators["loss"] += size
            for head, value in individual.items():
                count = int(batch["categorical_masks"][head].sum()) if head in CATEGORICAL_HEADS else size
                totals[head] += float(value.detach()) * count
                denominators[head] += count
            if not training:
                for head in CATEGORICAL_HEADS:
                    mask = batch["categorical_masks"][head].bool()
                    raw["categorical_targets"][head].extend(batch["categorical_targets"][head][mask].cpu().tolist())
                    raw["categorical_predictions"][head].extend(outputs[head][mask].argmax(dim=1).cpu().tolist())
                for head in MULTILABEL_HEADS:
                    raw["multilabel_targets"][head].extend(batch["multilabel_targets"][head].cpu().tolist())
                    raw["multilabel_probabilities"][head].extend(torch.sigmoid(outputs[head]).float().cpu().tolist())
    losses = {key: totals[key] / denominators[key] for key in totals}
    return losses, raw


def score_outputs(raw, classes):
    metrics = {}
    for head in CATEGORICAL_HEADS:
        metrics[head] = categorical_metrics(np.asarray(raw["categorical_targets"][head]), np.asarray(raw["categorical_predictions"][head]), classes[head])
    for head in MULTILABEL_HEADS:
        metrics[head] = multilabel_metrics(np.asarray(raw["multilabel_targets"][head]), np.asarray(raw["multilabel_probabilities"][head]), classes[head], [0.5] * len(classes[head]))
    return {"aggregate_macro_f1": aggregate_macro_f1(metrics), "heads": metrics, "threshold": 0.5}


def v1_common_metrics(classes, predictions_path=Path("artifacts/dinov2/v1/test_predictions.csv")):
    with predictions_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    metrics = {}
    for head in CATEGORICAL_HEADS:
        valid = [row for row in rows if row[f"{head}_ground_truth"] != "<unknown-masked>"]
        targets = np.asarray([classes[head].index(row[f"{head}_ground_truth"]) for row in valid])
        predictions = np.asarray([classes[head].index(row[f"{head}_prediction"]) for row in valid])
        metrics[head] = categorical_metrics(targets, predictions, classes[head])
    for head in MULTILABEL_HEADS:
        targets = np.asarray([[int(label in json.loads(row[f"{head}_ground_truth"])) for label in classes[head]] for row in rows])
        probabilities = np.asarray([[json.loads(row[f"{head}_confidence"])[label] for label in classes[head]] for row in rows])
        metrics[head] = multilabel_metrics(targets, probabilities, classes[head], [0.5] * len(classes[head]))
    return {"aggregate_macro_f1": aggregate_macro_f1(metrics), "heads": metrics, "threshold": 0.5}


def main():
    from transformers import AutoImageProcessor

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("frozen", "partial"), default="frozen")
    mode = parser.parse_args().mode
    if not torch.cuda.is_available():
        raise SystemExit("CUDA é necessária para este experimento")
    output = Path("artifacts/dinov2/v2") / mode
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Diretório de resultados não está vazio: {output}")
    records, all_classes, statuses = load_dinov2_records("annotations/transitability_annotations.csv", "data/annotation-pilot", "annotations/annotation-schema.yaml")
    assignments = load_frozen_split()
    if set(assignments) != {record.filename for record in records}:
        raise ValueError("Registros não correspondem ao split congelado")
    panoramas = {}
    for record in records:
        split = assignments[record.filename]
        if record.panorama_id in panoramas and panoramas[record.panorama_id] != split:
            raise ValueError(f"Panorama em splits distintos: {record.panorama_id}")
        panoramas[record.panorama_id] = split
    splits = {split: [r for r in records if assignments[r.filename] == split] for split in SPLIT_SIZES}
    classes, excluded = select_targets(all_classes, splits["train"])
    categorical_weights, multilabel_weights = compute_weights(splits["train"], classes)
    set_seed(TRAINING_CONFIG["seed"])
    processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    datasets = {name: TransitabilityDinoDataset(items, classes, processor, augment=name == "train") for name, items in splits.items()}
    loaders = {name: DataLoader(dataset, batch_size=8, shuffle=name == "train", num_workers=0, pin_memory=True) for name, dataset in datasets.items()}
    device = torch.device("cuda")
    model = build_model(classes, mode).to(device)
    optimizer = build_optimizer(model, mode)
    scaler = torch.amp.GradScaler("cuda")
    def lr_factor(epoch):
        if epoch < 2:
            return (epoch + 1) / 2
        return 0.5 * (1 + math.cos(math.pi * (epoch - 2) / 28))
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lr_factor)
    output.mkdir(parents=True, exist_ok=False)
    processor.save_pretrained(output / "image_processor")
    config = {**TRAINING_CONFIG, "mode": mode, "model_name": MODEL_NAME,
              "split": str(FROZEN_SPLIT), "selection_metric": "validation aggregate macro F1 at 0.5",
              "classes": classes, "excluded_targets": excluded, "statuses": dict(statuses),
              "categorical_weights": {h: v.tolist() for h, v in categorical_weights.items()},
              "multilabel_weights": {h: v.tolist() for h, v in multilabel_weights.items()},
              "warmup_schedule": "epoch 1: 0.5 LR; epoch 2: 1.0 LR; cosine thereafter"}
    (output / "training_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    history, best, patience = [], -1.0, 0
    checkpoint_path = output / "best_dinov2_v2.pt"
    for epoch in range(1, 31):
        if mode == "partial":
            configure_backbone(model, mode, warmup=epoch <= TRAINING_CONFIG["warmup_epochs"])
        train_losses, _ = run_epoch(model, loaders["train"], device, categorical_weights, multilabel_weights, optimizer, scaler)
        val_losses, val_raw = run_epoch(model, loaders["validation"], device, categorical_weights, multilabel_weights)
        val = score_outputs(val_raw, classes)
        row = {"epoch": epoch, "learning_rate": optimizer.param_groups[0]["lr"], "train_loss": train_losses["loss"], "validation_loss": val_losses["loss"], "validation_macro_f1": val["aggregate_macro_f1"]}
        row["backbone_trainable"] = not model.freeze_backbone
        row["backbone_lr"] = optimizer.param_groups[1]["lr"] if mode == "partial" else 0.0
        for head in ALL_HEADS:
            row[f"train_{head}_loss"] = train_losses.get(head, 0.0)
            row[f"validation_{head}_loss"] = val_losses.get(head, 0.0)
            row[f"validation_{head}_macro_f1"] = val["heads"][head]["macro_f1"]
        history.append(row)
        with (output / "training_history.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=row.keys()); writer.writeheader(); writer.writerows(history)
        print(f"Epoch {epoch}: train={train_losses['loss']:.4f} val={val_losses['loss']:.4f} macro_f1={val['aggregate_macro_f1']:.4f}", flush=True)
        if val["aggregate_macro_f1"] > best:
            best, patience = val["aggregate_macro_f1"], 0
            save_checkpoint(checkpoint_path, model, config, epoch, best)
        else:
            patience += 1
        scheduler.step()
        if patience >= 5:
            break
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.backbone.load_state_dict(checkpoint["backbone_state_dict"])
    model.heads.load_state_dict(checkpoint["heads_state_dict"])
    val_losses, val_raw = run_epoch(model, loaders["validation"], device, categorical_weights, multilabel_weights)
    validation = score_outputs(val_raw, classes); validation["losses"] = val_losses
    test_losses, test_raw = run_epoch(model, loaders["test"], device, categorical_weights, multilabel_weights)
    test = score_outputs(test_raw, classes); test["losses"] = test_losses
    baseline = v1_common_metrics(classes)
    comparison = {"v1_common": baseline, f"v2_{mode}": test,
                  "aggregate_delta": test["aggregate_macro_f1"] - baseline["aggregate_macro_f1"],
                  "head_deltas": {head: test["heads"][head]["macro_f1"] - baseline["heads"][head]["macro_f1"] for head in ALL_HEADS}}
    if mode == "partial":
        frozen = json.loads(Path("artifacts/dinov2/v2/frozen/test_metrics.json").read_text(encoding="utf-8"))
        comparison["v2_frozen"] = frozen
        comparison["frozen_to_partial_delta"] = test["aggregate_macro_f1"] - frozen["aggregate_macro_f1"]
    for name, payload in (("validation_metrics.json", validation), ("test_metrics.json", test), ("comparison_v1_common.json", comparison), ("targets.json", {"modeled": classes, "not_modeled": excluded})):
        (output / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Melhor época: {checkpoint['epoch']}; test macro F1: {test['aggregate_macro_f1']:.4f}", flush=True)


if __name__ == "__main__":
    main()
