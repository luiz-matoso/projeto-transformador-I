from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CoherenceWarning:
    code: str
    message: str


SURFACE_PROBLEMS_INCOMPATIBLE_WITH_REGULAR = frozenset(
    {"cracks", "bumpy", "uneven_slanted", "very_broken", "pooled_water", "debris"}
)


def _selected(value: Any) -> set[str]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return set()
    return {item for item in value if isinstance(item, str)}


def find_coherence_warnings(values: Mapping[str, Any]) -> tuple[CoherenceWarning, ...]:
    """Retorna combinações suspeitas sem impedir que a anotação seja salva."""

    warnings: list[CoherenceWarning] = []
    obstacles = _selected(values.get("obstacle_type"))
    surface_problems = _selected(values.get("surface_obstacle"))

    if values.get("obstruction") == "none" and obstacles:
        warnings.append(
            CoherenceWarning(
                "obstruction_none_with_obstacles",
                "Você marcou ausência de obstrução, mas existem obstáculos relevantes selecionados.",
            )
        )
    if values.get("obstruction") == "full" and values.get("path_continuity") == "continuous":
        warnings.append(
            CoherenceWarning(
                "full_obstruction_with_continuous_path",
                "Obstrução total normalmente não é compatível com rota contínua.",
            )
        )
    if values.get("passage_width") == "blocked" and values.get("path_continuity") == "continuous":
        warnings.append(
            CoherenceWarning(
                "blocked_width_with_continuous_path",
                "Passagem bloqueada normalmente não é compatível com rota contínua.",
            )
        )
    if values.get("curb_access") == "raised_no_ramp" and values.get("ramp_condition") == "not_applicable":
        warnings.append(
            CoherenceWarning(
                "raised_curb_without_ramp_assessment",
                "Há meio-fio elevado sem rampa; revise se a condição deveria ser 'rampa necessária ausente'.",
            )
        )
    if values.get("curb_access") == "ramp" and values.get("ramp_condition") == "not_applicable":
        warnings.append(
            CoherenceWarning(
                "ramp_with_not_applicable_condition",
                "Há uma rampa marcada, mas sua condição está como não aplicável.",
            )
        )
    if (
        values.get("surface_condition") == "regular"
        and surface_problems & SURFACE_PROBLEMS_INCOMPATIBLE_WITH_REGULAR
    ):
        warnings.append(
            CoherenceWarning(
                "regular_surface_with_problem",
                "Há problema de superfície marcado, mas a condição geral está como regular.",
            )
        )
    return tuple(warnings)
