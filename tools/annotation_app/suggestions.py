from collections.abc import Sequence
from typing import Any


MANUAL_ORIGIN = "manual"
ACCEPTED_ORIGIN = "segformer_v1_accepted"
CORRECTED_ORIGIN = "segformer_v1_corrected"
VALID_ORIGINS = (MANUAL_ORIGIN, ACCEPTED_ORIGIN, CORRECTED_ORIGIN)


def annotation_state(annotation_key: str, annotations: dict[str, Any]) -> str:
    return "annotated" if annotation_key in annotations else "pending"


def polygons_are_close(
    first: Sequence[Sequence[Sequence[float]]],
    second: Sequence[Sequence[Sequence[float]]],
    *,
    tolerance: float = 1e-6,
) -> bool:
    if len(first) != len(second):
        return False
    return all(
        len(first_polygon) == len(second_polygon)
        and all(
            len(first_point) == 2
            and len(second_point) == 2
            and abs(float(first_point[0]) - float(second_point[0])) <= tolerance
            and abs(float(first_point[1]) - float(second_point[1])) <= tolerance
            for first_point, second_point in zip(first_polygon, second_polygon)
        )
        for first_polygon, second_polygon in zip(first, second)
    )


def annotation_origin(
    geometry: Sequence[Sequence[Sequence[float]]],
    suggestion: Sequence[Sequence[Sequence[float]]] | None,
    *,
    existing_origin: str | None = None,
) -> str:
    """Classifica a contribuição do modelo sem marcar nada como humano antes do save."""

    if suggestion is None:
        return existing_origin if existing_origin in VALID_ORIGINS else MANUAL_ORIGIN
    return ACCEPTED_ORIGIN if polygons_are_close(geometry, suggestion) else CORRECTED_ORIGIN


def should_offer_suggestion(
    existing: dict[str, Any] | None,
    *,
    is_editing: bool,
) -> bool:
    """Anotação salva só recebe sugestão após ação explícita de editar."""

    return existing is None or is_editing
