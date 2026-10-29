"""Leitura, validação, rasterização e split do dataset de segmentação."""

from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import torch
from PIL import Image, ImageDraw, ImageEnhance
from torch.utils.data import Dataset


@dataclass(frozen=True)
class SegmentationRecord:
    filename: str
    local_filename: str
    image_path: Path
    subset: str
    panorama_id: str
    polygons: tuple[tuple[tuple[float, float], ...], ...]
    image_width: int
    image_height: int


@dataclass(frozen=True)
class DatasetQaIssue:
    filename: str
    code: str
    message: str


def normalized_point_to_pixel(
    point: Sequence[float], width: int, height: int
) -> tuple[int, int]:
    """Converte uma coordenada normalizada em pixel, incluindo as bordas."""

    if width <= 0 or height <= 0:
        raise ValueError("Dimensões da imagem devem ser positivas")
    if len(point) != 2:
        raise ValueError("Cada vértice deve conter x e y")
    x, y = float(point[0]), float(point[1])
    if not math.isfinite(x) or not math.isfinite(y) or not (0 <= x <= 1 and 0 <= y <= 1):
        raise ValueError("Coordenadas normalizadas devem estar em [0, 1]")
    return round(x * (width - 1)), round(y * (height - 1))


def parse_polygons(value: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Valida o JSON humano sem corrigir ou alterar a geometria."""

    try:
        raw = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("circulation_path não contém JSON válido") from error
    if not isinstance(raw, list) or not raw:
        raise ValueError("circulation_path deve conter ao menos um polígono")
    polygons: list[tuple[tuple[float, float], ...]] = []
    for polygon_index, polygon in enumerate(raw):
        if not isinstance(polygon, list) or len(polygon) < 3:
            raise ValueError(f"polígono {polygon_index} deve ter ao menos 3 pontos")
        points: list[tuple[float, float]] = []
        for point in polygon:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"vértice inválido no polígono {polygon_index}")
            x, y = point
            if isinstance(x, bool) or isinstance(y, bool):
                raise ValueError("coordenada booleana é inválida")
            try:
                normalized = float(x), float(y)
            except (TypeError, ValueError) as error:
                raise ValueError("coordenadas devem ser numéricas") from error
            if not all(math.isfinite(item) and 0 <= item <= 1 for item in normalized):
                raise ValueError("coordenadas normalizadas devem estar em [0, 1]")
            points.append(normalized)
        polygons.append(tuple(points))
    return tuple(polygons)


def rasterize_polygons(
    polygons: Sequence[Sequence[Sequence[float]]], width: int, height: int
) -> Image.Image:
    """Rasteriza os polígonos em uma máscara PIL binária 0/1."""

    mask = Image.new("L", (width, height), 0)
    drawer = ImageDraw.Draw(mask)
    for polygon in polygons:
        if len(polygon) < 3:
            raise ValueError("Cada polígono deve ter ao menos 3 pontos")
        pixels = [normalized_point_to_pixel(point, width, height) for point in polygon]
        drawer.polygon(pixels, fill=1)
    return mask


def resize_binary_mask(mask: Image.Image, size: tuple[int, int]) -> Image.Image:
    resized = mask.resize(size, Image.Resampling.NEAREST)
    values = set(resized.tobytes())
    if not values <= {0, 1}:
        raise ValueError(f"Máscara deixou de ser binária após resize: {sorted(values)}")
    return resized


def _manifest_index(manifest_path: Path) -> dict[str, dict[str, str]]:
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row.get("annotation_filename", "")
        if not key or key in index:
            raise ValueError(f"annotation_filename ausente ou duplicado no manifesto: {key!r}")
        index[key] = row
    return index


def audit_segmentation_annotations(
    annotations_csv: str | Path,
    pilot_root: str | Path,
) -> tuple[list[SegmentationRecord], list[DatasetQaIssue]]:
    """Audita todas as linhas e devolve somente registros estruturalmente válidos."""

    csv_path = Path(annotations_csv)
    root = Path(pilot_root)
    manifest = _manifest_index(root / "pilot_manifest.csv")
    images_root = root / "images"
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    issues: list[DatasetQaIssue] = []
    records: list[SegmentationRecord] = []
    filenames = [row.get("filename", "") for row in rows]
    duplicates = {name for name, count in Counter(filenames).items() if count > 1}
    for row_number, row in enumerate(rows, start=2):
        filename = row.get("filename", "").strip()

        def issue(code: str, message: str) -> None:
            issues.append(DatasetQaIssue(filename or f"linha {row_number}", code, message))

        if not filename:
            issue("missing_filename", "filename vazio")
            continue
        if filename in duplicates:
            issue("duplicate_filename", "filename/chave duplicada no CSV")
            continue
        metadata = manifest.get(filename)
        if metadata is None:
            issue("missing_manifest_entry", "imagem não encontrada no manifesto do piloto")
            continue
        if row.get("circulation_path_status") != "annotated":
            issue(
                "status_not_annotated",
                f"circulation_path_status={row.get('circulation_path_status')!r}; esperado 'annotated'",
            )
            continue
        try:
            polygons = parse_polygons(row.get("circulation_path", ""))
        except ValueError as error:
            issue("invalid_polygon", str(error))
            continue
        try:
            declared_width = int(row.get("image_width", ""))
            declared_height = int(row.get("image_height", ""))
            if declared_width <= 0 or declared_height <= 0:
                raise ValueError
        except ValueError:
            issue("invalid_dimensions", "image_width/image_height devem ser inteiros positivos")
            continue
        local_filename = metadata["local_filename"].replace("\\", "/")
        relative_path = PurePosixPath(local_filename)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            issue("invalid_local_filename", "local_filename inseguro no manifesto")
            continue
        image_path = images_root.joinpath(*relative_path.parts)
        if not image_path.is_file():
            issue("missing_image", f"imagem não encontrada: {image_path}")
            continue
        try:
            with Image.open(image_path) as image:
                actual_width, actual_height = image.size
                image.verify()
        except OSError as error:
            issue("invalid_image", f"arquivo de imagem inválido: {error}")
            continue
        if (actual_width, actual_height) != (declared_width, declared_height):
            issue(
                "dimension_mismatch",
                f"CSV={declared_width}x{declared_height}; imagem={actual_width}x{actual_height}",
            )
            continue
        records.append(
            SegmentationRecord(
                filename=filename,
                local_filename=local_filename,
                image_path=image_path,
                subset=metadata["subset"],
                panorama_id=metadata["panorama_id"],
                polygons=polygons,
                image_width=declared_width,
                image_height=declared_height,
            )
        )
    return records, issues


def _split_targets(total: int) -> dict[str, int]:
    if total != 105:
        raise ValueError(f"O split congelado exige 105 registros válidos; encontrados {total}")
    return {"train": 75, "validation": 15, "test": 15}


def create_grouped_split(
    records: Sequence[SegmentationRecord], seed: int = 42
) -> dict[str, str]:
    """Cria split determinístico, aproximando subset e mantendo panoramas unidos."""

    targets = _split_targets(len(records))
    groups: dict[str, list[SegmentationRecord]] = defaultdict(list)
    for record in records:
        groups[record.panorama_id].append(record)
    rng = random.Random(seed)
    group_items = list(groups.items())
    rng.shuffle(group_items)
    group_items.sort(key=lambda item: len(item[1]), reverse=True)
    global_subset = Counter(record.subset for record in records)
    assignments: dict[str, str] = {}
    counts = Counter()
    subset_counts: dict[str, Counter[str]] = defaultdict(Counter)
    split_order = ("train", "validation", "test")
    for _, group in group_items:
        group_size = len(group)
        group_subsets = Counter(record.subset for record in group)
        candidates = [split for split in split_order if counts[split] + group_size <= targets[split]]
        if not candidates:
            raise ValueError("Grupos de panorama não permitem atingir o split exato 75/15/15")

        def score(split: str) -> tuple[float, int]:
            capacity_need = (targets[split] - counts[split]) / targets[split]
            subset_need = sum(
                max(0.0, global_subset[subset] * targets[split] / len(records) - subset_counts[split][subset])
                * amount
                for subset, amount in group_subsets.items()
            )
            return subset_need + capacity_need, -split_order.index(split)

        chosen = max(candidates, key=score)
        for record in group:
            assignments[record.filename] = chosen
        counts[chosen] += group_size
        subset_counts[chosen].update(group_subsets)
    if counts != Counter(targets):
        raise ValueError(f"Split incorreto: {dict(counts)}")
    return assignments


class CirculationPathDataset(Dataset):
    """Dataset que aplica transformações geométricas idênticas à imagem e máscara."""

    def __init__(
        self,
        records: Sequence[SegmentationRecord],
        *,
        image_processor: Any | None = None,
        image_size: int = 512,
        augment: bool = False,
    ) -> None:
        self.records = tuple(records)
        self.image_processor = image_processor
        self.image_size = image_size
        self.augment = augment

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.records[index]
        with Image.open(record.image_path) as source:
            image = source.convert("RGB")
        mask = rasterize_polygons(record.polygons, record.image_width, record.image_height)
        image = image.resize((self.image_size, self.image_size), Image.Resampling.BILINEAR)
        mask = resize_binary_mask(mask, (self.image_size, self.image_size))
        if self.augment and torch.rand(()) < 0.5:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            mask = mask.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if self.augment:
            image = ImageEnhance.Brightness(image).enhance(float(torch.empty(1).uniform_(0.9, 1.1)))
            image = ImageEnhance.Contrast(image).enhance(float(torch.empty(1).uniform_(0.9, 1.1)))
            image = ImageEnhance.Color(image).enhance(float(torch.empty(1).uniform_(0.9, 1.1)))
        if self.image_processor is not None:
            pixel_values = self.image_processor(images=image, return_tensors="pt", do_resize=False)["pixel_values"].squeeze(0)
        else:
            array = torch.frombuffer(bytearray(image.tobytes()), dtype=torch.uint8)
            pixel_values = array.view(self.image_size, self.image_size, 3).permute(2, 0, 1).float() / 255.0
        labels = torch.frombuffer(bytearray(mask.tobytes()), dtype=torch.uint8).long().view(self.image_size, self.image_size)
        if not set(torch.unique(labels).tolist()) <= {0, 1}:
            raise RuntimeError("Máscara do Dataset não é binária")
        return {"pixel_values": pixel_values, "labels": labels, "filename": record.filename}

