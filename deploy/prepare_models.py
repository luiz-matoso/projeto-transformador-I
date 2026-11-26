import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / ".modal-models"


def main():
    from transformers import AutoConfig

    if DESTINATION.exists():
        raise SystemExit(f"Destino já existe; revise antes de gerar outro pacote: {DESTINATION}")
    sources = {
        "segformer/best_segformer.pt": ROOT / "artifacts/segmentation/common-dino-split/best_segformer.pt",
        "segformer/image_processor/preprocessor_config.json": ROOT / "artifacts/segmentation/common-dino-split/image_processor/preprocessor_config.json",
        "dinov2/best_dinov2_v2.pt": ROOT / "artifacts/dinov2/v2/partial/best_dinov2_v2.pt",
        "dinov2/image_processor/preprocessor_config.json": ROOT / "artifacts/dinov2/v2/partial/image_processor/preprocessor_config.json",
    }
    for path in sources.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    # Só a arquitetura é necessária: os pesos completos já estão no checkpoint partial.
    config = AutoConfig.from_pretrained("facebook/dinov2-base", local_files_only=True)
    for target, source in sources.items():
        destination = DESTINATION / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    config.save_pretrained(DESTINATION / "dinov2/backbone_config")
    files = sorted(p for p in DESTINATION.rglob("*") if p.is_file())
    manifest = {str(p.relative_to(DESTINATION)).replace("\\", "/"): {"bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}
    (DESTINATION / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
