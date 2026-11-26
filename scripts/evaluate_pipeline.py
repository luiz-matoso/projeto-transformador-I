import csv
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor

from ml.dinov2 import CATEGORICAL_HEADS, MULTILABEL_HEADS
from ml.dinov2.dataset import load_dinov2_records, emphasize_circulation_path, emphasize_circulation_mask
from ml.dinov2.train_v2 import load_checkpoint, load_frozen_split, score_outputs
from ml.segmentation.predict import load_segformer_predictor, predict_circulation_path


def main():
    parser = argparse.ArgumentParser(description="Avaliação pareada de máscaras humanas e previstas no DINO")
    parser.add_argument("--segformer-root", type=Path, default=Path("artifacts/segmentation/v2"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/pipeline-evaluation/segformer-v2-dinov2-partial"))
    parser.add_argument("--require-common-split", action="store_true")
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    paths = [args.segformer_root / "best_segformer.pt", Path("artifacts/dinov2/v2/partial/best_dinov2_v2.pt")]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, checkpoint = load_checkpoint(paths[1], device=device)
    model.eval()
    classes = model.classes
    processor = AutoImageProcessor.from_pretrained(paths[1].parent / "image_processor", local_files_only=True)
    segmenter = load_segformer_predictor(paths[0], device=device)
    records, _, _ = load_dinov2_records("annotations/transitability_annotations.csv", "data/annotation-pilot", "annotations/annotation-schema.yaml")
    splits = load_frozen_split()
    test = [r for r in records if splits[r.filename] == "test"]
    with (args.segformer_root / "splits.csv").open(encoding="utf-8-sig", newline="") as handle:
        seg_rows = list(csv.DictReader(handle))
        seg_splits = {r["filename"]: r["split"] for r in seg_rows}
    if args.require_common_split:
        if len(seg_rows) != len(seg_splits) or seg_splits != splits or len(test) != 29:
            raise ValueError("Os splits não são idênticos ou não há 29 imagens de teste")
        test_panoramas = {r.panorama_id for r in test}
        if any(r["panorama_id"] in test_panoramas and r["split"] != "test" for r in seg_rows):
            raise ValueError("Panorama de teste presente em treino/validação")
    overlap = {r.filename: seg_splits.get(r.filename, "absent") for r in test}
    raw = {scenario: {"categorical_targets": {h: [] for h in CATEGORICAL_HEADS}, "categorical_predictions": {h: [] for h in CATEGORICAL_HEADS},
                      "multilabel_targets": {h: [] for h in MULTILABEL_HEADS}, "multilabel_probabilities": {h: [] for h in MULTILABEL_HEADS}} for scenario in ("human", "predicted")}
    rows, sample_summary = [], []
    for start in range(0, len(test), 8):
        batch = test[start:start + 8]
        views = {scenario: [] for scenario in raw}
        for record in batch:
            with Image.open(record.image_path) as source:
                image = source.convert("RGB")
            suggestion = predict_circulation_path(segmenter, image)
            human = emphasize_circulation_path(image, record.polygons)
            predicted = emphasize_circulation_mask(image, Image.fromarray(suggestion.mask * 255))
            views["human"].append(human)
            views["predicted"].append(predicted)
        outputs = {}
        with torch.inference_mode(), torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
            for scenario in raw:
                pixels = torch.cat([processor(images=view, return_tensors="pt")["pixel_values"] for view in views[scenario]]).to(device)
                outputs[scenario] = {h: value.float().cpu() for h, value in model(pixels).items()}
        for i, record in enumerate(batch):
            degraded, improved, changed, max_change = 0, 0, 0, 0.0
            for head in classes:
                if head in CATEGORICAL_HEADS:
                    target = record.categorical[head]
                    if target is None:
                        continue
                    actual = classes[head].index(target)
                    probabilities = {s: torch.softmax(outputs[s][head][i], dim=0).numpy() for s in raw}
                    predictions = {s: int(probabilities[s].argmax()) for s in raw}
                    correct = {s: predictions[s] == actual for s in raw}
                    changed += int(predictions["human"] != predictions["predicted"])
                    degraded += int(correct["human"] and not correct["predicted"])
                    improved += int(not correct["human"] and correct["predicted"])
                    rows.append({"filename": record.filename, "head": head, "label": "", "target": target,
                                 "human": classes[head][predictions["human"]], "predicted": classes[head][predictions["predicted"]],
                                 "correct_to_wrong": bool(correct["human"] and not correct["predicted"])})
                    for s in raw:
                        raw[s]["categorical_targets"][head].append(actual)
                        raw[s]["categorical_predictions"][head].append(predictions[s])
                else:
                    actual = [int(label in record.multilabel[head]) for label in classes[head]]
                    probabilities = {s: torch.sigmoid(outputs[s][head][i]).numpy() for s in raw}
                    for j, label in enumerate(classes[head]):
                        h, p = bool(probabilities["human"][j] >= 0.5), bool(probabilities["predicted"][j] >= 0.5)
                        changed += int(h != p)
                        degraded += int(h == actual[j] and p != actual[j])
                        improved += int(h != actual[j] and p == actual[j])
                        rows.append({"filename": record.filename, "head": head, "label": label, "target": actual[j],
                                     "human": int(h), "predicted": int(p), "correct_to_wrong": bool(h == actual[j] and p != actual[j])})
                    for s in raw:
                        raw[s]["multilabel_targets"][head].append(actual)
                        raw[s]["multilabel_probabilities"][head].append(probabilities[s].tolist())
                max_change = max(max_change, float(np.max(np.abs(probabilities["human"] - probabilities["predicted"]))))
            sample_summary.append({"filename": record.filename, "changed_decisions": changed, "correct_to_wrong": degraded,
                                   "wrong_to_correct": improved, "max_probability_change": max_change, "segformer_split": overlap[record.filename]})
            panel = Image.new("RGB", (960, 320))
            for column, scenario in enumerate(("human", "predicted")):
                panel.paste(views[scenario][i].resize((480, 320)), (column * 480, 0))
            panel.save(output / f"{Path(record.filename).stem}_human_vs_predicted.jpg", quality=85)
        print(f"Avaliadas {start + len(batch)}/{len(test)} imagens", flush=True)
    metrics = {s: score_outputs(values, classes) for s, values in raw.items()}
    delta = {h: metrics["predicted"]["heads"][h]["macro_f1"] - metrics["human"]["heads"][h]["macro_f1"] for h in classes}
    payload = {"metrics": metrics, "head_macro_f1_delta": delta,
               "aggregate_delta": metrics["predicted"]["aggregate_macro_f1"] - metrics["human"]["aggregate_macro_f1"],
               "checkpoint_hashes": hashes, "segformer_split_for_dino_test": overlap, "checkpoint_epoch": checkpoint["epoch"],
               "sample_count": len(test), "panel_order": "human focused image | predicted-mask focused image", "threshold": 0.5}
    payload["correct_to_wrong"] = sum(s["correct_to_wrong"] for s in sample_summary)
    payload["wrong_to_correct"] = sum(s["wrong_to_correct"] for s in sample_summary)
    payload["unchanged_images"] = sum(s["changed_decisions"] == 0 for s in sample_summary)
    (output / "metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for name, items in (("decisions.csv", rows), ("samples.csv", sample_summary)):
        with (output / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=items[0].keys()); writer.writeheader(); writer.writerows(items)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == hashes[str(p)] for p in paths)
    print(json.dumps(payload, indent=2), flush=True)


if __name__ == "__main__":
    main()
