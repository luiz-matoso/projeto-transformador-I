import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ml.dinov2 import ALL_HEADS
from ml.dinov2.dataset import load_dinov2_records
from ml.dinov2.train_v2 import load_frozen_split
from ml.segmentation.dataset import rasterize_polygons
from ml.segmentation.predict import load_segformer_predictor, predict_circulation_path


def ranks(values):
    values = np.asarray(values)
    return np.asarray([np.sum(values < value) + (np.sum(values == value) - 1) / 2 for value in values])


def correlation(x, y):
    if np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def main():
    source = Path("artifacts/pipeline-evaluation/common-split-dinov2-partial")
    output = source / "mask-error-analysis"
    output.mkdir(exist_ok=False)
    provenance = json.loads((source / "metrics.json").read_text())
    for path, digest in provenance["checkpoint_hashes"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Checkpoint mudou desde avaliação: {path}")
    with (source / "decisions.csv").open(newline="", encoding="utf-8") as handle:
        decisions = list(csv.DictReader(handle))
    records, _, _ = load_dinov2_records("annotations/transitability_annotations.csv", "data/annotation-pilot", "annotations/annotation-schema.yaml")
    split = load_frozen_split()
    records = [record for record in records if split[record.filename] == "test"]
    predictor = load_segformer_predictor("artifacts/segmentation/common-dino-split/best_segformer.pt")
    rows, changes = [], []
    for record in records:
        with Image.open(record.image_path) as source_image:
            image = source_image.convert("RGB")
        gt = np.asarray(rasterize_polygons(record.polygons, image.width, image.height)).astype(bool)
        predicted = predict_circulation_path(predictor, image).mask.astype(bool)
        intersection = int((gt & predicted).sum())
        union = int((gt | predicted).sum())
        row = {"filename": record.filename, "iou": intersection / union,
               "dice": 2 * intersection / (int(gt.sum()) + int(predicted.sum())),
               "human_area_fraction": float(gt.mean()), "predicted_area_fraction": float(predicted.mean()),
               "changed": 0, "correct_to_wrong": 0, "wrong_to_correct": 0}
        for head in ALL_HEADS:
            local = [d for d in decisions if d["filename"] == record.filename and d["head"] == head]
            modified = [d for d in local if d["human"] != d["predicted"]]
            bad = sum(d["human"] == d["target"] and d["predicted"] != d["target"] for d in modified)
            good = sum(d["human"] != d["target"] and d["predicted"] == d["target"] for d in modified)
            row[f"{head}_changed"] = len(modified)
            row[f"{head}_correct_to_wrong"] = bad
            row[f"{head}_wrong_to_correct"] = good
            row["changed"] += len(modified)
            row["correct_to_wrong"] += bad
            row["wrong_to_correct"] += good
            for decision in modified:
                changes.append({**decision, "iou": row["iou"], "dice": row["dice"],
                                "transition": "correct_to_wrong" if decision["human"] == decision["target"] else "wrong_to_correct" if decision["predicted"] == decision["target"] else "wrong_to_wrong"})
        row["net_errors"] = row["correct_to_wrong"] - row["wrong_to_correct"]
        rows.append(row)
        panel = Image.new("RGB", (960, 350), "white")
        panel.paste(image.resize((320, 320)), (0, 30))
        for col, mask in enumerate((gt, predicted), start=1):
            panel.paste(Image.fromarray(mask.astype(np.uint8) * 255).convert("RGB").resize((320, 320)), (320 * col, 30))
        draw = ImageDraw.Draw(panel)
        draw.text((5, 5), "Original", fill="black")
        draw.text((325, 5), "Human mask", fill="black")
        draw.text((645, 5), f"Predicted IoU={row['iou']:.3f} Dice={row['dice']:.3f}", fill="black")
        panel.save(output / f"{Path(record.filename).stem}_masks.jpg", quality=88)
    for filename, table in (("per_image.csv", rows), ("changed_decisions.csv", changes)):
        with (output / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=table[0].keys()); writer.writeheader(); writer.writerows(table)
    iou = [r["iou"] for r in rows]
    stats = {"n": len(rows), "mean_iou": float(np.mean(iou)), "mean_dice": float(np.mean([r["dice"] for r in rows])), "correlations": {}}
    for field in ("changed", "correct_to_wrong", "net_errors", *(f"{h}_correct_to_wrong" for h in ALL_HEADS)):
        y = [r[field] for r in rows]
        stats["correlations"][field] = {"pearson_iou": correlation(iou, y), "spearman_iou": correlation(ranks(iou), ranks(y))}
    for name, subset in (("low_iou", sorted(rows, key=lambda r: r["iou"])[:10]), ("high_iou", sorted(rows, key=lambda r: r["iou"])[-10:])):
        stats[name] = {"n": len(subset), "mean_iou": float(np.mean([r["iou"] for r in subset])), "correct_to_wrong": sum(r["correct_to_wrong"] for r in subset), "wrong_to_correct": sum(r["wrong_to_correct"] for r in subset), "unchanged": sum(r["changed"] == 0 for r in subset)}
    (output / "statistics.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    for path, digest in provenance["checkpoint_hashes"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    print(json.dumps(stats, indent=2))
    for row in sorted(rows, key=lambda r: r["iou"]):
        print(row["filename"], round(row["iou"], 3), round(row["dice"], 3), row["changed"], row["correct_to_wrong"], row["wrong_to_correct"])


if __name__ == "__main__":
    main()
