import argparse
import json
from pathlib import Path

import torch
from PIL import Image

from ml.dinov2 import CATEGORICAL_HEADS, MULTILABEL_HEADS
from ml.dinov2.dataset import emphasize_circulation_mask, emphasize_circulation_path
from ml.dinov2.model import DinoV2MultiTask
from ml.segmentation.dataset import parse_polygons


DEFAULT_CHECKPOINT = Path("artifacts/dinov2/v1/best_dinov2_multitask.pt")


def _load_polygon(value: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    candidate = Path(value)
    text = candidate.read_text(encoding="utf-8") if candidate.is_file() else value
    return parse_polygons(text)


def load_predictor(checkpoint_path: str | Path, device: str | None = None):
    from transformers import AutoImageProcessor

    path = Path(checkpoint_path)
    if not path.is_file():
        raise FileNotFoundError(f"Checkpoint não encontrado: {path}")
    selected = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    checkpoint = torch.load(path, map_location=selected, weights_only=True)
    required = {"heads_state_dict", "model_name", "classes", "multilabel_thresholds"}
    missing = required - set(checkpoint)
    if missing:
        raise ValueError("Checkpoint incompleto: " + ", ".join(sorted(missing)))
    classes = {head: tuple(values) for head, values in checkpoint["classes"].items()}
    model = DinoV2MultiTask(
        classes,
        model_name=checkpoint["model_name"],
        freeze_backbone=True,
    ).to(selected)
    model.heads.load_state_dict(checkpoint["heads_state_dict"])
    model.eval()
    processor_dir = path.parent / "image_processor"
    processor = AutoImageProcessor.from_pretrained(
        processor_dir if processor_dir.is_dir() else checkpoint["model_name"]
    )
    thresholds = {
        head: tuple(checkpoint["multilabel_thresholds"][head][label] for label in classes[head])
        for head in MULTILABEL_HEADS
    }
    return model, processor, classes, thresholds, selected


@torch.inference_mode()
def predict_image(model, processor, classes, thresholds, device, image: Image.Image) -> dict:
    pixels = processor(images=image, return_tensors="pt")["pixel_values"].to(device)
    with torch.autocast(
        device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"
    ):
        outputs = model(pixels)
    result: dict[str, dict] = {}
    for head in CATEGORICAL_HEADS:
        probabilities = torch.softmax(outputs[head], dim=1)[0].float().cpu()
        index = int(probabilities.argmax())
        result[head] = {
            "prediction": classes[head][index],
            "confidence": float(probabilities[index]),
            "probabilities": {
                label: float(value) for label, value in zip(classes[head], probabilities)
            },
        }
    for head in MULTILABEL_HEADS:
        probabilities = torch.sigmoid(outputs[head])[0].float().cpu()
        result[head] = {
            "predictions": [
                label
                for label, probability, threshold in zip(
                    classes[head], probabilities, thresholds[head]
                )
                if float(probability) >= threshold
            ],
            "probabilities": {
                label: float(value) for label, value in zip(classes[head], probabilities)
            },
            "thresholds": {
                label: float(value) for label, value in zip(classes[head], thresholds[head])
            },
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executa inferência DINOv2 com uma região de circulação."
    )
    parser.add_argument("--image", required=True, type=Path)
    region = parser.add_mutually_exclusive_group(required=True)
    region.add_argument("--mask", type=Path)
    region.add_argument("--polygon", help="JSON inline ou caminho de arquivo JSON")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--device", choices=("cpu", "cuda"), help="Padrão: CUDA quando disponível")
    args = parser.parse_args()
    try:
        with Image.open(args.image) as source:
            original = source.convert("RGB")
    except (FileNotFoundError, OSError) as error:
        raise SystemExit(f"Imagem inválida: {error}") from error
    try:
        if args.mask:
            with Image.open(args.mask) as source:
                focused = emphasize_circulation_mask(original, source.convert("L"))
        else:
            focused = emphasize_circulation_path(original, _load_polygon(args.polygon))
        model, processor, classes, thresholds, device = load_predictor(
            args.checkpoint, args.device
        )
        result = predict_image(model, processor, classes, thresholds, device, focused)
    except (FileNotFoundError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        raise SystemExit(f"Falha na inferência: {error}") from error
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
