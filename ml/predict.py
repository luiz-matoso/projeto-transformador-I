from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import torch
from PIL import Image, UnidentifiedImageError
from torch import Tensor

from ml.data.obstacles import TARGET_LABELS, build_image_transform
from ml.evaluate import DEFAULT_CHECKPOINT, load_trained_model
from ml.transitability import classify_transitability


@dataclass(frozen=True)
class LabelPrediction:
    label: str
    probability: float
    threshold: float
    detected: bool


def build_predictions(
    probabilities: Tensor | Sequence[float],
    thresholds: Sequence[float],
) -> tuple[LabelPrediction, ...]:
    """Associate probabilities and thresholds with TARGET_LABELS in order."""
    probability_values = tuple(float(value) for value in probabilities)
    threshold_values = tuple(float(value) for value in thresholds)

    expected_count = len(TARGET_LABELS)
    if len(probability_values) != expected_count:
        raise ValueError(
            f"Esperadas {expected_count} probabilidades, "
            f"mas foram recebidas {len(probability_values)}."
        )
    if len(threshold_values) != expected_count:
        raise ValueError(
            f"Esperados {expected_count} thresholds, "
            f"mas foram recebidos {len(threshold_values)}."
        )

    return tuple(
        LabelPrediction(
            label=label,
            probability=probability,
            threshold=threshold,
            detected=probability >= threshold,
        )
        for label, probability, threshold in zip(
            TARGET_LABELS,
            probability_values,
            threshold_values,
            strict=True,
        )
    )


def load_image_tensor(image_path: str | Path) -> Tensor:
    """Load one image with the deterministic transform used for test data."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Imagem não encontrada: {path}")

    try:
        with Image.open(path) as source_image:
            image = source_image.convert("RGB")
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError(f"Arquivo não é uma imagem válida: {path}") from error

    transform = build_image_transform(train=False, image_size=224)
    return transform(image)


def predict_image(
    image_path: str | Path,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT,
    device: torch.device | None = None,
) -> tuple[LabelPrediction, ...]:
    """Run multilabel inference for a single image."""
    checkpoint = Path(checkpoint_path)
    if not checkpoint.is_file():
        raise FileNotFoundError(f"Checkpoint não encontrado: {checkpoint}")

    inference_device = device or torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )
    model, thresholds = load_trained_model(checkpoint, inference_device)
    image_tensor = load_image_tensor(image_path).unsqueeze(0).to(inference_device)

    model.eval()
    with torch.no_grad():
        probabilities = torch.sigmoid(model(image_tensor)).squeeze(0).cpu()

    return build_predictions(probabilities, thresholds)


def print_predictions(
    image_path: str | Path,
    predictions: Sequence[LabelPrediction],
) -> None:
    print(f"Imagem: {Path(image_path).name}")
    print("\nResultados:")
    for prediction in predictions:
        status = "SIM" if prediction.detected else "NÃO"
        print(
            f"{prediction.label:<23} {prediction.probability:.2f}  "
            f"threshold={prediction.threshold:.2f}  {status}"
        )

    print("\nCaracterísticas detectadas:")
    detected = [prediction.label for prediction in predictions if prediction.detected]
    if detected:
        for label in detected:
            print(f"- {label}")
    else:
        print("- nenhuma")

    transitability = classify_transitability(detected)
    print(f"\nClassificação:\n{transitability.classification}")
    print(f"\nMotivo:\n{transitability.justification}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa inferência multilabel em uma imagem individual."
    )
    parser.add_argument("image", type=Path, help="Caminho da imagem")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT,
        help=f"Checkpoint a carregar (padrão: {DEFAULT_CHECKPOINT})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        predictions = predict_image(args.image, args.checkpoint)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1

    print_predictions(args.image, predictions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
