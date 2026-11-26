from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from ml.mobility_profile import MobilityProfile


FEATURE_VALUES = {
    "passage_width": ("wide", "adequate", "narrow", "very_narrow", "blocked"),
    "obstruction": ("none", "partial", "full"),
    "surface_condition": ("regular", "minor_problem", "major_problem"),
    "level_change": ("none", "minor", "step"),
    "path_continuity": ("continuous", "restricted", "interrupted"),
}
IMPACT_RANK = {"none": 0, "moderate": 1, "critical": 2}
OBSTACLE_NAMES = {"pole": "poste", "sign": "placa", "tree": "árvore", "vegetation": "vegetação",
                  "construction": "obra", "litter_debris": "lixo ou entulho", "utility": "equipamento urbano"}
SURFACE_NAMES = {"cracks": "rachaduras", "bumpy": "piso irregular", "uneven_slanted": "piso desnivelado",
                 "height_difference": "diferença de altura", "very_broken": "piso muito quebrado",
                 "grass": "grama", "sand_gravel": "areia ou cascalho"}


@dataclass(frozen=True)
class RuleResult:
    feature: str
    observed: Any
    requirement: Any
    impact: str
    code: str
    message: str
    evaluated: bool = True


@dataclass(frozen=True)
class MobilityAssessment:
    classification: str
    severity: str
    reasons: tuple[RuleResult, ...]
    rule_results: tuple[RuleResult, ...]
    requires_review: bool


def evaluate_rule(feature: str, observed: Any, profile: MobilityProfile) -> RuleResult:
    """Avalia uma característica; listas divergentes representam evidência contraditória."""
    requirement = {
        "passage_width": profile.minimum_passage_width,
        "obstruction": profile.accepts_partial_obstruction,
        "surface_condition": profile.surface_tolerance,
        "level_change": profile.level_change_tolerance,
        "path_continuity": "continuous",
    }[feature]
    if isinstance(observed, (list, tuple)):
        if any(not isinstance(value, str) or value not in (*FEATURE_VALUES[feature], "unknown") for value in observed):
            raise ValueError(f"Observações inválidas para {feature}: {observed!r}")
        if not observed:
            observed = None
        elif len(set(observed)) == 1:
            observed = observed[0]
        else:
            return RuleResult(feature, tuple(observed), requirement, "none", f"{feature}_conflicting",
                              f"Há observações contraditórias para {feature}.", False)
    if observed is None or observed == "unknown":
        return RuleResult(feature, observed, requirement, "none", f"{feature}_unknown",
                          f"Não foi possível avaliar {feature}; a informação é necessária ao perfil.", False)
    if not isinstance(observed, str) or observed not in FEATURE_VALUES[feature]:
        raise ValueError(f"Valor inválido para {feature}: {observed!r}")

    impact, code, message = "none", f"{feature}_compatible", "Condição compatível com o perfil."
    if feature == "passage_width":
        if observed == "blocked":
            impact, code, message = "critical", "passage_blocked", "Não existe passagem contínua utilizável."
        elif FEATURE_VALUES[feature].index(observed) > FEATURE_VALUES[feature].index(requirement):
            impact, code, message = "critical", "passage_width_below_requirement", "A passagem aparenta ser mais estreita que a necessária para o perfil."
    elif feature == "obstruction":
        if observed == "full":
            impact, code, message = "critical", "obstruction_full", "A obstrução impede completamente a passagem."
        elif observed == "partial":
            impact = "moderate" if requirement else "critical"
            code = "obstruction_partial_accepted" if requirement else "obstruction_partial_incompatible"
            message = "A passagem apresenta obstrução parcial aceita pelo perfil." if requirement else "O perfil não aceita a obstrução parcial observada."
    elif feature in ("surface_condition", "level_change"):
        tolerance = (("regular_only", "minor_problems", "major_problems") if feature == "surface_condition" else FEATURE_VALUES[feature]).index(requirement)
        observed_rank = FEATURE_VALUES[feature].index(observed)
        if observed_rank:
            impact = "critical" if observed_rank > tolerance else "moderate"
            code = f"{feature}_incompatible" if impact == "critical" else f"{feature}_tolerated"
            subject = "As irregularidades do piso" if feature == "surface_condition" else "O desnível observado"
            message = f"{subject}: condição incompatível com o perfil." if impact == "critical" else f"{subject}: condição tolerada, com dificuldade moderada."
    elif feature == "path_continuity":
        if observed == "interrupted":
            impact, code, message = "critical", "path_interrupted", "A faixa de circulação está interrompida."
        elif observed == "restricted":
            impact, code, message = "moderate", "path_restricted", "A faixa de circulação apresenta restrição."
    return RuleResult(feature, observed, requirement, impact, code, message)


def aggregate_classification(results: tuple[RuleResult, ...]) -> tuple[str, str]:
    severity = max((result.impact for result in results), key=IMPACT_RANK.__getitem__)
    if severity == "critical":
        return "non_transitable", severity
    if any(not result.evaluated for result in results):
        return "undetermined", severity
    return ("partially_transitable" if severity == "moderate" else "transitable"), severity


def generate_reasons(results: tuple[RuleResult, ...], features: Mapping) -> tuple[RuleResult, ...]:
    reasons = []
    for result in results:
        if result.impact == "none" and result.evaluated:
            continue
        names = None
        if result.feature == "obstruction":
            names = ("obstacle_type", OBSTACLE_NAMES)
        elif result.feature == "surface_condition":
            names = ("surface_obstacle", SURFACE_NAMES)
        if names and result.evaluated:
            values = features.get(names[0], ())
            if not isinstance(values, (list, tuple)):
                raise ValueError(f"{names[0]} deve ser uma lista de labels")
            details = list(dict.fromkeys(names[1][value] for value in values if value in names[1]))
            if details:
                result = replace(result, message=result.message + " Características observadas: " + ", ".join(details) + ".")
        reasons.append(result)
    return tuple(sorted(reasons, key=lambda result: -IMPACT_RANK[result.impact]))


def assess_transitability(features: Mapping[str, Any], profile: MobilityProfile) -> MobilityAssessment:
    """Classifica somente pelas cinco heads categóricas do DINO atual."""
    results = tuple(evaluate_rule(feature, features.get(feature), profile) for feature in FEATURE_VALUES)
    # Uma barreira crítica observada continua decisiva mesmo quando há conflito entre heads.
    conflicting = ((features.get("obstruction") == "full" or features.get("passage_width") == "blocked")
                   and features.get("path_continuity") == "continuous")
    if conflicting:
        results += (RuleResult("path_continuity", features.get("path_continuity"), "consistent_evidence", "none",
                               "continuity_conflicts_with_blockage", "A continuidade informada contradiz a passagem bloqueada ou a obstrução total.", False),)
    classification, severity = aggregate_classification(results)
    return MobilityAssessment(classification, severity, generate_reasons(results, features), results,
                              any(not result.evaluated for result in results))
