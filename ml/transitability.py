from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum

from ml.data.obstacles import TARGET_LABELS


class Impact(IntEnum):
    BAIXO = 1
    MODERADO = 2
    ALTO = 3


@dataclass(frozen=True)
class FeatureRule:
    display_name: str
    impact: Impact


@dataclass(frozen=True)
class TransitabilityResult:
    classification: str
    detected_features: tuple[str, ...]
    justification: str


# Configuração única das características consideradas pelo MVP0.
FEATURE_RULES: dict[str, FeatureRule] = {
    "construction": FeatureRule("obra", Impact.ALTO),
    "height-difference": FeatureRule("desnível", Impact.ALTO),
    "parked-car": FeatureRule("veículo estacionado", Impact.MODERADO),
    "pole": FeatureRule("poste", Impact.MODERADO),
    "trash-recycling-can": FeatureRule(
        "lixeira ou recipiente de reciclagem",
        Impact.MODERADO,
    ),
    "tree": FeatureRule("árvore", Impact.BAIXO),
    "vegetation": FeatureRule("vegetação", Impact.BAIXO),
}

CLASSIFICATION_BY_MAX_IMPACT: dict[Impact, str] = {
    Impact.BAIXO: "Transitável",
    Impact.MODERADO: "Parcialmente transitável",
    Impact.ALTO: "Não transitável",
}


class UnknownFeatureError(ValueError):
    """Raised when transitability receives a feature outside the MVP0 labels."""


def _format_feature_list(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} e {names[-1]}"


def classify_transitability(
    detected_features: Iterable[str],
) -> TransitabilityResult:
    """Classify transitability from detected features and their maximum impact."""
    features = tuple(dict.fromkeys(detected_features))
    unknown_features = tuple(
        feature for feature in features if feature not in FEATURE_RULES
    )
    if unknown_features:
        unknown_list = ", ".join(unknown_features)
        raise UnknownFeatureError(
            f"Características desconhecidas para o MVP0: {unknown_list}."
        )

    if not features:
        return TransitabilityResult(
            classification="Transitável",
            detected_features=(),
            justification=(
                "Não foram identificadas barreiras consideradas pelo MVP0."
            ),
        )

    maximum_impact = max(FEATURE_RULES[feature].impact for feature in features)
    friendly_names = [FEATURE_RULES[feature].display_name for feature in features]
    formatted_names = _format_feature_list(friendly_names)

    return TransitabilityResult(
        classification=CLASSIFICATION_BY_MAX_IMPACT[maximum_impact],
        detected_features=features,
        justification=(
            "Foram identificadas as seguintes características no trecho: "
            f"{formatted_names}."
        ),
    )


if tuple(FEATURE_RULES) != TARGET_LABELS:
    raise RuntimeError(
        "A configuração de transitabilidade deve seguir exatamente TARGET_LABELS."
    )
