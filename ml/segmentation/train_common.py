import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from ml.dinov2.train_v2 import FROZEN_SPLIT, load_frozen_split
from ml.segmentation import ID2LABEL, LABEL2ID, MODEL_NAME
from ml.segmentation.dataset import CirculationPathDataset, audit_segmentation_annotations
from ml.segmentation.train import build_model, evaluate, set_seed, train_epoch, _write_history


OUTPUT = Path("artifacts/segmentation/common-dino-split")
LIMITATION = "O teste é comum aos dois modelos, mas não é um holdout final completamente cego: seus resultados já foram observados durante o desenvolvimento."


def validate_common_split(records):
    assignments = load_frozen_split()
    if {record.filename for record in records} != set(assignments):
        raise ValueError("Registros não correspondem ao split DINO")
    with FROZEN_SPLIT.open(encoding="utf-8-sig", newline="") as handle:
        original = {row["filename"]: row for row in csv.DictReader(handle)}
    panoramas = {}
    for record in records:
        if record.panorama_id != original[record.filename]["panorama_id"]:
            raise ValueError(f"Panorama incompatível: {record.filename}")
        split = assignments[record.filename]
        if record.panorama_id in panoramas and panoramas[record.panorama_id] != split:
            raise ValueError(f"Panorama em splits diferentes: {record.panorama_id}")
        panoramas[record.panorama_id] = split
    return assignments


def main():
    from transformers import AutoImageProcessor

    if OUTPUT.exists():
        raise SystemExit(f"Destino já existe: {OUTPUT}")
    if not torch.cuda.is_available():
        raise SystemExit("CUDA necessária")
    protected = [Path("artifacts/segmentation/v2/best_segformer.pt"),
                 Path("artifacts/dinov2/v2/partial/best_dinov2_v2.pt")]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    records, issues = audit_segmentation_annotations("annotations/transitability_annotations.csv", "data/annotation-pilot", excluded_statuses={"unknown"})
    if issues:
        raise ValueError(f"QA bloqueado: {issues}")
    assignments = validate_common_split(records)
    splits = {name: [r for r in records if assignments[r.filename] == name] for name in ("train", "validation", "test")}
    print(f"Split DINO validado: {dict(Counter(assignments.values()))}; panoramas isolados", flush=True)
    OUTPUT.mkdir(parents=True)
    shutil.copyfile(FROZEN_SPLIT, OUTPUT / "splits.csv")
    assert (OUTPUT / "splits.csv").read_bytes() == FROZEN_SPLIT.read_bytes()
    config = {"model_name": MODEL_NAME, "initialized_from": MODEL_NAME, "image_size": 512,
              "loss": "Cross Entropy + Dice", "optimizer": "AdamW", "learning_rate": 6e-5,
              "weight_decay": 0.01, "batch_size": 4, "amp": True, "max_epochs": 30,
              "patience": 5, "seed": 42, "selection": "validation foreground IoU; tie: validation loss",
              "split_source": str(FROZEN_SPLIT), "split_sha256": hashlib.sha256(FROZEN_SPLIT.read_bytes()).hexdigest(),
              "split_sizes": {name: len(items) for name, items in splits.items()}, "limitation": LIMITATION}
    (OUTPUT / "training_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUTPUT / "dataset_qa.md").write_text(f"# Split comum SegFormer/DINO\n\n192 máscaras válidas; 8 unknown excluídas.\n134 treino / 29 validação / 29 teste.\nCópia byte a byte do split DINO; nenhum panorama cruza splits.\n\n{LIMITATION}\n", encoding="utf-8")
    set_seed(42)
    processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    processor.save_pretrained(OUTPUT / "image_processor")
    datasets = {name: CirculationPathDataset(items, image_processor=processor, image_size=512, augment=name == "train") for name, items in splits.items()}
    loaders = {name: DataLoader(dataset, batch_size=4, shuffle=name == "train", num_workers=0, pin_memory=True) for name, dataset in datasets.items()}
    device = torch.device("cuda")
    model = build_model().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=6e-5, weight_decay=0.01)
    scaler = torch.amp.GradScaler("cuda")
    history, best_iou, best_loss, patience = [], -1.0, float("inf"), 0
    checkpoint_path = OUTPUT / "best_segformer.pt"
    for epoch in range(1, 31):
        loss = train_epoch(model, loaders["train"], optimizer, scaler, device)
        validation = evaluate(model, loaders["validation"], device)
        history.append({"epoch": epoch, "train_loss": loss, "validation_loss": validation["loss"], "validation_iou": validation["foreground_iou"], "validation_dice": validation["dice"]})
        _write_history(OUTPUT / "training_history.csv", history)
        print(f"Epoch {epoch}: train={loss:.4f} val={validation['loss']:.4f} IoU={validation['foreground_iou']:.4f} Dice={validation['dice']:.4f}", flush=True)
        if validation["foreground_iou"] > best_iou or (validation["foreground_iou"] == best_iou and validation["loss"] < best_loss):
            best_iou, best_loss, patience = validation["foreground_iou"], validation["loss"], 0
            torch.save({"state_dict": model.state_dict(), "model_name": MODEL_NAME, "id2label": ID2LABEL,
                        "label2id": LABEL2ID, "image_size": 512, "seed": 42, "epoch": epoch,
                        "validation_metrics": validation, "config": config, "initialized_from": MODEL_NAME}, checkpoint_path)
        else:
            patience += 1
        if patience >= 5:
            break
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["state_dict"])
    test = evaluate(model, loaders["test"], device)
    (OUTPUT / "test_metrics.json").write_text(json.dumps(test, indent=2), encoding="utf-8")
    (OUTPUT / "validation_metrics.json").write_text(json.dumps(checkpoint["validation_metrics"], indent=2), encoding="utf-8")
    old = json.loads(Path("artifacts/segmentation/v2/test_metrics.json").read_text())
    lines = ["# SegFormer: teste comum ao DINO", "", LIMITATION, "",
             "Os testes e os tamanhos de treino são diferentes; os deltas abaixo não isolam ganho ou perda de modelo.", "",
             "| Métrica | V2 anterior (15 teste) | Split comum (29 teste) | Delta |", "|---|---:|---:|---:|"]
    for key in ("foreground_iou", "dice", "precision", "recall"):
        lines.append(f"| {key} | {old[key]:.4f} | {test[key]:.4f} | {test[key]-old[key]:+.4f} |")
    lines.extend(["", f"Melhor época: {checkpoint['epoch']}. Train anterior: 162; comum: 134.", "Teste avaliado uma vez, após restaurar o checkpoint escolhido pela validação."])
    (OUTPUT / "comparison_previous_v2.md").write_text("\n".join(lines), encoding="utf-8")
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == hashes[str(p)] for p in protected)
    print(f"Melhor época: {checkpoint['epoch']}; teste: {test}", flush=True)


if __name__ == "__main__":
    main()
