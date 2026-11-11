import argparse
import statistics
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ml.segmentation.dataset import (
    DatasetQaIssue,
    SegmentationRecord,
    audit_segmentation_annotations,
    rasterize_polygons,
)


def _overlay(record: SegmentationRecord, max_width: int = 900) -> Image.Image:
    with Image.open(record.image_path) as source:
        image = source.convert("RGB")
    mask = rasterize_polygons(record.polygons, record.image_width, record.image_height)
    if image.width > max_width:
        ratio = max_width / image.width
        size = (max_width, max(1, round(image.height * ratio)))
        image = image.resize(size, Image.Resampling.LANCZOS)
        mask = mask.resize(size, Image.Resampling.NEAREST)
    color = Image.new("RGB", image.size, (0, 210, 255))
    return Image.composite(Image.blend(image, color, 0.42), image, mask.point(lambda value: 255 if value else 0))


def _contact_sheets(items: list[tuple[SegmentationRecord, Image.Image]], output: Path) -> int:
    columns, rows = 4, 4
    cell_width, image_height, caption_height = 300, 200, 42
    page_size = columns * rows
    pages = 0
    for offset in range(0, len(items), page_size):
        page_items = items[offset : offset + page_size]
        sheet = Image.new("RGB", (columns * cell_width, rows * (image_height + caption_height)), "white")
        draw = ImageDraw.Draw(sheet)
        for index, (record, overlay) in enumerate(page_items):
            row, column = divmod(index, columns)
            thumbnail = overlay.copy()
            thumbnail.thumbnail((cell_width, image_height), Image.Resampling.LANCZOS)
            x = column * cell_width + (cell_width - thumbnail.width) // 2
            y = row * (image_height + caption_height) + (image_height - thumbnail.height) // 2
            sheet.paste(thumbnail, (x, y))
            caption = f"{record.subset} | {Path(record.filename).name}"
            draw.text((column * cell_width + 5, row * (image_height + caption_height) + image_height + 5), caption[:48], fill="black", font=ImageFont.load_default())
        pages += 1
        sheet.save(output / f"contact_sheet_{pages:02d}.jpg", quality=90)
    return pages


def _area_fraction(record: SegmentationRecord) -> float:
    mask = rasterize_polygons(record.polygons, record.image_width, record.image_height)
    return mask.histogram()[1] / (record.image_width * record.image_height)


def _report(
    records: list[SegmentationRecord],
    issues: list[DatasetQaIssue],
    areas: list[float],
    contact_sheet_count: int,
) -> str:
    subsets = Counter(record.subset for record in records)
    panoramas = Counter(record.panorama_id for record in records)
    duplicate_panoramas = sum(count > 1 for count in panoramas.values())
    lines = [
        "# QA do dataset de segmentação",
        "",
        f"- Linhas auditadas: **{len(records) + len(issues)}**",
        f"- Válidas para segmentação: **{len(records)}**",
        f"- Inválidas: **{len(issues)}**",
        f"- Panoramas repetidos entre registros válidos: **{duplicate_panoramas}**",
        f"- Área média ocupada pela máscara: **{statistics.fmean(areas):.2%}**" if areas else "- Área média ocupada pela máscara: n/a",
        f"- Área mediana ocupada pela máscara: **{statistics.median(areas):.2%}**" if areas else "- Área mediana ocupada pela máscara: n/a",
        f"- Contact sheets geradas: **{contact_sheet_count}**",
        "",
        "## Registros válidos por subset",
        "",
        "| Subset | Quantidade |",
        "|---|---:|",
    ]
    for subset in ("Obstacle", "CurbRamp", "SurfaceProblem"):
        lines.append(f"| {subset} | {subsets[subset]} |")
    lines.extend(["", "## Anomalias", ""])
    if issues:
        lines.extend(
            f"- `{item.filename}` — `{item.code}`: {item.message}" for item in issues
        )
        lines.extend(
            [
                "",
                "## Decisão de QA",
                "",
                "**Treinamento bloqueado.** O split 75/15/15 exige 105 máscaras estruturalmente válidas. Nenhuma geometria humana foi corrigida ou gerada automaticamente.",
            ]
        )
    else:
        lines.extend(["- Nenhuma anomalia estrutural.", "", "## Decisão de QA", "", "Dataset liberado para criação do split e treinamento."])
    lines.append("")
    return "\n".join(lines)


def generate_qa_artifacts(
    annotations_csv: str | Path,
    pilot_root: str | Path,
    output: str | Path,
) -> tuple[list[SegmentationRecord], list[DatasetQaIssue]]:
    output_path = Path(output)
    overlays_path = output_path / "qa_overlays"
    output_path.mkdir(parents=True, exist_ok=True)
    overlays_path.mkdir(parents=True, exist_ok=True)
    records, issues = audit_segmentation_annotations(annotations_csv, pilot_root)
    areas: list[float] = []
    contact_items: list[tuple[SegmentationRecord, Image.Image]] = []
    for record in records:
        areas.append(_area_fraction(record))
        overlay = _overlay(record)
        subset_path = overlays_path / record.subset.lower()
        subset_path.mkdir(exist_ok=True)
        overlay.save(subset_path / f"{Path(record.filename).stem}_overlay.jpg", quality=90)
        contact_items.append((record, overlay))
    pages = _contact_sheets(contact_items, overlays_path)
    (output_path / "dataset_qa.md").write_text(
        _report(records, issues, areas, pages), encoding="utf-8"
    )
    return records, issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera o QA das anotações de faixa de circulação."
    )
    parser.add_argument("--annotations", type=Path, default=Path("annotations/transitability_annotations.csv"))
    parser.add_argument("--pilot-root", type=Path, default=Path("data/annotation-pilot"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/segmentation"))
    args = parser.parse_args()
    records, issues = generate_qa_artifacts(args.annotations, args.pilot_root, args.output)
    print(f"QA: {len(records)} válido(s), {len(issues)} inválido(s)")
    for issue in issues:
        print(f"- {issue.filename}: {issue.message}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
