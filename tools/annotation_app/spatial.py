"""Adaptação isolada entre Fabric.js e a geometria oficial normalizada."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from tools.annotation_app.core import AnnotationValidationError, validate_circulation_path


ORIGIN_OFFSET = {
    "left": 0.0,
    "top": 0.0,
    "center": 0.5,
    "right": 1.0,
    "bottom": 1.0,
}


def fit_canvas_size(
    image_width: int,
    image_height: int,
    *,
    max_width: int = 760,
    max_height: int = 620,
) -> tuple[int, int]:
    """Ajusta a imagem à viewport preservando rigorosamente o aspect ratio."""

    if image_width <= 0 or image_height <= 0:
        raise ValueError("Dimensões da imagem devem ser positivas")
    scale = min(max_width / image_width, max_height / image_height, 1.0)
    return max(1, round(image_width * scale)), max(1, round(image_height * scale))


def circulation_path_to_fabric_json(
    polygons: Any,
    canvas_width: int,
    canvas_height: int,
) -> dict[str, list[dict[str, Any]]]:
    """Reprojeta geometria normalizada para objetos Polygon editáveis."""

    normalized = validate_circulation_path(polygons)
    objects: list[dict[str, Any]] = []
    for polygon in normalized:
        points = [
            {"x": x * canvas_width, "y": y * canvas_height}
            for x, y in polygon
        ]
        xs = [point["x"] for point in points]
        ys = [point["y"] for point in points]
        center_x = (min(xs) + max(xs)) / 2
        center_y = (min(ys) + max(ys)) / 2
        objects.append(
            {
                "type": "Polygon",
                "version": "7.0.0",
                "originX": "center",
                "originY": "center",
                "left": center_x,
                "top": center_y,
                "width": max(xs) - min(xs),
                "height": max(ys) - min(ys),
                "fill": "rgba(0, 174, 239, 0.22)",
                "stroke": "#00AEEF",
                "strokeWidth": 3,
                "strokeUniform": True,
                "scaleX": 1,
                "scaleY": 1,
                "angle": 0,
                "flipX": False,
                "flipY": False,
                "skewX": 0,
                "skewY": 0,
                "points": points,
                "pathOffset": {"x": center_x, "y": center_y},
            }
        )
    return {"objects": objects}


def _number(value: Any, context: str, default: float | None = None) -> float:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnnotationValidationError(f"{context} deve ser numérico")
    result = float(value)
    if not math.isfinite(result):
        raise AnnotationValidationError(f"{context} deve ser finito")
    return result


def _fabric_point_to_canvas(
    point: Mapping[str, Any],
    obj: Mapping[str, Any],
) -> tuple[float, float]:
    path_offset = obj.get("pathOffset")
    if path_offset is None:
        # Fabric 7 omite pathOffset na serialização de Polygon. O valor
        # implícito é o centro da bounding box dos pontos originais.
        raw_points = obj.get("points", ())
        point_xs = [
            _number(item.get("x"), "point.x")
            for item in raw_points
            if isinstance(item, Mapping)
        ]
        point_ys = [
            _number(item.get("y"), "point.y")
            for item in raw_points
            if isinstance(item, Mapping)
        ]
        if not point_xs or len(point_xs) != len(raw_points):
            raise AnnotationValidationError("Polygon Fabric.js sem points válidos")
        path_offset = {
            "x": (min(point_xs) + max(point_xs)) / 2,
            "y": (min(point_ys) + max(point_ys)) / 2,
        }
    local_x = _number(point.get("x"), "point.x") - _number(
        path_offset.get("x"), "pathOffset.x", 0
    )
    local_y = _number(point.get("y"), "point.y") - _number(
        path_offset.get("y"), "pathOffset.y", 0
    )
    scale_x = _number(obj.get("scaleX"), "scaleX", 1) * (
        -1 if obj.get("flipX") else 1
    )
    scale_y = _number(obj.get("scaleY"), "scaleY", 1) * (
        -1 if obj.get("flipY") else 1
    )
    scaled_x = local_x * scale_x
    scaled_y = local_y * scale_y
    skew_x = math.tan(math.radians(_number(obj.get("skewX"), "skewX", 0)))
    skew_y = math.tan(math.radians(_number(obj.get("skewY"), "skewY", 0)))
    transformed_x = scaled_x + skew_x * scaled_y
    transformed_y = scaled_y + skew_y * scaled_x

    width = _number(obj.get("width"), "width", 0) * abs(scale_x)
    height = _number(obj.get("height"), "height", 0) * abs(scale_y)
    origin_x = ORIGIN_OFFSET.get(str(obj.get("originX", "left")))
    origin_y = ORIGIN_OFFSET.get(str(obj.get("originY", "top")))
    if origin_x is None or origin_y is None:
        raise AnnotationValidationError("Origem Fabric.js desconhecida")
    center_offset_x = (0.5 - origin_x) * width
    center_offset_y = (0.5 - origin_y) * height
    angle = math.radians(_number(obj.get("angle"), "angle", 0))
    cos_angle, sin_angle = math.cos(angle), math.sin(angle)
    center_x = _number(obj.get("left"), "left", 0) + (
        center_offset_x * cos_angle - center_offset_y * sin_angle
    )
    center_y = _number(obj.get("top"), "top", 0) + (
        center_offset_x * sin_angle + center_offset_y * cos_angle
    )
    return (
        center_x + transformed_x * cos_angle - transformed_y * sin_angle,
        center_y + transformed_x * sin_angle + transformed_y * cos_angle,
    )


def fabric_json_to_circulation_path(
    drawing: Mapping[str, Any] | None,
    canvas_width: int,
    canvas_height: int,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Extrai polígonos Fabric.js e normaliza no espaço da imagem original."""

    if canvas_width <= 0 or canvas_height <= 0:
        raise AnnotationValidationError("Dimensões do canvas devem ser positivas")
    if drawing is None:
        return ()
    objects = drawing.get("objects", [])
    if isinstance(objects, (str, bytes)) or not isinstance(objects, Sequence):
        raise AnnotationValidationError("JSON do canvas possui objects inválido")
    polygons: list[list[list[float]]] = []
    for obj in objects:
        if not isinstance(obj, Mapping):
            raise AnnotationValidationError("Objeto inválido no canvas")
        if str(obj.get("type", "")).casefold() != "polygon":
            continue
        points = obj.get("points")
        if isinstance(points, (str, bytes)) or not isinstance(points, Sequence):
            raise AnnotationValidationError("Polygon Fabric.js sem points válidos")
        polygon: list[list[float]] = []
        for point in points:
            if not isinstance(point, Mapping):
                raise AnnotationValidationError("Ponto Fabric.js inválido")
            canvas_x, canvas_y = _fabric_point_to_canvas(point, obj)
            polygon.append(
                [
                    round(canvas_x / canvas_width, 8),
                    round(canvas_y / canvas_height, 8),
                ]
            )
        polygons.append(polygon)
    return validate_circulation_path(polygons)
