import argparse
import csv
import hashlib
import json
import math
import shutil
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


SUBSETS = ("Obstacle", "SurfaceProblem", "CurbRamp")
SUBSET_SLUGS = {
    "Obstacle": "obstacle",
    "SurfaceProblem": "surface_problem",
    "CurbRamp": "curb_ramp",
}
DEFAULT_WEIGHTS = {"Obstacle": 80, "SurfaceProblem": 70, "CurbRamp": 50}
MANIFEST_COLUMNS = (
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


class PilotBuildError(ValueError):
    pass


@dataclass(frozen=True)
class SourceRecord:
    subset: str
    split: str
    filename: str
    labels: tuple[str, ...]
    available_labels: tuple[str, ...]
    normalized_x: float
    normalized_y: float
    source: Path
    source_member: str
    panorama_id: str
    city: str

    @property
    def identity(self) -> tuple[str, str]:
        return self.subset, self.filename

    @property
    def label_combination(self) -> tuple[str, ...]:
        return self.labels


def _safe_filename(value: str) -> str:
    path = PurePosixPath(value.strip().replace("\\", "/"))
    if not value.strip() or path.is_absolute() or ".." in path.parts:
        raise PilotBuildError(f"Filename inseguro no CSV: {value!r}")
    return path.name


def _coordinate(value: str, field: str, filename: str) -> float:
    try:
        coordinate = float(value)
    except ValueError as error:
        raise PilotBuildError(f"{field} inválido para {filename}") from error
    if not math.isfinite(coordinate) or not 0 <= coordinate <= 1:
        raise PilotBuildError(f"{field} fora de [0, 1] para {filename}")
    return coordinate


def _location(filename: str, subset: str) -> tuple[str, str]:
    stem = Path(filename).stem
    suffix = f"-{subset}"
    panorama_id = stem[: -len(suffix)] if stem.endswith(suffix) else stem
    parts = panorama_id.split("-")
    city = parts[1] if len(parts) >= 3 and parts[0].lower() == "gsv" else "unknown"
    return panorama_id, city


def _parse_csv_rows(
    text: str,
    *,
    subset: str,
    split: str,
    source: Path,
    image_members: dict[str, str],
) -> list[SourceRecord]:
    reader = csv.DictReader(text.splitlines())
    fields = tuple(reader.fieldnames or ())
    required = ("filename", "normalized_x", "normalized_y")
    if not all(field in fields for field in required):
        raise PilotBuildError(f"CSV {subset}/{split} sem colunas obrigatórias")
    labels = tuple(field for field in fields if field not in required)
    if not labels:
        raise PilotBuildError(f"CSV {subset}/{split} não possui labels")
    records: list[SourceRecord] = []
    for row_number, row in enumerate(reader, start=2):
        filename = _safe_filename(row["filename"])
        if filename not in image_members:
            raise PilotBuildError(f"Imagem referenciada não encontrada: {subset}/{filename}")
        positives: list[str] = []
        for label in labels:
            value = str(row[label]).strip()
            if value not in {"0", "1"}:
                raise PilotBuildError(
                    f"Valor não binário em {subset}/{split}, linha {row_number}, label {label}"
                )
            if value == "1":
                positives.append(label)
        panorama_id, city = _location(filename, subset)
        records.append(
            SourceRecord(
                subset=subset,
                split=split,
                filename=filename,
                labels=tuple(positives),
                available_labels=labels,
                normalized_x=_coordinate(row["normalized_x"], "normalized_x", filename),
                normalized_y=_coordinate(row["normalized_y"], "normalized_y", filename),
                source=source,
                source_member=image_members[filename],
                panorama_id=panorama_id,
                city=city,
            )
        )
    return records


def read_directory_subset(path: str | Path, subset: str = "Obstacle") -> list[SourceRecord]:
    root = Path(path)
    if not root.is_dir():
        raise PilotBuildError(f"Diretório do subset ausente: {root}")
    image_files = [
        item for item in root.rglob("*") if item.is_file() and item.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ]
    image_members: dict[str, str] = {}
    for item in image_files:
        if item.name in image_members:
            raise PilotBuildError(f"Filename de imagem duplicado em {root}: {item.name}")
        image_members[item.name] = item.relative_to(root).as_posix()
    records: list[SourceRecord] = []
    for split in ("train", "test"):
        candidates = (root / f"{split}.csv", root / "csv" / f"{split}.csv")
        csv_path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if csv_path is None:
            raise PilotBuildError(f"CSV {split}.csv não encontrado em {root}")
        records.extend(
            _parse_csv_rows(
                csv_path.read_text(encoding="utf-8-sig"),
                subset=subset,
                split=split,
                source=root,
                image_members=image_members,
            )
        )
    return records


def _unique_members_by_name(members: Iterable[str], context: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for member in members:
        name = PurePosixPath(member).name
        if name in result:
            raise PilotBuildError(f"Filename duplicado dentro de {context}: {name}")
        result[name] = member
    return result


def read_zip_subset(path: str | Path, subset: str) -> list[SourceRecord]:
    archive = Path(path)
    if not archive.is_file():
        raise PilotBuildError(f"ZIP do subset {subset} ausente: {archive}")
    try:
        with zipfile.ZipFile(archive) as zipped:
            names = [name for name in zipped.namelist() if not name.endswith("/")]
            images = [
                name for name in names
                if "/crops/" in f"/{name}" and PurePosixPath(name).suffix.lower() in {".png", ".jpg", ".jpeg"}
            ]
            image_members = _unique_members_by_name(images, str(archive))
            records: list[SourceRecord] = []
            for split in ("train", "test"):
                csv_candidates = [
                    name for name in names
                    if PurePosixPath(name).name == f"{split}.csv" and "/csv/" in f"/{name}"
                ]
                if len(csv_candidates) != 1:
                    raise PilotBuildError(
                        f"Esperado um CSV {split}.csv em {archive}; encontrados {len(csv_candidates)}"
                    )
                text = zipped.read(csv_candidates[0]).decode("utf-8-sig")
                records.extend(
                    _parse_csv_rows(
                        text,
                        subset=subset,
                        split=split,
                        source=archive,
                        image_members=image_members,
                    )
                )
    except zipfile.BadZipFile as error:
        raise PilotBuildError(f"ZIP inválido: {archive}") from error
    return records


def read_annotation_filenames(path: str | Path) -> set[str]:
    csv_path = Path(path)
    if not csv_path.is_file():
        raise PilotBuildError(f"CSV de anotações humanas ausente: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if "filename" not in (reader.fieldnames or ()):
            raise PilotBuildError("CSV de anotações humanas não possui filename")
        filenames = [_safe_filename(row["filename"]) for row in reader]
    if len(filenames) != len(set(filenames)):
        raise PilotBuildError("CSV de anotações humanas contém filenames duplicados")
    return set(filenames)


def allocate_quotas(size: int) -> dict[str, int]:
    if size <= 0:
        raise PilotBuildError("--size deve ser positivo")
    total_weight = sum(DEFAULT_WEIGHTS.values())
    raw = {subset: size * DEFAULT_WEIGHTS[subset] / total_weight for subset in SUBSETS}
    quotas = {subset: int(raw[subset]) for subset in SUBSETS}
    remaining = size - sum(quotas.values())
    for subset in sorted(SUBSETS, key=lambda item: (raw[item] - quotas[item], DEFAULT_WEIGHTS[item]), reverse=True)[:remaining]:
        quotas[subset] += 1
    return quotas


def _tie_value(record: SourceRecord, seed: int) -> int:
    payload = f"{seed}|{record.subset}|{record.split}|{record.filename}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def select_diverse(
    records: Iterable[SourceRecord],
    quota: int,
    seed: int,
    required_filenames: set[str] | None = None,
) -> list[SourceRecord]:
    pool = sorted(records, key=lambda record: (record.filename, record.split))
    if len(pool) < quota:
        raise PilotBuildError(f"Subset {pool[0].subset if pool else '?'} possui somente {len(pool)} exemplos para quota {quota}")
    by_filename = {record.filename: record for record in pool}
    if len(by_filename) != len(pool):
        raise PilotBuildError("Há filenames duplicados entre splits do mesmo subset")
    required = set(required_filenames or ())
    missing = required - set(by_filename)
    if missing:
        preview = ", ".join(sorted(missing)[:3])
        raise PilotBuildError(f"Anotações humanas não localizadas no Obstacle: {preview}")
    if len(required) > quota:
        raise PilotBuildError("A quota de Obstacle é menor que as anotações humanas existentes")

    selected = [by_filename[name] for name in sorted(required)]
    selected_ids = {record.identity for record in selected}
    label_frequency = Counter(label for record in pool for label in record.labels)
    selected_labels = Counter(label for record in selected for label in record.labels)
    selected_combinations = Counter(record.label_combination for record in selected)
    selected_cities = Counter(record.city for record in selected)
    selected_splits = Counter(record.split for record in selected)
    selected_panoramas = Counter(record.panorama_id for record in selected)

    while len(selected) < quota:
        candidates = [record for record in pool if record.identity not in selected_ids]

        def score(record: SourceRecord) -> tuple[float, int]:
            rarity = sum(
                1.0 / (math.sqrt(label_frequency[label]) * (1 + selected_labels[label]))
                for label in record.labels
            )
            empty_bonus = 0.15 if not record.labels and selected_combinations[()] == 0 else 0.0
            diversity = (
                (1.6 if selected_combinations[record.label_combination] == 0 else 0.0)
                + 0.8 / (1 + selected_cities[record.city])
                + 0.45 / (1 + selected_splits[record.split])
                + empty_bonus
            )
            repetition_penalty = (
                2.5 * selected_panoramas[record.panorama_id]
                + 0.18 * selected_combinations[record.label_combination]
            )
            return rarity + diversity - repetition_penalty, -_tie_value(record, seed)

        chosen = max(candidates, key=score)
        selected.append(chosen)
        selected_ids.add(chosen.identity)
        selected_labels.update(chosen.labels)
        selected_combinations[chosen.label_combination] += 1
        selected_cities[chosen.city] += 1
        selected_splits[chosen.split] += 1
        selected_panoramas[chosen.panorama_id] += 1
    return selected


def select_pilot(
    records_by_subset: dict[str, list[SourceRecord]],
    *,
    size: int,
    seed: int,
    annotated_obstacle_filenames: set[str],
) -> list[SourceRecord]:
    quotas = allocate_quotas(size)
    selected: list[SourceRecord] = []
    for subset in SUBSETS:
        selected.extend(
            select_diverse(
                records_by_subset[subset],
                quotas[subset],
                seed,
                annotated_obstacle_filenames if subset == "Obstacle" else set(),
            )
        )
    if len({record.identity for record in selected}) != len(selected):
        raise PilotBuildError("A seleção resultou em duplicatas")
    return selected


def _copy_selected(record: SourceRecord, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if record.source.is_dir():
        source_file = record.source.joinpath(*PurePosixPath(record.source_member).parts)
        shutil.copy2(source_file, destination)
    else:
        with zipfile.ZipFile(record.source) as zipped, zipped.open(record.source_member) as source_handle, destination.open("wb") as output_handle:
            shutil.copyfileobj(source_handle, output_handle)


def _manifest_row(record: SourceRecord, seed: int, annotated: set[str]) -> dict[str, str]:
    local_filename = f"{SUBSET_SLUGS[record.subset]}/{record.filename}"
    is_annotated = record.subset == "Obstacle" and record.filename in annotated
    return {
        "local_filename": local_filename,
        "original_filename": record.filename,
        "subset": record.subset,
        "original_split": record.split,
        "original_labels": json.dumps(record.labels, ensure_ascii=False, separators=(",", ":")),
        "normalized_x": format(record.normalized_x, ".12g"),
        "normalized_y": format(record.normalized_y, ".12g"),
        "source": str(record.source),
        "source_member": record.source_member,
        "panorama_id": record.panorama_id,
        "city": record.city,
        "selected_seed": str(seed),
        "annotation_status": "annotated" if is_annotated else "pending",
        "annotation_filename": record.filename if is_annotated else local_filename,
    }


def _summary(selected: list[SourceRecord], seed: int, annotated: set[str]) -> str:
    subset_counts = Counter(record.subset for record in selected)
    split_counts = Counter((record.subset, record.split) for record in selected)
    labels = Counter((record.subset, label) for record in selected for label in record.labels)
    known_labels: dict[str, set[str]] = {subset: set() for subset in SUBSETS}
    for record in selected:
        known_labels[record.subset].update(record.available_labels)
    annotated_count = sum(record.subset == "Obstacle" and record.filename in annotated for record in selected)
    lines = [
        "# Piloto de anotação",
        "",
        f"- Total: **{len(selected)}** imagens",
        f"- Já anotadas: **{annotated_count}**",
        f"- Pendentes: **{len(selected) - annotated_count}**",
        f"- Seed: **{seed}**",
        "",
        "## Composição por subset",
        "",
        "| Subset | Imagens | Train | Test |",
        "|---|---:|---:|---:|",
    ]
    for subset in SUBSETS:
        lines.append(
            f"| {subset} | {subset_counts[subset]} | {split_counts[(subset, 'train')]} | {split_counts[(subset, 'test')]} |"
        )
    lines.extend(["", "## Frequência das tags originais", ""])
    for subset in SUBSETS:
        lines.append(f"### {subset}")
        lines.append("")
        subset_labels = sorted((label, count) for (item_subset, label), count in labels.items() if item_subset == subset)
        if subset_labels:
            lines.extend(f"- `{label}`: {count}" for label, count in subset_labels)
        else:
            lines.append("- Nenhuma tag positiva nas imagens selecionadas.")
        absent = sorted(known_labels[subset] - {label for label, _ in subset_labels})
        if absent:
            lines.append("- Sem positivos selecionados: " + ", ".join(f"`{label}`" for label in absent))
        lines.append("")
    lines.extend(
        [
            "## Critérios de seleção",
            "",
            "As 27 anotações humanas foram preservadas e incluídas primeiro. O restante foi selecionado de forma determinística, favorecendo tags raras, combinações de tags ainda não cobertas, diversidade de cidade e de split, e penalizando repetição de panorama e de combinação.",
            "",
            "## Limitações",
            "",
            "O balanceamento usa somente metadados originais do Project Sidewalk. Ele não estima nem balanceia as 11 propriedades próprias de transitabilidade antes da anotação humana. Tags ausentes ou sem positivos nos CSVs não podem ser representadas.",
            "",
        ]
    )
    return "\n".join(lines)


def build_pilot(
    *,
    obstacle: str | Path,
    surface_problem: str | Path,
    curb_ramp: str | Path,
    annotations: str | Path,
    output: str | Path,
    size: int,
    seed: int,
) -> dict[str, int]:
    output_path = Path(output)
    if output_path.exists():
        raise PilotBuildError(f"O destino já existe; remova ou escolha outro: {output_path}")
    records_by_subset = {
        "Obstacle": read_directory_subset(obstacle, "Obstacle"),
        "SurfaceProblem": read_zip_subset(surface_problem, "SurfaceProblem"),
        "CurbRamp": read_zip_subset(curb_ramp, "CurbRamp"),
    }
    annotated = read_annotation_filenames(annotations)
    selected = select_pilot(
        records_by_subset,
        size=size,
        seed=seed,
        annotated_obstacle_filenames=annotated,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.mkdir()
    try:
        images_root = output_path / "images"
        rows = []
        for record in sorted(selected, key=lambda item: (SUBSETS.index(item.subset), item.filename)):
            row = _manifest_row(record, seed, annotated)
            _copy_selected(record, images_root.joinpath(*row["local_filename"].split("/")))
            rows.append(row)
        with (output_path / "pilot_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        (output_path / "pilot_summary.md").write_text(
            _summary(selected, seed, annotated), encoding="utf-8"
        )
    except Exception:
        shutil.rmtree(output_path, ignore_errors=True)
        raise
    counts = Counter(record.subset for record in selected)
    return {subset: counts[subset] for subset in SUBSETS}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monta um piloto diversificado sem extrair datasets completos."
    )
    parser.add_argument("--obstacle", required=True, type=Path)
    parser.add_argument("--surface-problem", required=True, type=Path)
    parser.add_argument("--curb-ramp", required=True, type=Path)
    parser.add_argument("--annotations", type=Path, default=Path("annotations/transitability_annotations.csv"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        counts = build_pilot(
            obstacle=args.obstacle,
            surface_problem=args.surface_problem,
            curb_ramp=args.curb_ramp,
            annotations=args.annotations,
            output=args.output,
            size=args.size,
            seed=args.seed,
        )
    except (OSError, PilotBuildError) as error:
        print(f"Erro: {error}")
        return 1
    print(f"Piloto criado em {args.output} · total={sum(counts.values())} · seed={args.seed}")
    for subset in SUBSETS:
        print(f"{subset}: {counts[subset]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
