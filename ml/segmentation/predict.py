"""Inferência de circulation_path em uma imagem arbitrária."""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image


def main() -> int:
    from transformers import AutoImageProcessor, SegformerConfig, SegformerForSemanticSegmentation

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--checkpoint", type=Path, default=Path("artifacts/segmentation/best_segformer.pt"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if not args.image.is_file():
        raise SystemExit(f"Imagem não encontrada: {args.image}")
    if not args.checkpoint.is_file():
        raise SystemExit(f"Checkpoint não encontrado: {args.checkpoint}")
    try:
        with Image.open(args.image) as source:
            original = source.convert("RGB")
    except OSError as error:
        raise SystemExit(f"Arquivo de imagem inválido: {error}") from error
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(args.checkpoint, map_location=device, weights_only=True)
    model_name = checkpoint["model_name"]
    image_size = int(checkpoint["image_size"])
    config = SegformerConfig.from_pretrained(
        model_name,
        num_labels=2,
        id2label={0: "background", 1: "circulation_path"},
        label2id={"background": 0, "circulation_path": 1},
    )
    model = SegformerForSemanticSegmentation(config)
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device).eval()
    processor_dir = args.checkpoint.parent / "image_processor"
    processor = AutoImageProcessor.from_pretrained(processor_dir if processor_dir.is_dir() else model_name)
    resized = original.resize((image_size, image_size), Image.Resampling.BILINEAR)
    pixels = processor(images=resized, return_tensors="pt", do_resize=False)["pixel_values"].to(device)
    with torch.no_grad(), torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
        logits = model(pixel_values=pixels).logits
        logits = F.interpolate(logits, size=(original.height, original.width), mode="bilinear", align_corners=False)
        probabilities = torch.softmax(logits, dim=1)[0, 1]
    prediction_tensor = probabilities >= 0.5
    prediction = prediction_tensor.byte().cpu().numpy()
    mask = Image.fromarray(prediction * 255, mode="L")
    overlay_color = Image.new("RGB", original.size, (255, 90, 50))
    overlay = Image.composite(Image.blend(original, overlay_color, 0.42), original, mask)
    output_dir = args.output_dir or args.image.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.image.stem
    mask_path = output_dir / f"{stem}_circulation_path_mask.png"
    overlay_path = output_dir / f"{stem}_circulation_path_overlay.jpg"
    mask.save(mask_path)
    overlay.save(overlay_path, quality=92)
    foreground = probabilities[prediction_tensor]
    confidence = float(foreground.mean()) if foreground.numel() else float(probabilities.max())
    print(f"Máscara: {mask_path}")
    print(f"Overlay: {overlay_path}")
    print(f"Confiança média do foreground previsto: {confidence:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
