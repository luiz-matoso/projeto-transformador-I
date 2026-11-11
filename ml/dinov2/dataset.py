import csv
import json
import random
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import torch
import yaml
from PIL import Image, ImageEnhance, ImageFilter
from torch.utils.data import Dataset

from ml.dinov2 import ALL_HEADS, CATEGORICAL_HEADS, MULTILABEL_HEADS
from ml.segmentation.dataset import parse_polygons, rasterize_polygons


@dataclass(frozen=True)
class DinoRecord:
    filename: str
    image_path: Path
    subset: str
    panorama_id: str
    polygons: tuple[tuple[tuple[float, float], ...], ...]
    image_width: int
    image_height: int
    categorical: Mapping[str, str | None]
    multilabel: Mapping[str, tuple[str, ...]]

    def stratification_features(self) -> tuple[str, ...]:
        features: list[str] = []
        for head in CATEGORICAL_HEADS:
            value = self.categorical[head]
            if value is not None:
                features.append(f"{head}={value}")
        for head in MULTILABEL_HEADS:
            values = self.multilabel[head]
            features.extend(f"{head}={value}" for value in values)
            if not values:
                features.append(f"{head}=<empty>")
        features.append(f"subset={self.subset}")
        return tuple(features)


def load_head_classes(schema_path: str | Path) -> dict[str, tuple[str, ...]]:
    with Path(schema_path).open("r", encoding="utf-8") as handle:
        schema = yaml.safe_load(handle)
    labels = schema.get("labels", {})
    result: dict[str, tuple[str, ...]] = {}
    for head in ALL_HEADS:
        options = labels.get(head, {}).get("options", [])
        values = tuple(option["value"] for option in options)
        if not values:
            raise ValueError(f"Head ausente ou sem classes no schema: {head}")
        result[head] = (
            tuple(value for value in values if value != "unknown")
            if head in CATEGORICAL_HEADS
            else values
        )
    return result


def _manifest_index(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row.get("annotation_filename", "")
        if not key or key in index:
            raise ValueError(f"annotation_filename ausente ou duplicado: {key!r}")
        index[key] = row
    return index


def load_dinov2_records(
    annotations_csv: str | Path,
    pilot_root: str | Path,
    schema_path: str | Path,
) -> tuple[list[DinoRecord], dict[str, tuple[str, ...]], Counter[str]]:
    """Lê apenas circulation_path humana válida, sem alterar o CSV."""

    root = Path(pilot_root)
    classes = load_head_classes(schema_path)
    manifest = _manifest_index(root / "pilot_manifest.csv")
    with Path(annotations_csv).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    statuses = Counter(row.get("circulation_path_status", "") for row in rows)
    records: list[DinoRecord] = []
    for row_number, row in enumerate(rows, start=2):
        if row.get("circulation_path_status") != "annotated":
            continue
        filename = row.get("filename", "").strip()
        metadata = manifest.get(filename)
        if metadata is None:
            raise ValueError(f"Linha {row_number}: filename fora do manifesto: {filename}")
        polygons = parse_polygons(row.get("circulation_path", ""))
        width, height = int(row["image_width"]), int(row["image_height"])
        local_filename = metadata["local_filename"].replace("\\", "/")
        relative = PurePosixPath(local_filename)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"local_filename inseguro: {local_filename}")
        image_path = root / "images" / Path(*relative.parts)
        if not image_path.is_file():
            raise FileNotFoundError(f"Imagem não encontrada: {image_path}")
        with Image.open(image_path) as image:
            if image.size != (width, height):
                raise ValueError(
                    f"Dimensões divergentes em {filename}: CSV={width}x{height}, imagem={image.size}"
                )
        categorical: dict[str, str | None] = {}
        for head in CATEGORICAL_HEADS:
            value = row.get(head, "")
            if value == "unknown":
                categorical[head] = None
            elif value not in classes[head]:
                raise ValueError(f"Linha {row_number}: {head} inválida: {value!r}")
            else:
                categorical[head] = value
        multilabel: dict[str, tuple[str, ...]] = {}
        for head in MULTILABEL_HEADS:
            try:
                values = tuple(json.loads(row.get(head, "")))
            except (json.JSONDecodeError, TypeError) as error:
                raise ValueError(f"Linha {row_number}: JSON inválido em {head}") from error
            unknown = set(values) - set(classes[head])
            if unknown:
                raise ValueError(f"Linha {row_number}: classes desconhecidas em {head}: {sorted(unknown)}")
            multilabel[head] = tuple(value for value in classes[head] if value in values)
        records.append(
            DinoRecord(
                filename=filename,
                image_path=image_path,
                subset=metadata["subset"],
                panorama_id=metadata["panorama_id"],
                polygons=polygons,
                image_width=width,
                image_height=height,
                categorical=categorical,
                multilabel=multilabel,
            )
        )
    if len({record.filename for record in records}) != len(records):
        raise ValueError("Filenames duplicados entre os registros DINOv2")
    return records, classes, statuses


def emphasize_circulation_path(
    image: Image.Image,
    polygons: Sequence[Sequence[Sequence[float]]],
    *,
    outside_brightness: float = 0.45,
    outside_saturation: float = 0.20,
    blur_radius: float = 1.2,
) -> Image.Image:
    """Mantém a circulação intacta e atenua, dessatura e suaviza o contexto."""

    rgb = image.convert("RGB")
    mask = rasterize_polygons(polygons, rgb.width, rgb.height).point(
        lambda value: 255 if value else 0
    )
    return emphasize_circulation_mask(
        rgb,
        mask,
        outside_brightness=outside_brightness,
        outside_saturation=outside_saturation,
        blur_radius=blur_radius,
    )


def emphasize_circulation_mask(
    image: Image.Image,
    mask: Image.Image,
    *,
    outside_brightness: float = 0.45,
    outside_saturation: float = 0.20,
    blur_radius: float = 1.2,
) -> Image.Image:
    rgb = image.convert("RGB")
    binary_mask = mask.convert("L").resize(rgb.size, Image.Resampling.NEAREST).point(
        lambda value: 255 if value else 0
    )
    context = ImageEnhance.Color(rgb).enhance(outside_saturation)
    context = ImageEnhance.Brightness(context).enhance(outside_brightness)
    context = context.filter(ImageFilter.GaussianBlur(blur_radius))
    return Image.composite(rgb, context, binary_mask)


def create_grouped_multitask_split(
    records: Sequence[DinoRecord], seed: int = 42
) -> dict[str, str]:
    """Split 70/15/15 aproximando features e mantendo cada panorama isolado."""

    total = len(records)
    train_size = round(total * 0.70)
    remaining = total - train_size
    targets = {
        "train": train_size,
        "validation": remaining // 2,
        "test": remaining - remaining // 2,
    }
    groups: dict[str, list[DinoRecord]] = defaultdict(list)
    for record in records:
        groups[record.panorama_id].append(record)
    global_features = Counter(
        feature for record in records for feature in record.stratification_features()
    )
    # No piloto atual cada panorama aparece uma vez. Uma busca determinística
    # entre splits aleatórios exatos produz estratificação muito melhor que um
    # greedy para as classes raras, sem fingir balanceamento perfeito.
    if all(len(group) == 1 for group in groups.values()):
        rng = random.Random(seed)
        items = [group[0] for group in groups.values()]
        best_score = float("inf")
        best: dict[str, str] | None = None
        for _ in range(5000):
            rng.shuffle(items)
            candidate: dict[str, str] = {}
            boundaries = (targets["train"], targets["train"] + targets["validation"])
            for index, record in enumerate(items):
                split = "train" if index < boundaries[0] else "validation" if index < boundaries[1] else "test"
                candidate[record.filename] = split
            split_features = {
                split: Counter(
                    feature
                    for record in records
                    if candidate[record.filename] == split
                    for feature in record.stratification_features()
                )
                for split in ("train", "validation", "test")
            }
            score = 0.0
            for feature, total_count in global_features.items():
                for split in ("train", "validation", "test"):
                    desired = total_count * targets[split] / total
                    actual = split_features[split][feature]
                    score += ((actual - desired) / max(desired, 1.0)) ** 2
                    if actual == 0 and (
                        split == "train" or (split in {"validation", "test"} and total_count >= 5)
                    ):
                        score += 25.0
            if score < best_score:
                best_score = score
                best = candidate.copy()
        if best is None:
            raise RuntimeError("Busca de split não produziu candidato")
        return best

    rng = random.Random(seed)
    group_items = list(groups.items())
    rng.shuffle(group_items)
    group_items.sort(
        key=lambda item: (
            len(item[1]),
            sum(
                1 / global_features[feature]
                for record in item[1]
                for feature in record.stratification_features()
            ),
        ),
        reverse=True,
    )
    counts = Counter()
    feature_counts: dict[str, Counter[str]] = defaultdict(Counter)
    assignments: dict[str, str] = {}
    split_order = ("train", "validation", "test")
    for _, group in group_items:
        size = len(group)
        group_features = Counter(
            feature for record in group for feature in record.stratification_features()
        )
        candidates = [
            split for split in split_order if counts[split] + size <= targets[split]
        ]
        if not candidates:
            raise ValueError("Grupos de panorama não permitem atingir o split 70/15/15")

        def score(split: str) -> tuple[float, float, int]:
            fraction = targets[split] / total
            feature_need = sum(
                max(0.0, global_features[feature] * fraction - feature_counts[split][feature])
                / max(global_features[feature], 1)
                * amount
                for feature, amount in group_features.items()
            )
            capacity_need = (targets[split] - counts[split]) / targets[split]
            return feature_need, capacity_need, -split_order.index(split)

        chosen = max(candidates, key=score)
        for record in group:
            assignments[record.filename] = chosen
        counts[chosen] += size
        feature_counts[chosen].update(group_features)
    if counts != Counter(targets):
        raise ValueError(f"Split incorreto: {dict(counts)}; esperado {targets}")
    return assignments


def write_splits(
    path: str | Path,
    records: Sequence[DinoRecord],
    assignments: Mapping[str, str],
) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("filename", "subset", "panorama_id", "split"),
            lineterminator="\n",
        )
        writer.writeheader()
        for record in sorted(records, key=lambda item: item.filename):
            writer.writerow(
                {
                    "filename": record.filename,
                    "subset": record.subset,
                    "panorama_id": record.panorama_id,
                    "split": assignments[record.filename],
                }
            )


class TransitabilityDinoDataset(Dataset):
    def __init__(
        self,
        records: Sequence[DinoRecord],
        classes: Mapping[str, Sequence[str]],
        processor: Any,
        *,
        augment: bool = False,
    ) -> None:
        self.records = tuple(records)
        self.classes = {head: tuple(values) for head, values in classes.items()}
        self.processor = processor
        self.augment = augment

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.records[index]
        with Image.open(record.image_path) as source:
            image = source.convert("RGB")
        polygons = record.polygons
        if self.augment and bool(torch.rand(()) < 0.5):
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            polygons = tuple(
                tuple((1.0 - x, y) for x, y in polygon) for polygon in polygons
            )
        image = emphasize_circulation_path(image, polygons)
        if self.augment:
            image = ImageEnhance.Brightness(image).enhance(
                float(torch.empty(1).uniform_(0.90, 1.10))
            )
            image = ImageEnhance.Contrast(image).enhance(
                float(torch.empty(1).uniform_(0.90, 1.10))
            )
            image = ImageEnhance.Color(image).enhance(
                float(torch.empty(1).uniform_(0.90, 1.10))
            )
        pixels = self.processor(images=image, return_tensors="pt")[
            "pixel_values"
        ].squeeze(0)
        categorical_targets: dict[str, torch.Tensor] = {}
        categorical_masks: dict[str, torch.Tensor] = {}
        for head in CATEGORICAL_HEADS:
            value = record.categorical[head]
            categorical_targets[head] = torch.tensor(
                -100 if value is None else self.classes[head].index(value),
                dtype=torch.long,
            )
            categorical_masks[head] = torch.tensor(value is not None, dtype=torch.bool)
        multilabel_targets = {
            head: torch.tensor(
                [float(value in record.multilabel[head]) for value in self.classes[head]],
                dtype=torch.float32,
            )
            for head in MULTILABEL_HEADS
        }
        return {
            "pixel_values": pixels,
            "categorical_targets": categorical_targets,
            "categorical_masks": categorical_masks,
            "multilabel_targets": multilabel_targets,
            "filename": record.filename,
        }
