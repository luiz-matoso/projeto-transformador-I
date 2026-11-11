import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFont
from torch.utils.data import DataLoader

from ml.segmentation import ID2LABEL, LABEL2ID, MODEL_NAME
from ml.segmentation.dataset import (
    CirculationPathDataset,
    SegmentationRecord,
    audit_segmentation_annotations,
    create_grouped_split,
    rasterize_polygons,
)
from ml.segmentation.metrics import (
    binary_segmentation_counts,
    combined_segmentation_loss,
    metrics_from_counts,
)


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def build_model():
    from transformers import SegformerForSemanticSegmentation

    return SegformerForSemanticSegmentation.from_pretrained(
        MODEL_NAME,
        num_labels=2,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        ignore_mismatched_sizes=True,
    )


def _forward_logits(model, pixel_values: torch.Tensor, target_size: tuple[int, int]) -> torch.Tensor:
    logits = model(pixel_values=pixel_values).logits
    return F.interpolate(logits, size=target_size, mode="bilinear", align_corners=False)


def train_epoch(model, loader, optimizer, scaler, device: torch.device) -> float:
    model.train()
    loss_sum = 0.0
    for batch in loader:
        pixels = batch["pixel_values"].to(device, non_blocking=True)
        labels = batch["labels"].to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
            logits = _forward_logits(model, pixels, labels.shape[-2:])
            loss = combined_segmentation_loss(logits, labels)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        loss_sum += float(loss.detach()) * labels.size(0)
    return loss_sum / len(loader.dataset)


@torch.no_grad()
def evaluate(model, loader, device: torch.device) -> dict[str, float]:
    model.eval()
    loss_sum = 0.0
    counts = Counter()
    for batch in loader:
        pixels = batch["pixel_values"].to(device, non_blocking=True)
        labels = batch["labels"].to(device, non_blocking=True)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
            logits = _forward_logits(model, pixels, labels.shape[-2:])
            loss = combined_segmentation_loss(logits, labels)
        predictions = logits.argmax(dim=1)
        tp, fp, fn, tn = binary_segmentation_counts(predictions, labels)
        counts.update({"tp": tp, "fp": fp, "fn": fn, "tn": tn})
        loss_sum += float(loss) * labels.size(0)
    metrics = metrics_from_counts(counts["tp"], counts["fp"], counts["fn"], counts["tn"])
    metrics["loss"] = loss_sum / len(loader.dataset)
    return metrics


def _write_splits(path: Path, records: list[SegmentationRecord], assignments: dict[str, str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("filename", "subset", "panorama_id", "split"), lineterminator="\n")
        writer.writeheader()
        for record in sorted(records, key=lambda item: item.filename):
            writer.writerow({
                "filename": record.filename,
                "subset": record.subset,
                "panorama_id": record.panorama_id,
                "split": assignments[record.filename],
            })


def _write_history(path: Path, rows: list[dict[str, float | int]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("epoch", "train_loss", "validation_loss", "validation_iou", "validation_dice"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


@torch.no_grad()
def _test_visuals(model, processor, records: list[SegmentationRecord], output: Path, image_size: int, device: torch.device) -> None:
    output.mkdir(parents=True, exist_ok=True)
    panels: list[Image.Image] = []
    for record in records:
        with Image.open(record.image_path) as source:
            original = source.convert("RGB")
        resized = original.resize((image_size, image_size), Image.Resampling.BILINEAR)
        ground_truth = rasterize_polygons(record.polygons, record.image_width, record.image_height).resize((image_size, image_size), Image.Resampling.NEAREST)
        pixels = processor(images=resized, return_tensors="pt", do_resize=False)["pixel_values"].to(device)
        logits = _forward_logits(model, pixels, (image_size, image_size))
        prediction = logits.argmax(dim=1)[0].byte().cpu().numpy()
        predicted_mask = Image.fromarray(prediction, mode="L")
        ground_rgb = Image.new("RGB", resized.size, (0, 210, 255))
        prediction_rgb = Image.new("RGB", resized.size, (255, 90, 50))
        gt_view = Image.composite(ground_rgb, Image.new("RGB", resized.size, "black"), ground_truth.point(lambda value: 255 if value else 0))
        pred_view = Image.composite(prediction_rgb, Image.new("RGB", resized.size, "black"), predicted_mask.point(lambda value: 255 if value else 0))
        overlay = Image.composite(Image.blend(resized, prediction_rgb, 0.42), resized, predicted_mask.point(lambda value: 255 if value else 0))
        panel = Image.new("RGB", (image_size * 4, image_size + 28), "white")
        for column, item in enumerate((resized, gt_view, pred_view, overlay)):
            panel.paste(item, (column * image_size, 28))
        draw = ImageDraw.Draw(panel)
        draw.text((5, 7), "original", fill="black", font=ImageFont.load_default())
        draw.text((image_size + 5, 7), "ground truth", fill="black", font=ImageFont.load_default())
        draw.text((image_size * 2 + 5, 7), "prediction", fill="black", font=ImageFont.load_default())
        draw.text((image_size * 3 + 5, 7), "overlay", fill="black", font=ImageFont.load_default())
        panel.save(output / f"{Path(record.filename).stem}_comparison.jpg", quality=91)
        thumbnail = panel.copy()
        thumbnail.thumbnail((1200, 320), Image.Resampling.LANCZOS)
        panels.append(thumbnail)
    sheet = Image.new("RGB", (1200, sum(panel.height for panel in panels)), "white")
    y = 0
    for panel in panels:
        sheet.paste(panel, (0, y))
        y += panel.height
    sheet.save(output / "test_contact_sheet.jpg", quality=91)


def main() -> int:
    from transformers import AutoImageProcessor

    parser = argparse.ArgumentParser(description="Treina o SegFormer-B0 v1.")
    parser.add_argument("--annotations", type=Path, default=Path("annotations/transitability_annotations.csv"))
    parser.add_argument("--pilot-root", type=Path, default=Path("data/annotation-pilot"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/segmentation"))
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=6e-5)
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("CUDA é obrigatória para este treino; nenhuma GPU compatível foi encontrada.")
    records, issues = audit_segmentation_annotations(args.annotations, args.pilot_root)
    if issues:
        details = "\n".join(f"- {issue.filename}: {issue.message}" for issue in issues)
        raise SystemExit(f"Treinamento bloqueado pelo QA ({len(issues)} erro(s)):\n{details}")
    assignments = create_grouped_split(records, args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    _write_splits(args.output / "splits.csv", records, assignments)
    split_records = {
        split: [record for record in records if assignments[record.filename] == split]
        for split in ("train", "validation", "test")
    }
    set_seed(args.seed)
    processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    processor.save_pretrained(args.output / "image_processor")
    datasets = {
        "train": CirculationPathDataset(split_records["train"], image_processor=processor, image_size=args.image_size, augment=True),
        "validation": CirculationPathDataset(split_records["validation"], image_processor=processor, image_size=args.image_size),
        "test": CirculationPathDataset(split_records["test"], image_processor=processor, image_size=args.image_size),
    }
    loaders = {
        name: DataLoader(dataset, batch_size=args.batch_size, shuffle=name == "train", num_workers=0, pin_memory=True)
        for name, dataset in datasets.items()
    }
    device = torch.device("cuda")
    model = build_model().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.01)
    scaler = torch.amp.GradScaler("cuda")
    history: list[dict[str, float | int]] = []
    best_iou = -1.0
    best_validation_loss = float("inf")
    epochs_without_improvement = 0
    checkpoint_path = args.output / "best_segformer.pt"
    for epoch in range(1, args.epochs + 1):
        train_loss = train_epoch(model, loaders["train"], optimizer, scaler, device)
        validation = evaluate(model, loaders["validation"], device)
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "validation_loss": validation["loss"],
            "validation_iou": validation["foreground_iou"],
            "validation_dice": validation["dice"],
        }
        history.append(row)
        _write_history(args.output / "training_history.csv", history)
        print(
            f"Epoch {epoch}/{args.epochs} | train_loss={train_loss:.5f} | "
            f"val_loss={validation['loss']:.5f} | val_iou={validation['foreground_iou']:.4f} | val_dice={validation['dice']:.4f}"
        )
        improved = validation["foreground_iou"] > best_iou or (
            validation["foreground_iou"] == best_iou and validation["loss"] < best_validation_loss
        )
        if improved:
            best_iou = validation["foreground_iou"]
            best_validation_loss = validation["loss"]
            epochs_without_improvement = 0
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "model_name": MODEL_NAME,
                    "id2label": ID2LABEL,
                    "label2id": LABEL2ID,
                    "image_size": args.image_size,
                    "seed": args.seed,
                    "epoch": epoch,
                    "validation_metrics": validation,
                },
                checkpoint_path,
            )
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(f"Early stopping após {epoch} épocas.")
                break
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["state_dict"])
    test_metrics = evaluate(model, loaders["test"], device)
    (args.output / "test_metrics.json").write_text(
        json.dumps(test_metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _test_visuals(model, processor, split_records["test"], args.output / "test_predictions", args.image_size, device)
    print(f"Teste congelado: IoU={test_metrics['foreground_iou']:.4f} Dice={test_metrics['dice']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
