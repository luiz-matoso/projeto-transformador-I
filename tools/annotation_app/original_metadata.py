"""Leitura dos metadados originais associados ao piloto de anotação."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

from tools.annotation_app.core import normalize_filename


REQUIRED_MANIFEST_COLUMNS = (
    "local_filename",
    "original_filename",
    "subset",
    "original_split",
    "original_labels",
    "normalized_x",
    "normalized_y",
    "source",
    "source_member",
    "panorama_id",
    "city",
    "selected_seed",
    "annotation_status",
    "annotation_filename",
)


@dataclass(frozen=True)
class OriginalMetadata:
    local_filename: str
    original_filename: str
    subset: str
    original_split: str
    original_labels: tuple[str, ...]
    normalized_x: float
    normalized_y: float
    source: str
    source_member: str
    panorama_id: str
    city: str
    selected_seed: int
    annotation_status: str
    annotation_filename: str


def find_pilot_manifest(image_root: str | Path) -> Path | None:
    root = Path(image_root)
    for candidate in (root / "pilot_manifest.csv", root.parent / "pilot_manifest.csv"):
        if candidate.is_file():
            return candidate
    return None


def _coordinate(value: str, field: str) -> float:
    try:
        coordinate = float(value)
    except ValueError as error:
        raise ValueError(f"{field} inválido no manifesto: {value!r}") from error
    if not math.isfinite(coordinate) or not 0.0 <= coordinate <= 1.0:
        raise ValueError(f"{field} deve estar entre 0 e 1")
    return coordinate


def load_pilot_manifest(
    path: str | Path,
    image_root: str | Path,
) -> dict[str, OriginalMetadata]:
    """Lê e valida o manifesto, indexado pelo caminho relativo da imagem."""

    manifest_path = Path(path)
    root = Path(image_root)
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REQUIRED_MANIFEST_COLUMNS:
            raise ValueError("Cabeçalho incompatível no pilot_manifest.csv")
        result: dict[str, OriginalMetadata] = {}
        for row_number, row in enumerate(reader, start=2):
            local_filename = normalize_filename(row["local_filename"])
            if local_filename in result:
                raise ValueError(f"local_filename duplicado na linha {row_number}: {local_filename}")
            try:
                raw_labels = json.loads(row["original_labels"])
            except json.JSONDecodeError as error:
                raise ValueError(f"original_labels inválido na linha {row_number}") from error
            if not isinstance(raw_labels, list) or any(not isinstance(label, str) for label in raw_labels):
                raise ValueError(f"original_labels deve ser uma lista textual na linha {row_number}")
            if row["annotation_status"] not in {"annotated", "pending"}:
                raise ValueError(f"annotation_status inválido na linha {row_number}")
            image_path = root.joinpath(*local_filename.split("/"))
            if not image_path.is_file():
                raise ValueError(f"Imagem do manifesto não encontrada: {image_path}")
            metadata = OriginalMetadata(
                local_filename=local_filename,
                original_filename=normalize_filename(row["original_filename"]),
                subset=row["subset"].strip(),
                original_split=row["original_split"].strip(),
                original_labels=tuple(raw_labels),
                normalized_x=_coordinate(row["normalized_x"], "normalized_x"),
                normalized_y=_coordinate(row["normalized_y"], "normalized_y"),
                source=row["source"].strip(),
                source_member=row["source_member"].strip(),
                panorama_id=row["panorama_id"].strip(),
                city=row["city"].strip(),
                selected_seed=int(row["selected_seed"]),
                annotation_status=row["annotation_status"],
                annotation_filename=normalize_filename(row["annotation_filename"]),
            )
            result[local_filename] = metadata
    return result
