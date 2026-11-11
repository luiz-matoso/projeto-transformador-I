import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import torch
from PIL import Image, ImageDraw, ImageFont
from torch.utils.data import DataLoader

from ml.segmentation import ID2LABEL, LABEL2ID, MODEL_NAME
from ml.segmentation.dataset import (
    CirculationPathDataset,
    SegmentationRecord,
    audit_segmentation_annotations,
    create_expanded_split,
    rasterize_polygons,
)
from ml.segmentation.predict import load_segformer_predictor
from ml.segmentation.train import (
    _forward_logits,
    _write_history,
    _write_splits,
    build_model,
    evaluate,
    set_seed,
    train_epoch,
)


V1_TRAIN_SIZE = 75


def _status_counts(path: Path) -> Counter[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return Counter(row.get("circulation_path_status", "") for row in csv.DictReader(handle))


def _v1_hashes(root: Path) -> dict[str, str]:
    names = (
        "best_segformer.pt",
        "splits.csv",
        "training_history.csv",
        "test_metrics.json",
    )
    hashes: dict[str, str] = {}
    for name in names:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Artefato v1 obrigatório ausente: {path}")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def validate_v2_output_path(output: Path, v1_root: Path) -> None:
    if output.resolve() == v1_root.resolve():
        raise ValueError("O output v2 não pode ser a pasta de artefatos do v1")


def _write_dataset_qa(
    path: Path,
    records: list[SegmentationRecord],
    excluded_unknown: int,
    assignments: dict[str, str],
    frozen_splits: Path,
) -> None:
    split_counts = Counter(assignments.values())
    subset_counts = Counter(record.subset for record in records)
    panorama_splits: dict[str, set[str]] = {}
    for record in records:
        panorama_splits.setdefault(record.panorama_id, set()).add(
            assignments[record.filename]
        )
    lines = [
        "# QA do dataset de segmentação v2",
        "",
        f"- Anotações totais: **{len(records) + excluded_unknown}**",
        f"- Máscaras válidas: **{len(records)}**",
        f"- `unknown` excluídas: **{excluded_unknown}**",
        f"- Split v1 usado como fonte congelada: `{frozen_splits.as_posix()}`",
        f"- Train: **{split_counts['train']}**",
        f"- Validation preservado: **{split_counts['validation']}**",
        f"- Test preservado: **{split_counts['test']}**",
        f"- Panoramas em mais de um split: **{sum(len(splits) > 1 for splits in panorama_splits.values())}**",
        "",
        "## Registros válidos por subset",
        "",
        "| Subset | Quantidade |",
        "|---|---:|",
    ]
    for subset in ("Obstacle", "CurbRamp", "SurfaceProblem"):
        lines.append(f"| {subset} | {subset_counts[subset]} |")
    lines.extend(
        [
            "",
            "## Decisão",
            "",
            "Dataset liberado. Validation/test do v1 foram preservados e nenhuma linha `unknown` entrou no split.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _prediction_mask(model, processor, image: Image.Image, size: int, device: torch.device) -> Image.Image:
    resized = image.resize((size, size), Image.Resampling.BILINEAR)
    pixels = processor(images=resized, return_tensors="pt", do_resize=False)[
        "pixel_values"
    ].to(device)
    with torch.inference_mode(), torch.autocast(
        device_type=device.type,
        dtype=torch.float16,
        enabled=device.type == "cuda",
    ):
        logits = _forward_logits(model, pixels, (size, size))
    prediction = logits.argmax(dim=1)[0].byte().cpu().numpy() * 255
    return Image.fromarray(prediction, mode="L")


def _comparison_visuals(
    v1_model,
    v2_model,
    processor,
    records: list[SegmentationRecord],
    output: Path,
    image_size: int,
    device: torch.device,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    thumbnails: list[Image.Image] = []
    colors = ((0, 210, 255), (255, 90, 50), (180, 70, 255))
    for record in records:
        with Image.open(record.image_path) as source:
            original = source.convert("RGB")
        resized = original.resize((image_size, image_size), Image.Resampling.BILINEAR)
        ground_truth = rasterize_polygons(
            record.polygons, record.image_width, record.image_height
        ).resize((image_size, image_size), Image.Resampling.NEAREST)
        ground_truth = ground_truth.point(lambda value: 255 if value else 0)
        v1_mask = _prediction_mask(v1_model, processor, original, image_size, device)
        v2_mask = _prediction_mask(v2_model, processor, original, image_size, device)
        masks = (ground_truth, v1_mask, v2_mask)
        views = [resized]
        for color, mask in zip(colors, masks):
            overlay_color = Image.new("RGB", resized.size, color)
            views.append(
                Image.composite(Image.blend(resized, overlay_color, 0.45), resized, mask)
            )
        panel = Image.new("RGB", (image_size * 4, image_size + 30), "white")
        for column, view in enumerate(views):
            panel.paste(view, (column * image_size, 30))
        draw = ImageDraw.Draw(panel)
        for column, label in enumerate(("Original", "Ground Truth", "SegFormer v1", "SegFormer v2")):
            draw.text(
                (column * image_size + 6, 8),
                label,
                fill="black",
                font=ImageFont.load_default(),
            )
        panel_path = output / f"{Path(record.filename).stem}_v1_v2_comparison.jpg"
        panel.save(panel_path, quality=91)
        thumbnail = panel.copy()
        thumbnail.thumbnail((1600, 430), Image.Resampling.LANCZOS)
        thumbnails.append(thumbnail)
    sheet = Image.new("RGB", (1600, sum(item.height for item in thumbnails)), "white")
    y = 0
    for thumbnail in thumbnails:
        sheet.paste(thumbnail, (0, y))
        y += thumbnail.height
    sheet.save(output / "test_contact_sheet.jpg", quality=91)


def _write_comparison(
    path: Path,
    v1_metrics: dict[str, float],
    v2_metrics: dict[str, float],
    checkpoint: dict,
    train_size: int,
    history: list[dict[str, float | int]],
) -> None:
    labels = (
        ("Foreground IoU", "foreground_iou"),
        ("Dice", "dice"),
        ("Precision", "precision"),
        ("Recall", "recall"),
    )
    lines = [
        "# Comparação SegFormer v1 × v2",
        "",
        "| Métrica | V1 | V2 | Delta |",
        "|---|---:|---:|---:|",
    ]
    for label, key in labels:
        v1_value = float(v1_metrics[key])
        v2_value = float(v2_metrics[key])
        lines.append(
            f"| {label} | {v1_value:.4f} | {v2_value:.4f} | {v2_value - v1_value:+.4f} |"
        )
    validation = checkpoint["validation_metrics"]
    best_row = next(row for row in history if row["epoch"] == checkpoint["epoch"])
    final_row = history[-1]
    overfitting_signal = (
        float(final_row["train_loss"]) < float(best_row["train_loss"])
        and float(final_row["validation_iou"]) < float(best_row["validation_iou"])
    )
    lines.extend(
        [
            "",
            "## Seleção por validação",
            "",
            f"- Melhor epoch v2: **{checkpoint['epoch']}**",
            f"- Validation IoU v2: **{validation['foreground_iou']:.4f}**",
            f"- Validation Dice v2: **{validation['dice']:.4f}**",
            f"- Train v1: **{V1_TRAIN_SIZE}** imagens",
            f"- Train v2: **{train_size}** imagens",
            "- O test congelado foi avaliado uma única vez após a seleção do checkpoint.",
            "",
            "## Sinal de overfitting",
            "",
            (
                f"- **Sim, após o melhor checkpoint.** Entre as épocas {checkpoint['epoch']} e "
                f"{final_row['epoch']}, a train loss caiu de {float(best_row['train_loss']):.4f} "
                f"para {float(final_row['train_loss']):.4f}, enquanto a validation IoU caiu de "
                f"{float(best_row['validation_iou']):.4f} para {float(final_row['validation_iou']):.4f}. "
                "O early stopping impediu que essas épocas substituíssem o melhor checkpoint."
                if overfitting_signal
                else "- Não foi observado o padrão de train loss menor acompanhado por queda da validation IoU após o melhor checkpoint."
            ),
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    from transformers import AutoImageProcessor

    parser = argparse.ArgumentParser(description="Treina o SegFormer-B0 v2.")
    parser.add_argument("--annotations", type=Path, default=Path("annotations/transitability_annotations.csv"))
    parser.add_argument("--pilot-root", type=Path, default=Path("data/annotation-pilot"))
    parser.add_argument("--v1-root", type=Path, default=Path("artifacts/segmentation"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/segmentation/v2"))
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=6e-5)
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    validate_v2_output_path(args.output, args.v1_root)
    before_hashes = _v1_hashes(args.v1_root)
    status_counts = _status_counts(args.annotations)
    if status_counts != Counter({"annotated": 192, "unknown": 8}):
        raise SystemExit(f"Distribuição de status inesperada: {dict(status_counts)}")
    records, issues = audit_segmentation_annotations(
        args.annotations,
        args.pilot_root,
        excluded_statuses={"unknown"},
    )
    if issues:
        details = "\n".join(f"- {item.filename}: {item.message}" for item in issues)
        raise SystemExit(f"Treinamento v2 bloqueado pelo QA:\n{details}")
    if len(records) != 192:
        raise SystemExit(f"Esperadas 192 máscaras válidas; encontradas {len(records)}")
    frozen_splits = args.v1_root / "splits.csv"
    assignments = create_expanded_split(records, frozen_splits)
    split_records = {
        split: [record for record in records if assignments[record.filename] == split]
        for split in ("train", "validation", "test")
    }
    if {name: len(items) for name, items in split_records.items()} != {
        "train": 162,
        "validation": 15,
        "test": 15,
    }:
        raise SystemExit("Split v2 não corresponde a 162/15/15")

    args.output.mkdir(parents=True, exist_ok=True)
    _write_splits(args.output / "splits.csv", records, assignments)
    _write_dataset_qa(
        args.output / "dataset_qa.md",
        records,
        status_counts["unknown"],
        assignments,
        frozen_splits,
    )

    set_seed(args.seed)
    processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    processor.save_pretrained(args.output / "image_processor")
    datasets = {
        "train": CirculationPathDataset(
            split_records["train"],
            image_processor=processor,
            image_size=args.image_size,
            augment=True,
        ),
        "validation": CirculationPathDataset(
            split_records["validation"],
            image_processor=processor,
            image_size=args.image_size,
        ),
        "test": CirculationPathDataset(
            split_records["test"],
            image_processor=processor,
            image_size=args.image_size,
        ),
    }
    loaders = {
        name: DataLoader(
            dataset,
            batch_size=args.batch_size,
            shuffle=name == "train",
            num_workers=0,
            pin_memory=True,
        )
        for name, dataset in datasets.items()
    }
    if not torch.cuda.is_available():
        raise SystemExit("CUDA é obrigatória para o treino v2")
    device = torch.device("cuda")
    model = build_model().to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.learning_rate, weight_decay=0.01
    )
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
            f"val_loss={validation['loss']:.5f} | "
            f"val_iou={validation['foreground_iou']:.4f} | "
            f"val_dice={validation['dice']:.4f}",
            flush=True,
        )
        improved = validation["foreground_iou"] > best_iou or (
            validation["foreground_iou"] == best_iou
            and validation["loss"] < best_validation_loss
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
                    "train_size": len(datasets["train"]),
                    "validation_size": len(datasets["validation"]),
                    "test_size": len(datasets["test"]),
                    "initialized_from": MODEL_NAME,
                },
                checkpoint_path,
            )
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(f"Early stopping após {epoch} épocas.", flush=True)
                break

    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["state_dict"])
    test_metrics = evaluate(model, loaders["test"], device)
    (args.output / "test_metrics.json").write_text(
        json.dumps(test_metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    v1_metrics = json.loads((args.v1_root / "test_metrics.json").read_text(encoding="utf-8"))
    _write_comparison(
        args.output / "comparison_v1_v2.md",
        v1_metrics,
        test_metrics,
        checkpoint,
        len(datasets["train"]),
        history,
    )
    v1_predictor = load_segformer_predictor(
        args.v1_root / "best_segformer.pt", device=device
    )
    _comparison_visuals(
        v1_predictor.model,
        model,
        processor,
        split_records["test"],
        args.output / "test_predictions",
        args.image_size,
        device,
    )
    if _v1_hashes(args.v1_root) != before_hashes:
        raise RuntimeError("Um ou mais artefatos v1 foram alterados durante o treino v2")
    print(
        f"Teste congelado: IoU={test_metrics['foreground_iou']:.4f} "
        f"Dice={test_metrics['dice']:.4f} "
        f"Precision={test_metrics['precision']:.4f} "
        f"Recall={test_metrics['recall']:.4f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
