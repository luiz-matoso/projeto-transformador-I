import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from PIL import Image

from ml.dinov2.dataset import load_dinov2_records
from ml.dinov2.train_v2 import load_frozen_split
from ml.mobility_profile import MobilityProfile
from ml.pipeline import DINO_CHECKPOINT, SEGFORMER_CHECKPOINT, apply_profile, observe_scene


# Cenários de teste funcionais; não representam grupos de pessoas ou diagnósticos.
EXAMPLE_PROFILES = {
    "wide_regular_no_steps": MobilityProfile("wide", "regular_only", "none", False),
    "adequate_minor_partial": MobilityProfile("adequate", "minor_problems", "minor", True),
    "narrow_major_steps": MobilityProfile("narrow", "major_problems", "step", True),
}


def main():
    output = Path("artifacts/pipeline-evaluation/mobility-engine-v1")
    output.mkdir(parents=True, exist_ok=False)
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (SEGFORMER_CHECKPOINT, DINO_CHECKPOINT)}
    split = load_frozen_split()
    with (SEGFORMER_CHECKPOINT.parent / "splits.csv").open(encoding="utf-8-sig", newline="") as handle:
        if {r["filename"]: r["split"] for r in csv.DictReader(handle)} != split:
            raise ValueError("Splits diferentes")
    records, _, _ = load_dinov2_records("annotations/transitability_annotations.csv", "data/annotation-pilot", "annotations/annotation-schema.yaml")
    test = [r for r in records if split[r.filename] == "test"]
    rows, counts = [], {name: Counter() for name in EXAMPLE_PROFILES}
    for record in test:
        scene = observe_scene(record.image_path)
        mask_file = record.image_path.stem + "_mask.png"
        Image.fromarray(scene.pop("mask") * 255).save(output / mask_file)
        scene["mask_path"] = mask_file
        for name, profile in EXAMPLE_PROFILES.items():
            result = apply_profile(scene, profile)
            result.update(filename=record.filename, scenario=name)
            rows.append(result)
            counts[name][result["classification"]] += 1
        print(f"Avaliada: {record.filename}", flush=True)
    (output / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {"image_count": len(test), "assessment_count": len(rows),
               "profiles": {name: asdict(profile) for name, profile in EXAMPLE_PROFILES.items()},
               "classifications": counts, "checkpoint_hashes": hashes,
               "purpose": "Execução e consistência; sem ground truth de transitabilidade personalizada e sem métrica de acurácia.",
               "limitation": "Teste comum sem participação em treino/validação, mas observado anteriormente durante o desenvolvimento."}
    for path, digest in hashes.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
