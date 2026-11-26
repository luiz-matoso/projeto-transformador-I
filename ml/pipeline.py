from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timedelta

import torch
from PIL import Image

from ml.dinov2 import CATEGORICAL_HEADS, MULTILABEL_HEADS
from ml.dinov2.dataset import emphasize_circulation_mask
from ml.dinov2.predict import predict_image
from ml.dinov2.train_v2 import load_checkpoint
from ml.mobility_profile import MobilityProfile
from ml.mobility_rules import assess_transitability
from ml.observation import DEFAULT_VALIDITY_PERIOD, evaluate_observation
from ml.segmentation.predict import load_segformer_predictor, predict_circulation_path


SEGFORMER_CHECKPOINT = Path("artifacts/segmentation/common-dino-split/best_segformer.pt")
DINO_CHECKPOINT = Path("artifacts/dinov2/v2/partial/best_dinov2_v2.pt")
INACTIVE_FEATURES = ("slope", "ramp_condition", "curb_access", "detour")


@lru_cache(maxsize=1)
def _load_components():
    from transformers import AutoImageProcessor

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    segmenter = load_segformer_predictor(SEGFORMER_CHECKPOINT, device=device)
    model, checkpoint = load_checkpoint(DINO_CHECKPOINT, device=device)
    model.eval()
    processor = AutoImageProcessor.from_pretrained(DINO_CHECKPOINT.parent / "image_processor", local_files_only=True)
    # A avaliação congelada da v2 utiliza 0.5; não há thresholds calibrados nesse checkpoint.
    thresholds = {head: (0.5,) * len(model.classes[head]) for head in MULTILABEL_HEADS}
    return segmenter, model, processor, thresholds, device, checkpoint["config"]["excluded_targets"]


def observe_scene(image_path: str | Path, *, observation: dict | None = None) -> dict:
    """Executa a percepção uma vez, permitindo reaplicar perfis à mesma cena."""
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    segmenter, model, processor, thresholds, device, excluded = _load_components()
    suggestion = predict_circulation_path(segmenter, image)
    focused = emphasize_circulation_mask(image, Image.fromarray(suggestion.mask * 255))
    predictions = predict_image(model, processor, model.classes, thresholds, device, focused)
    features = {head: predictions[head]["prediction"] for head in CATEGORICAL_HEADS if head in predictions}
    features.update({head: predictions[head]["predictions"] for head in MULTILABEL_HEADS if head in predictions})
    return {"image_path": str(image_path), "mask": suggestion.mask, "features": features,
            "predictions": predictions, "not_modeled": excluded,
            "inactive_features": list(INACTIVE_FEATURES), "observation": observation}


def apply_profile(scene: dict, profile: MobilityProfile, *, validity_period: timedelta = DEFAULT_VALIDITY_PERIOD,
                  evaluated_at: datetime | None = None) -> dict:
    temporal = evaluate_observation(scene.get("observation"), validity_period=validity_period, evaluated_at=evaluated_at)
    if not temporal["is_valid"]:
        reason = {"feature": "observation", "observed": temporal["observed_at"],
                  "requirement": "valid_observation", "impact": "none", "code": temporal["code"],
                  "message": temporal["message"], "evaluated": False}
        return {**scene, "observation": temporal, "profile": asdict(profile), "classification": "undetermined",
                "severity": "none", "reasons": [reason], "rule_results": [], "requires_review": True,
                "unassessed_features": list(CATEGORICAL_HEADS)}
    assessment = assess_transitability(scene["features"], profile)
    return {**scene, "observation": temporal, "profile": asdict(profile), **asdict(assessment),
            "unassessed_features": list(dict.fromkeys(result.feature for result in assessment.rule_results if not result.evaluated))}


def infer_transitability(image_path: str | Path, profile: MobilityProfile, *, observation: dict | None = None,
                        validity_period: timedelta = DEFAULT_VALIDITY_PERIOD, evaluated_at: datetime | None = None) -> dict:
    """Retorna percepção e decisão funcional com os checkpoints atuais cacheados."""
    return apply_profile(observe_scene(image_path, observation=observation), profile,
                         validity_period=validity_period, evaluated_at=evaluated_at)
