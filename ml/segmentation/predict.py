"""Inferência reutilizável de ``circulation_path`` com o SegFormer v1."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from ml.segmentation import ID2LABEL, LABEL2ID


DEFAULT_CHECKPOINT = Path("artifacts/segmentation/best_segformer.pt")
FOREGROUND_THRESHOLD = 0.5


@dataclass(frozen=True)
class SegformerPredictor:
    model: Any
    processor: Any
    device: torch.device
    image_size: int
    checkpoint_path: Path


@dataclass(frozen=True)
class SegmentationSuggestion:
    polygons: tuple[tuple[tuple[float, float], ...], ...]
    mask: np.ndarray
    confidence: float
    inference_seconds: float


def read_segformer_checkpoint(
    checkpoint_path: str | Path,
    *,
    map_location: str | torch.device = "cpu",
) -> dict[str, Any]:
    """Carrega e valida os metadados necessários do checkpoint v1."""

    path = Path(checkpoint_path)
    if not path.is_file():
        raise FileNotFoundError(f"Checkpoint não encontrado: {path}")
    checkpoint = torch.load(path, map_location=map_location, weights_only=True)
    required = {"state_dict", "model_name", "id2label", "label2id", "image_size"}
    missing = required - set(checkpoint)
    if missing:
        raise ValueError(
            "Checkpoint SegFormer incompleto; ausente(s): " + ", ".join(sorted(missing))
        )
    checkpoint_id2label = {
        int(key): str(value) for key, value in checkpoint["id2label"].items()
    }
    checkpoint_label2id = {
        str(key): int(value) for key, value in checkpoint["label2id"].items()
    }
    if checkpoint_id2label != ID2LABEL or checkpoint_label2id != LABEL2ID:
        raise ValueError("Labels do checkpoint são incompatíveis com o pipeline atual")
    image_size = int(checkpoint["image_size"])
    if image_size <= 0:
        raise ValueError("image_size inválido no checkpoint")
    return checkpoint


def load_segformer_predictor(
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT,
    *,
    device: str | torch.device | None = None,
) -> SegformerPredictor:
    """Restaura modelo e processor exatamente como usados no treino."""

    from transformers import (
        AutoImageProcessor,
        SegformerConfig,
        SegformerForSemanticSegmentation,
    )

    path = Path(checkpoint_path)
    selected_device = torch.device(
        device or ("cuda" if torch.cuda.is_available() else "cpu")
    )
    checkpoint = read_segformer_checkpoint(path, map_location=selected_device)
    # O checkpoint foi treinado com SegFormer-B0. A configuração padrão da
    # classe é B0; instanciá-la localmente evita qualquer consulta de rede.
    config = SegformerConfig(
        num_labels=2,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )
    model = SegformerForSemanticSegmentation(config)
    model.load_state_dict(checkpoint["state_dict"])
    model.to(selected_device).eval()
    processor_dir = path.parent / "image_processor"
    processor_source = processor_dir if processor_dir.is_dir() else checkpoint["model_name"]
    processor = AutoImageProcessor.from_pretrained(
        processor_source,
        local_files_only=True,
    )
    return SegformerPredictor(
        model=model,
        processor=processor,
        device=selected_device,
        image_size=int(checkpoint["image_size"]),
        checkpoint_path=path,
    )


def predict_foreground_probabilities(
    predictor: SegformerPredictor,
    image: Image.Image,
) -> tuple[np.ndarray, float]:
    """Retorna probabilidades do foreground na resolução original."""

    original = image.convert("RGB")
    resized = original.resize(
        (predictor.image_size, predictor.image_size), Image.Resampling.BILINEAR
    )
    pixels = predictor.processor(
        images=resized, return_tensors="pt", do_resize=False
    )["pixel_values"].to(predictor.device)
    if predictor.device.type == "cuda":
        torch.cuda.synchronize(predictor.device)
    started = time.perf_counter()
    with torch.inference_mode(), torch.autocast(
        device_type=predictor.device.type,
        dtype=torch.float16,
        enabled=predictor.device.type == "cuda",
    ):
        logits = predictor.model(pixel_values=pixels).logits
        logits = F.interpolate(
            logits,
            size=(original.height, original.width),
            mode="bilinear",
            align_corners=False,
        )
        probabilities = torch.softmax(logits, dim=1)[0, 1]
    if predictor.device.type == "cuda":
        torch.cuda.synchronize(predictor.device)
    elapsed = time.perf_counter() - started
    return probabilities.float().cpu().numpy(), elapsed


def remove_small_components(
    mask: np.ndarray,
    *,
    min_area_ratio: float = 0.0005,
    min_area_pixels: int = 64,
) -> np.ndarray:
    """Remove somente ilhas pequenas, preservando múltiplas regiões relevantes."""

    binary = (np.asarray(mask) > 0).astype(np.uint8)
    if binary.ndim != 2:
        raise ValueError("A máscara deve ser bidimensional")
    if not 0 <= min_area_ratio <= 1 or min_area_pixels < 0:
        raise ValueError("Parâmetros de área inválidos")
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if count <= 1:
        return binary
    minimum = max(min_area_pixels, round(binary.size * min_area_ratio))
    areas = stats[1:, cv2.CC_STAT_AREA]
    kept = [index + 1 for index, area in enumerate(areas) if int(area) >= minimum]
    if not kept:
        kept = [int(np.argmax(areas)) + 1]
    return np.isin(labels, kept).astype(np.uint8)


def mask_to_normalized_polygons(
    mask: np.ndarray,
    *,
    min_area_ratio: float = 0.0005,
    min_area_pixels: int = 64,
    simplify_ratio: float = 0.003,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Converte componentes externos da máscara em polygons normalizados editáveis."""

    if simplify_ratio < 0:
        raise ValueError("simplify_ratio deve ser não negativo")
    cleaned = remove_small_components(
        mask,
        min_area_ratio=min_area_ratio,
        min_area_pixels=min_area_pixels,
    )
    height, width = cleaned.shape
    contours, _ = cv2.findContours(
        cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    polygons: list[tuple[tuple[float, float], ...]] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(contour) <= 0:
            continue
        perimeter = cv2.arcLength(contour, True)
        approximated = cv2.approxPolyDP(contour, simplify_ratio * perimeter, True)
        points = approximated.reshape(-1, 2)
        if len(points) < 3:
            continue
        denominator_x = max(width - 1, 1)
        denominator_y = max(height - 1, 1)
        polygon = tuple(
            (
                round(float(np.clip(x / denominator_x, 0.0, 1.0)), 8),
                round(float(np.clip(y / denominator_y, 0.0, 1.0)), 8),
            )
            for x, y in points
        )
        polygons.append(polygon)
    return tuple(polygons)


def predict_circulation_path(
    predictor: SegformerPredictor,
    image: Image.Image,
    *,
    threshold: float = FOREGROUND_THRESHOLD,
) -> SegmentationSuggestion:
    """Executa inferência e produz uma sugestão no formato oficial do editor."""

    if not 0 < threshold < 1:
        raise ValueError("threshold deve estar entre 0 e 1")
    probabilities, elapsed = predict_foreground_probabilities(predictor, image)
    raw_mask = (probabilities >= threshold).astype(np.uint8)
    mask = remove_small_components(raw_mask)
    polygons = mask_to_normalized_polygons(
        mask, min_area_ratio=0.0, min_area_pixels=0
    )
    foreground = probabilities[mask.astype(bool)]
    confidence = (
        float(foreground.mean()) if foreground.size else float(probabilities.max())
    )
    return SegmentationSuggestion(polygons, mask, confidence, elapsed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if not args.image.is_file():
        raise SystemExit(f"Imagem não encontrada: {args.image}")
    try:
        with Image.open(args.image) as source:
            original = source.convert("RGB")
    except OSError as error:
        raise SystemExit(f"Arquivo de imagem inválido: {error}") from error
    try:
        predictor = load_segformer_predictor(args.checkpoint)
        suggestion = predict_circulation_path(predictor, original)
    except (FileNotFoundError, KeyError, RuntimeError, ValueError, OSError) as error:
        raise SystemExit(f"Falha na inferência SegFormer: {error}") from error
    mask = Image.fromarray(suggestion.mask * 255, mode="L")
    overlay_color = Image.new("RGB", original.size, (255, 90, 50))
    overlay = Image.composite(
        Image.blend(original, overlay_color, 0.42), original, mask
    )
    output_dir = args.output_dir or args.image.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.image.stem
    mask_path = output_dir / f"{stem}_circulation_path_mask.png"
    overlay_path = output_dir / f"{stem}_circulation_path_overlay.jpg"
    mask.save(mask_path)
    overlay.save(overlay_path, quality=92)
    print(f"Máscara: {mask_path}")
    print(f"Overlay: {overlay_path}")
    print(f"Polígonos editáveis: {len(suggestion.polygons)}")
    print(f"Confiança média do foreground previsto: {suggestion.confidence:.4f}")
    print(f"Inferência ({predictor.device.type}): {suggestion.inference_seconds:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
