"""Script de linha de comando para inspecionar o dataset de obstáculos."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence, TextIO

from .gallery import create_gallery
from .inspection import DatasetReport, inspect_csv

DEFAULT_DATASETS = (
    Path("data/obstacles/train.csv"),
    Path("data/obstacles/test.csv"),
)


def format_report(report: DatasetReport) -> str:
    """Formata o relatório para leitura no terminal."""

    lines = [
        f"Dataset: {report.path}",
        f"Amostras: {report.sample_count}",
        f"Filenames únicos: {report.unique_filename_count}",
        (
            "Duplicatas de filename: "
            f"{len(report.duplicate_filenames)} filename(s), "
            f"{report.duplicate_occurrence_count} ocorrência(s) além da primeira"
        ),
        f"Colunas ({len(report.columns)}): {', '.join(report.columns)}",
        f"Labels ({len(report.label_columns)}): {', '.join(report.label_columns)}",
    ]

    if report.duplicate_filenames:
        for filename, count in sorted(report.duplicate_filenames.items()):
            lines.append(f"  {filename}: {count} ocorrências")

    if report.image_directory is not None:
        existing_count = (
            report.unique_filename_count - report.unique_missing_image_count
        )
        lines.extend(
            [
                f"Diretório de imagens: {report.image_directory}",
                f"Imagens encontradas: {existing_count}/{report.unique_filename_count}",
                f"Imagens ausentes: {report.unique_missing_image_count}",
            ]
        )
        for filename, count in report.missing_image_counts.most_common(10):
            lines.append(f"  {filename}: referenciada {count} vez(es)")

    lines.extend(["", "Positivos por label:"])

    label_width = max((len(label) for label in report.label_columns), default=5)
    for statistic in report.label_statistics:
        lines.append(
            f"  {statistic.name:<{label_width}}  "
            f"{statistic.positives:>6} ({statistic.percentage:>6.2f}%)"
        )

    lines.extend(
        [
            "",
            "Labels positivos por amostra:",
            f"  média: {report.mean_positives_per_sample:.3f}",
        ]
    )
    if report.positives_per_sample:
        counts = sorted(report.positives_per_sample)
        lines.extend([f"  mínimo: {counts[0]}", f"  máximo: {counts[-1]}"])
        for positive_count in counts:
            frequency = report.positives_per_sample[positive_count]
            percentage = (
                frequency / report.sample_count * 100 if report.sample_count else 0
            )
            lines.append(
                f"  {positive_count:>2} label(s): {frequency:>6} "
                f"amostra(s) ({percentage:>6.2f}%)"
            )

    lines.extend(
        [
            "",
            f"Valores ausentes: {report.total_missing}",
            f"Valores inesperados: {report.total_unexpected}",
        ]
    )
    for heading, issue_counts in (
        ("Detalhes dos valores ausentes", report.missing_counts),
        ("Detalhes dos valores inesperados", report.unexpected_counts),
    ):
        if issue_counts:
            lines.append(f"  {heading}:")
            for category, count in sorted(issue_counts.items()):
                lines.append(f"    {category}: {count}")
                lines.extend(
                    f"      - {example}"
                    for example in report.examples.get(category, [])
                )

    status = "ATENÇÃO" if report.has_issues else "OK"
    lines.append(f"Status: {status}")
    return "\n".join(lines)


def format_examples(
    report: DatasetReport, labels: Sequence[str], *, limit: int
) -> str:
    """Formata exemplos positivos para inspeção rápida no terminal."""

    lines: list[str] = []
    for label in labels:
        lines.append(f"Exemplos positivos · {report.path.name} · {label}")
        examples = report.positive_examples.get(label, [])
        if not examples:
            lines.append("  Nenhum exemplo positivo encontrado.")
            continue
        for example in examples[:limit]:
            lines.append(
                f"  {example.filename} | x={example.normalized_x} | "
                f"y={example.normalized_y} | "
                f"labels={', '.join(example.positive_labels)}"
            )
    return "\n".join(lines)


def format_split_comparison(reports: Sequence[DatasetReport]) -> tuple[str, bool]:
    """Compara filenames e destaca a diferença da classe narrow entre splits."""

    if len(reports) < 2:
        return "", False

    first, second = reports[0], reports[1]
    overlap = set(first.filename_counts) & set(second.filename_counts)
    lines = [
        "Comparação entre splits:",
        (
            f"  Sobreposição de filenames entre {first.path.name} e "
            f"{second.path.name}: {len(overlap)}"
        ),
    ]
    for filename in sorted(overlap)[:10]:
        lines.append(f"    {filename}")
    if len(overlap) > 10:
        lines.append(f"    ... e mais {len(overlap) - 10}")

    if "narrow" in first.label_columns and "narrow" in second.label_columns:
        first_rate = (
            first.positive_counts["narrow"] / first.sample_count * 100
            if first.sample_count
            else 0.0
        )
        second_rate = (
            second.positive_counts["narrow"] / second.sample_count * 100
            if second.sample_count
            else 0.0
        )
        difference = second_rate - first_rate
        lines.extend(
            [
                "  Classe narrow:",
                f"    {first.path.name}: {first_rate:.2f}%",
                f"    {second.path.name}: {second_rate:.2f}%",
                f"    diferença ({second.path.name} - {first.path.name}): "
                f"{difference:+.2f} p.p.",
            ]
        )
        if abs(difference) >= 10:
            lines.append(
                "    ATENÇÃO: há uma diferença expressiva de distribuição "
                "entre os splits."
            )

    return "\n".join(lines), bool(overlap)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspeciona datasets CSV multilabel sem modificá-los."
    )
    parser.add_argument(
        "datasets",
        nargs="*",
        type=Path,
        default=DEFAULT_DATASETS,
        help="CSV(s) a inspecionar (padrão: train.csv e test.csv de obstacles)",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        help="diretório das imagens (padrão: pasta crops ao lado de cada CSV)",
    )
    parser.add_argument(
        "--examples",
        nargs="+",
        metavar="LABEL",
        default=(),
        help="mostra exemplos positivos das labels informadas",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="máximo de exemplos por label e split (padrão: 8)",
    )
    parser.add_argument(
        "--gallery",
        type=Path,
        help="cria uma galeria HTML para as labels passadas em --examples",
    )
    return parser


def run(
    paths: Sequence[Path],
    output: TextIO = sys.stdout,
    *,
    image_directory: Path | None = None,
    example_labels: Sequence[str] = (),
    example_limit: int = 8,
    gallery_path: Path | None = None,
) -> int:
    """Inspeciona os caminhos e escreve os relatórios; retorna um código de saída."""

    reports: list[DatasetReport] = []
    for path in paths:
        try:
            images = image_directory or path.parent / "crops"
            reports.append(inspect_csv(path, image_directory=images))
        except (OSError, ValueError, csv.Error) as error:
            print(f"Erro ao inspecionar {path}: {error}", file=sys.stderr)
            return 2

    if example_labels:
        known_labels = set().union(*(report.label_columns for report in reports))
        unknown_labels = sorted(set(example_labels) - known_labels)
        if unknown_labels:
            print(
                "Labels desconhecidas: " + ", ".join(unknown_labels),
                file=sys.stderr,
            )
            return 2

    for index, report in enumerate(reports):
        if index:
            print("\n" + "=" * 80 + "\n", file=output)
        print(format_report(report), file=output)
        if example_labels:
            examples = format_examples(
                report, example_labels, limit=example_limit
            )
            print("\n" + examples, file=output)

    has_comparison_issue = False
    if len(reports) > 1:
        reference = reports[0].label_columns
        for report in reports[1:]:
            if report.label_columns != reference:
                print(
                    "\nATENÇÃO: os datasets não possuem as mesmas colunas de labels.",
                    file=output,
                )
                return 1
        comparison, has_comparison_issue = format_split_comparison(reports)
        print("\n" + "=" * 80 + "\n", file=output)
        print(comparison, file=output)

    if gallery_path is not None:
        try:
            created_gallery = create_gallery(
                reports,
                example_labels,
                gallery_path,
                limit=example_limit,
            )
        except (OSError, ValueError) as error:
            print(f"Erro ao criar galeria: {error}", file=sys.stderr)
            return 2
        print(f"\nGaleria criada: {created_gallery}", file=output)

    return 1 if has_comparison_issue or any(r.has_issues for r in reports) else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error("--limit deve ser maior que zero")
    if args.gallery is not None and not args.examples:
        parser.error("--gallery requer ao menos uma label em --examples")
    return run(
        args.datasets,
        image_directory=args.images_dir,
        example_labels=args.examples,
        example_limit=args.limit,
        gallery_path=args.gallery,
    )


if __name__ == "__main__":
    raise SystemExit(main())

