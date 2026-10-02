"""Inspeção somente-leitura dos CSVs do dataset de obstáculos."""

from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

METADATA_COLUMNS = ("filename", "normalized_x", "normalized_y")
MISSING_VALUES = frozenset({"", "na", "n/a", "nan", "null", "none"})


@dataclass(frozen=True)
class LabelStatistics:
    """Contagem de ocorrências positivas de uma label."""

    name: str
    positives: int
    percentage: float


@dataclass(frozen=True)
class PositiveExample:
    """Amostra positiva, com os metadados úteis para revisão humana."""

    filename: str
    normalized_x: str
    normalized_y: str
    positive_labels: tuple[str, ...]


@dataclass
class DatasetReport:
    """Resultado estruturado da inspeção de um arquivo CSV."""

    path: Path
    sample_count: int = 0
    columns: tuple[str, ...] = ()
    label_columns: tuple[str, ...] = ()
    positive_counts: Counter[str] = field(default_factory=Counter)
    positives_per_sample: Counter[int] = field(default_factory=Counter)
    filename_counts: Counter[str] = field(default_factory=Counter)
    missing_image_counts: Counter[str] = field(default_factory=Counter)
    positive_examples: dict[str, list[PositiveExample]] = field(default_factory=dict)
    image_directory: Path | None = None
    missing_counts: Counter[str] = field(default_factory=Counter)
    unexpected_counts: Counter[str] = field(default_factory=Counter)
    examples: dict[str, list[str]] = field(default_factory=dict)

    @property
    def label_statistics(self) -> tuple[LabelStatistics, ...]:
        """Retorna estatísticas das labels na mesma ordem do cabeçalho."""

        return tuple(
            LabelStatistics(
                name=label,
                positives=self.positive_counts[label],
                percentage=(
                    self.positive_counts[label] / self.sample_count * 100
                    if self.sample_count
                    else 0.0
                ),
            )
            for label in self.label_columns
        )

    @property
    def total_missing(self) -> int:
        return sum(self.missing_counts.values())

    @property
    def total_unexpected(self) -> int:
        return sum(self.unexpected_counts.values())

    @property
    def mean_positives_per_sample(self) -> float:
        if not self.sample_count:
            return 0.0
        total = sum(
            count * frequency
            for count, frequency in self.positives_per_sample.items()
        )
        return total / self.sample_count

    @property
    def unique_filename_count(self) -> int:
        return len(self.filename_counts)

    @property
    def duplicate_filenames(self) -> dict[str, int]:
        """Filenames repetidos e sua quantidade total de ocorrências."""

        return {
            filename: count
            for filename, count in self.filename_counts.items()
            if count > 1
        }

    @property
    def duplicate_occurrence_count(self) -> int:
        """Quantidade de linhas excedentes causada por filenames repetidos."""

        return sum(count - 1 for count in self.duplicate_filenames.values())

    @property
    def unique_missing_image_count(self) -> int:
        return len(self.missing_image_counts)

    @property
    def has_issues(self) -> bool:
        return bool(
            self.total_missing
            or self.total_unexpected
            or self.missing_image_counts
            or self.duplicate_filenames
        )


def _is_missing(value: str | None) -> bool:
    return value is None or value.strip().lower() in MISSING_VALUES


def _record_issue(
    report: DatasetReport,
    category: str,
    message: str,
    *,
    missing: bool = False,
    example_limit: int = 5,
) -> None:
    counter = report.missing_counts if missing else report.unexpected_counts
    counter[category] += 1
    examples = report.examples.setdefault(category, [])
    if len(examples) < example_limit:
        examples.append(message)


def _validate_coordinate(
    report: DatasetReport, column: str, value: str | None, line_number: int
) -> None:
    if _is_missing(value):
        _record_issue(
            report,
            column,
            f"linha {line_number}: valor ausente",
            missing=True,
        )
        return

    assert value is not None
    try:
        numeric_value = float(value)
    except ValueError:
        _record_issue(
            report,
            f"{column}: valor não numérico",
            f"linha {line_number}: {value!r}",
        )
        return

    if not math.isfinite(numeric_value) or not 0.0 <= numeric_value <= 1.0:
        _record_issue(
            report,
            f"{column}: fora de [0, 1]",
            f"linha {line_number}: {value!r}",
        )


def inspect_csv(
    path: str | Path,
    *,
    metadata_columns: Iterable[str] = METADATA_COLUMNS,
    image_directory: str | Path | None = None,
) -> DatasetReport:
    """Inspeciona um CSV multilabel sem alterá-lo.

    As colunas que não pertencem a ``metadata_columns`` são tratadas como labels
    binárias e, portanto, devem conter exclusivamente ``0`` ou ``1``.
    """

    csv_path = Path(path)
    metadata = tuple(metadata_columns)
    report = DatasetReport(path=csv_path)
    if image_directory is not None:
        report.image_directory = Path(image_directory)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"O arquivo não possui cabeçalho: {csv_path}")

        columns = tuple(reader.fieldnames)
        report.columns = columns
        report.label_columns = tuple(
            column for column in columns if column not in metadata
        )

        duplicate_columns = [
            column for column, count in Counter(columns).items() if count > 1
        ]
        if duplicate_columns:
            raise ValueError(
                f"O cabeçalho possui colunas duplicadas: {', '.join(duplicate_columns)}"
            )

        missing_metadata = [column for column in metadata if column not in columns]
        if missing_metadata:
            raise ValueError(
                "Colunas de metadados obrigatórias ausentes: "
                + ", ".join(missing_metadata)
            )
        if not report.label_columns:
            raise ValueError("Nenhuma coluna de label foi encontrada")

        for line_number, row in enumerate(reader, start=2):
            report.sample_count += 1

            extra_values = row.get(None)
            if extra_values:
                _record_issue(
                    report,
                    "linha com campos extras",
                    f"linha {line_number}: {extra_values!r}",
                )

            filename = row.get("filename")
            if _is_missing(filename):
                _record_issue(
                    report,
                    "filename",
                    f"linha {line_number}: valor ausente",
                    missing=True,
                )
            elif filename is not None:
                clean_filename = filename.strip()
                report.filename_counts[clean_filename] += 1
                if report.image_directory is not None:
                    image_path = report.image_directory / clean_filename
                    if not image_path.is_file():
                        report.missing_image_counts[clean_filename] += 1

            _validate_coordinate(
                report, "normalized_x", row.get("normalized_x"), line_number
            )
            _validate_coordinate(
                report, "normalized_y", row.get("normalized_y"), line_number
            )

            positive_count = 0
            positive_labels: list[str] = []
            for label in report.label_columns:
                value = row.get(label)
                if _is_missing(value):
                    _record_issue(
                        report,
                        label,
                        f"linha {line_number}: valor ausente",
                        missing=True,
                    )
                elif value is not None and value.strip() in {"0", "1"}:
                    if value.strip() == "1":
                        report.positive_counts[label] += 1
                        positive_count += 1
                        positive_labels.append(label)
                else:
                    _record_issue(
                        report,
                        f"{label}: label não binária",
                        f"linha {line_number}: {value!r}",
                    )

            report.positives_per_sample[positive_count] += 1
            if filename is not None and not _is_missing(filename) and positive_labels:
                example = PositiveExample(
                    filename=filename.strip(),
                    normalized_x=(row.get("normalized_x") or "").strip(),
                    normalized_y=(row.get("normalized_y") or "").strip(),
                    positive_labels=tuple(positive_labels),
                )
                for label in positive_labels:
                    report.positive_examples.setdefault(label, []).append(example)

    return report

