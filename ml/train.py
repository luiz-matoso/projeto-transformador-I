"""Treinamento inicial da ResNet18 multilabel."""

from __future__ import annotations

import argparse
import math
from collections.abc import Sequence
from pathlib import Path

import torch
from torch import Tensor, nn
from torch.optim import AdamW
from torch.utils.data import DataLoader

from ml.data.obstacles import (
    DEFAULT_SPLIT_SEED,
    DEFAULT_VALIDATION_FRACTION,
    TARGET_LABELS,
    create_training_dataloaders,
)
from ml.model import create_model

DEFAULT_EPOCHS = 5
DEFAULT_CHECKPOINT = Path("best_model.pt")
THRESHOLD_CANDIDATES = (0.2, 0.3, 0.4, 0.5, 0.6)


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader[tuple[Tensor, Tensor]],
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> float:
    """Executa uma época e retorna a perda média por amostra."""

    model.train()
    total_loss = 0.0
    sample_count = 0

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        batch_size = images.shape[0]
        total_loss += loss.item() * batch_size
        sample_count += batch_size

    if sample_count == 0:
        raise ValueError("O DataLoader de treino está vazio")
    return total_loss / sample_count


def calculate_validation_loss(
    model: nn.Module,
    loader: DataLoader[tuple[Tensor, Tensor]],
    criterion: nn.Module,
    device: torch.device,
) -> float:
    """Calcula a perda média de validação sem atualizar o modelo."""

    model.eval()
    total_loss = 0.0
    sample_count = 0
    with torch.inference_mode():
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            loss = criterion(model(images), labels)

            batch_size = images.shape[0]
            total_loss += loss.item() * batch_size
            sample_count += batch_size

    if sample_count == 0:
        raise ValueError("O DataLoader de validação está vazio")
    return total_loss / sample_count


def collect_validation_outputs(
    model: nn.Module,
    loader: DataLoader[tuple[Tensor, Tensor]],
    device: torch.device,
) -> tuple[Tensor, Tensor]:
    """Coleta probabilidades e alvos exclusivamente no subset de validação."""

    probabilities: list[Tensor] = []
    targets: list[Tensor] = []
    model.eval()
    with torch.inference_mode():
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            probabilities.append(torch.sigmoid(model(images)).cpu())
            targets.append(labels.cpu())

    if not probabilities:
        raise ValueError("O DataLoader de validação está vazio")
    return torch.cat(probabilities), torch.cat(targets)


def select_label_thresholds(
    probabilities: Tensor,
    targets: Tensor,
    *,
    candidates: Sequence[float] = THRESHOLD_CANDIDATES,
) -> dict[str, float]:
    """Seleciona por label o threshold com maior F1 na validação."""

    expected_columns = len(TARGET_LABELS)
    if probabilities.ndim != 2 or probabilities.shape[1] != expected_columns:
        raise ValueError(
            f"Probabilidades devem ter shape [N, {expected_columns}], "
            f"recebido {tuple(probabilities.shape)}"
        )
    if targets.shape != probabilities.shape:
        raise ValueError(
            "Targets devem ter o mesmo shape das probabilidades: "
            f"{tuple(targets.shape)} != {tuple(probabilities.shape)}"
        )
    if not candidates:
        raise ValueError("Informe ao menos um threshold candidato")

    target_values = targets >= 0.5
    selected: dict[str, float] = {}
    for label_index, label in enumerate(TARGET_LABELS):
        label_targets = target_values[:, label_index]
        scored_candidates: list[tuple[float, float]] = []
        for threshold in candidates:
            predictions = probabilities[:, label_index] >= threshold
            true_positives = int((predictions & label_targets).sum().item())
            false_positives = int((predictions & ~label_targets).sum().item())
            false_negatives = int((~predictions & label_targets).sum().item())
            denominator = 2 * true_positives + false_positives + false_negatives
            f1 = 2 * true_positives / denominator if denominator else 0.0
            scored_candidates.append((float(threshold), f1))

        best_threshold, _ = max(
            scored_candidates,
            key=lambda item: (item[1], -abs(item[0] - 0.5), -item[0]),
        )
        selected[label] = best_threshold
    return selected


def calibrate_checkpoint_thresholds(
    checkpoint_path: str | Path,
    validation_loader: DataLoader[tuple[Tensor, Tensor]],
    device: torch.device,
) -> dict[str, float]:
    """Seleciona thresholds na validação e os adiciona ao checkpoint."""

    path = Path(checkpoint_path)
    checkpoint = torch.load(path, map_location=device, weights_only=True)
    checkpoint_labels = tuple(checkpoint.get("labels", ()))
    if checkpoint_labels != TARGET_LABELS:
        raise ValueError(
            "Ordem de labels incompatível no checkpoint. "
            f"Esperado {TARGET_LABELS}, recebido {checkpoint_labels}"
        )

    model = create_model(pretrained=False).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    probabilities, targets = collect_validation_outputs(
        model,
        validation_loader,
        device,
    )
    thresholds = select_label_thresholds(probabilities, targets)
    checkpoint["thresholds"] = thresholds
    checkpoint["threshold_candidates"] = THRESHOLD_CANDIDATES
    torch.save(checkpoint, path)
    return thresholds


def print_thresholds(thresholds: dict[str, float]) -> None:
    """Exibe thresholds na ordem oficial das labels."""

    print("Thresholds selecionados na validação:")
    for label in TARGET_LABELS:
        print(f"{label}: {thresholds[label]:.1f}")


def train_model(
    *,
    epochs: int = DEFAULT_EPOCHS,
    batch_size: int = 32,
    learning_rate: float = 1e-4,
    weight_decay: float = 1e-4,
    num_workers: int = 0,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT,
    train_csv: str | Path = "data/obstacles/train.csv",
    image_directory: str | Path = "data/obstacles/crops",
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    split_seed: int = DEFAULT_SPLIT_SEED,
) -> Path:
    """Treina por cinco épocas e salva o menor loss de validação."""

    if epochs <= 0:
        raise ValueError("epochs deve ser maior que zero")
    if learning_rate <= 0:
        raise ValueError("learning_rate deve ser maior que zero")
    if weight_decay < 0:
        raise ValueError("weight_decay não pode ser negativo")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    loaders = create_training_dataloaders(
        train_csv=train_csv,
        image_directory=image_directory,
        batch_size=batch_size,
        num_workers=num_workers,
        validation_fraction=validation_fraction,
        seed=split_seed,
    )
    model = create_model(pretrained=True).to(device)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay,
    )

    destination = Path(checkpoint_path)
    best_validation_loss = float("inf")
    best_epoch = 0
    print(f"Dispositivo: {device}")
    print(f"Labels: {', '.join(TARGET_LABELS)}")

    for epoch in range(1, epochs + 1):
        train_loss = train_one_epoch(
            model,
            loaders.train,
            criterion,
            optimizer,
            device,
        )
        validation_loss = calculate_validation_loss(
            model,
            loaders.validation,
            criterion,
            device,
        )
        if not math.isfinite(train_loss) or not math.isfinite(validation_loss):
            raise ValueError("O treinamento produziu uma perda não finita")

        print(f"Epoch {epoch}/{epochs}")
        print(f"Train Loss: {train_loss:.6f}")
        print(f"Validation Loss: {validation_loss:.6f}\n")

        if validation_loss < best_validation_loss:
            best_validation_loss = validation_loss
            best_epoch = epoch
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "labels": TARGET_LABELS,
                    "epoch": epoch,
                    "train_loss": train_loss,
                    "validation_loss": validation_loss,
                    "validation_fraction": validation_fraction,
                    "split_seed": split_seed,
                },
                destination,
            )

    print("Melhor checkpoint:")
    print(f"Epoch {best_epoch}")
    print(f"Validation Loss: {best_validation_loss:.6f}")
    print(f"Arquivo: {destination}")
    thresholds = calibrate_checkpoint_thresholds(
        destination,
        loaders.validation,
        device,
    )
    print_thresholds(thresholds)

    return destination


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Treina a ResNet18 multilabel.")
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--output", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument(
        "--select-thresholds-only",
        action="store_true",
        help="calibra thresholds no checkpoint atual sem retreinar",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.select_thresholds_only:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        loaders = create_training_dataloaders(
            batch_size=args.batch_size,
            num_workers=args.num_workers,
        )
        thresholds = calibrate_checkpoint_thresholds(
            args.output,
            loaders.validation,
            device,
        )
        print_thresholds(thresholds)
        return 0

    train_model(
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        num_workers=args.num_workers,
        checkpoint_path=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

