from collections.abc import Iterable
from dataclasses import dataclass

from ml.data.obstacles import TARGET_LABELS

@dataclass(frozen=True)
class TransitabilityResult:
    classification: str
    detected_features: tuple[str, ...]
    justification: str


FEATURE_RULES: dict[str, tuple[str, str]] = {
    "construction": ("obra", "alto"),
    "height-difference": ("desnível", "alto"),
    "parked-car": ("veículo estacionado", "moderado"),
    "pole": ("poste", "moderado"),
    "trash-recycling-can": ("lixeira ou recipiente de reciclagem", "moderado"),
    "tree": ("árvore", "baixo"),
    "vegetation": ("vegetação", "baixo"),
}

CLASSIFICATION_BY_IMPACT = {
    "baixo": "Transitável",
    "moderado": "Parcialmente transitável",
    "alto": "Não transitável",
}
IMPACT_RANK = {"baixo": 1, "moderado": 2, "alto": 3}


class UnknownFeatureError(ValueError):
    pass


def _format_feature_list(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} e {names[-1]}"


def classify_transitability(
    detected_features: Iterable[str],
) -> TransitabilityResult:
    """Classifica o trecho pelo maior impacto entre as características detectadas."""
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

    maximum_impact = max(
        (FEATURE_RULES[feature][1] for feature in features),
        key=IMPACT_RANK.__getitem__,
    )
    friendly_names = [FEATURE_RULES[feature][0] for feature in features]
    formatted_names = _format_feature_list(friendly_names)

    return TransitabilityResult(
        classification=CLASSIFICATION_BY_IMPACT[maximum_impact],
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
