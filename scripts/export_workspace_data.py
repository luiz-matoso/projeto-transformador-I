"""Exporta somente schema e resultados públicos; nunca imagens, pesos ou credenciais."""
import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from tools.annotation_app.core import load_schema
from tools.annotation_app.v4 import workspace_schema
from tools.annotation_app.presentation import OPTION_LABELS, FIELD_GROUPS

ROOT = Path(__file__).resolve().parents[1]


def build_payload():
    sources = {}
    def read(path):
        p = ROOT / path
        sources[path] = hashlib.sha256(p.read_bytes()).hexdigest()
        return json.loads(p.read_text(encoding="utf-8"))
    schema_path = ROOT / "annotations/annotation-schema.yaml"
    schema = load_schema(schema_path)
    sources[str(schema_path.relative_to(ROOT))] = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    with (ROOT / "annotations/transitability_annotations.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    annotations_path = "annotations/transitability_annotations.csv"
    sources[annotations_path] = hashlib.sha256((ROOT / annotations_path).read_bytes()).hexdigest()
    manifest_path = ROOT / "data/annotation-pilot/pilot_manifest.csv"
    with manifest_path.open(encoding="utf-8-sig", newline="") as f:
        manifest = list(csv.DictReader(f))
    sources[str(manifest_path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    subset_by_filename = {r[key]: r["subset"] for r in manifest for key in
                          ("local_filename", "annotation_filename", "original_filename") if r.get(key)}
    subsets = Counter(subset_by_filename[row["filename"]] for row in rows)
    experiments = []
    for name, family, directory in [
        ("SegFormer v1", "segmentation", "artifacts/segmentation"),
        ("SegFormer v2", "segmentation", "artifacts/segmentation/v2"),
        ("SegFormer · split comum", "segmentation", "artifacts/segmentation/common-dino-split"),
        ("DINOv2 v1", "classification", "artifacts/dinov2/v1"),
        ("DINOv2 v2-frozen", "classification", "artifacts/dinov2/v2/frozen"),
        ("DINOv2 v2-partial", "classification", "artifacts/dinov2/v2/partial")]:
        # Every displayed count is read from a frozen split, never transcribed.
        split_path = ROOT / directory / "splits.csv"
        if not split_path.exists() and family == "classification":
            split_path = ROOT / "artifacts/dinov2/v1/splits.csv"
        if split_path.exists():
            with split_path.open(encoding="utf-8-sig", newline="") as f:
                counts = Counter(row["split"] for row in csv.DictReader(f))
            split = [counts[k] for k in ("train", "validation", "test")]
            sources[str(split_path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(split_path.read_bytes()).hexdigest()
        else:
            raise FileNotFoundError(split_path)
        config_path = directory + "/training_config.json"
        config = read(config_path) if (ROOT / config_path).exists() else {}
        history_path = ROOT / directory / "training_history.csv"
        history = []
        if history_path.exists():
            with history_path.open(encoding="utf-8-sig",newline="") as f: history = list(csv.DictReader(f))
            sources[str(history_path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(history_path.read_bytes()).hexdigest()
        experiments.append({"name": name, "family": family, "directory": directory,
                            "split": split, "metrics": read(directory + "/test_metrics.json"),
                            "config": config, "history": history})
    legacy_path = ROOT / "artifacts/error-analysis/summary.csv"
    with legacy_path.open(encoding="utf-8-sig", newline="") as f:
        legacy = list(csv.DictReader(f))
    sources[str(legacy_path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(legacy_path.read_bytes()).hexdigest()
    sources["ml/functional_profile.py"] = hashlib.sha256((ROOT / "ml/functional_profile.py").read_bytes()).hexdigest()
    from ml.functional_profile import functional_spec
    return {"functional_profile": functional_spec(), "annotation_v4": workspace_schema(), "legacy": legacy, "schema": {"version": schema.version, "columns": schema.csv_columns,
                        "fields": [asdict(field) for field in schema.fields], "spatial": asdict(schema.spatial),
                        "labels": OPTION_LABELS, "groups": FIELD_GROUPS},
            "dataset": {"total": len(rows), "statuses": dict(Counter(row["circulation_path_status"] for row in rows)),
                        "subsets": dict(subsets),
                        "distributions": {field.name: dict(Counter(value for row in rows for value in
                          (json.loads(row[field.name]) if field.kind == "multilabel" else [row[field.name]]))) for field in schema.fields}},
            "experiments": experiments,
            "pipeline": read("artifacts/pipeline-evaluation/common-split-dinov2-partial/metrics.json"),
            "comparison": read("artifacts/dinov2/v2/partial/comparison_v1_common.json"),
            "sources": sources}


def main():
    output = ROOT / "frontend/src/generated/workspace.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Snapshot do Workspace gerado a partir dos artefatos locais.")


if __name__ == "__main__":
    main()
