import argparse
import csv
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import torch

from ml.data.obstacles import TARGET_LABELS, ObstacleDataset, create_test_dataloader
from ml.evaluate import load_trained_model


DEFAULT_CHECKPOINT = Path("best_model.pt")
DEFAULT_TEST_CSV = Path("data/obstacles/test.csv")
DEFAULT_IMAGE_DIRECTORY = Path("data/obstacles/crops")
DEFAULT_OUTPUT_DIRECTORY = Path("artifacts/error-analysis")


@dataclass(frozen=True)
class ErrorExample:
    sample_index: int
    filename: str
    probability: float


@dataclass(frozen=True)
class LabelSummary:
    label: str
    real_positives: int
    real_negatives: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float
    recall: float
    f1: float
    threshold: float


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def calculate_summaries(
    targets: torch.Tensor,
    probabilities: torch.Tensor,
    thresholds: Sequence[float],
) -> tuple[LabelSummary, ...]:
    """Calcula a matriz de confusão e as métricas de cada label."""

    expected_shape = (targets.shape[0], len(TARGET_LABELS))
    if tuple(targets.shape) != expected_shape:
        raise ValueError(f"Targets devem ter shape {expected_shape}")
    if tuple(probabilities.shape) != expected_shape:
        raise ValueError(f"Probabilidades devem ter shape {expected_shape}")
    if len(thresholds) != len(TARGET_LABELS):
        raise ValueError(f"Esperados {len(TARGET_LABELS)} thresholds")

    target_flags = targets >= 0.5
    threshold_tensor = torch.tensor(thresholds, dtype=probabilities.dtype)
    prediction_flags = probabilities >= threshold_tensor.unsqueeze(0)
    summaries: list[LabelSummary] = []

    for index, label in enumerate(TARGET_LABELS):
        actual = target_flags[:, index]
        predicted = prediction_flags[:, index]
        tp = int((actual & predicted).sum().item())
        fp = int((~actual & predicted).sum().item())
        fn = int((actual & ~predicted).sum().item())
        tn = int((~actual & ~predicted).sum().item())
        precision = _safe_ratio(tp, tp + fp)
        recall = _safe_ratio(tp, tp + fn)
        f1 = _safe_ratio(2 * precision * recall, precision + recall)
        summaries.append(
            LabelSummary(
                label=label,
                real_positives=tp + fn,
                real_negatives=tn + fp,
                true_positives=tp,
                false_positives=fp,
                false_negatives=fn,
                true_negatives=tn,
                precision=precision,
                recall=recall,
                f1=f1,
                threshold=float(thresholds[index]),
            )
        )
    return tuple(summaries)


def select_error_examples(
    samples: Sequence,
    targets: torch.Tensor,
    probabilities: torch.Tensor,
    thresholds: Sequence[float],
    *,
    limit: int,
) -> dict[str, dict[str, tuple[ErrorExample, ...]]]:
    """Seleciona os FP mais altos e os FN mais baixos por label."""

    target_flags = targets >= 0.5
    threshold_tensor = torch.tensor(thresholds, dtype=probabilities.dtype)
    prediction_flags = probabilities >= threshold_tensor.unsqueeze(0)
    selected: dict[str, dict[str, tuple[ErrorExample, ...]]] = {}

    for label_index, label in enumerate(TARGET_LABELS):
        false_positive_indices = torch.where(
            prediction_flags[:, label_index] & ~target_flags[:, label_index]
        )[0].tolist()
        false_negative_indices = torch.where(
            ~prediction_flags[:, label_index] & target_flags[:, label_index]
        )[0].tolist()

        false_positive_indices.sort(
            key=lambda index: float(probabilities[index, label_index]), reverse=True
        )
        false_negative_indices.sort(
            key=lambda index: float(probabilities[index, label_index])
        )

        def build(indices: Sequence[int]) -> tuple[ErrorExample, ...]:
            return tuple(
                ErrorExample(
                    sample_index=index,
                    filename=samples[index].filename,
                    probability=float(probabilities[index, label_index]),
                )
                for index in indices[:limit]
            )

        selected[label] = {
            "false_positive": build(false_positive_indices),
            "false_negative": build(false_negative_indices),
        }
    return selected


def write_summary_csv(
    output_path: Path,
    summaries: Sequence[LabelSummary],
) -> None:
    fieldnames = tuple(LabelSummary.__dataclass_fields__)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            row = summary.__dict__.copy()
            for metric in ("precision", "recall", "f1", "threshold"):
                row[metric] = f"{row[metric]:.6f}"
            writer.writerow(row)


def copy_error_examples(
    output_directory: Path,
    image_directory: Path,
    examples: dict[str, dict[str, tuple[ErrorExample, ...]]],
) -> None:
    for label in TARGET_LABELS:
        for error_type in ("false_positive", "false_negative"):
            target_directory = output_directory / label / error_type
            target_directory.mkdir(parents=True, exist_ok=True)
            for rank, example in enumerate(examples[label][error_type], start=1):
                source = image_directory / example.filename
                suffix = source.suffix.lower() or ".img"
                target_name = (
                    f"{rank:02d}_sample-{example.sample_index:04d}_"
                    f"p-{example.probability:.4f}{suffix}"
                )
                shutil.copy2(source, target_directory / target_name)


def write_examples_csv(
    output_path: Path,
    examples: dict[str, dict[str, tuple[ErrorExample, ...]]],
) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            ("label", "error_type", "rank", "sample_index", "filename", "probability")
        )
        for label in TARGET_LABELS:
            for error_type in ("false_positive", "false_negative"):
                for rank, example in enumerate(examples[label][error_type], start=1):
                    writer.writerow(
                        (
                            label,
                            error_type,
                            rank,
                            example.sample_index,
                            example.filename,
                            f"{example.probability:.6f}",
                        )
                    )


def _markdown_table(summaries: Sequence[LabelSummary]) -> str:
    header = (
        "| Label | Pos. reais | Neg. reais | TP | FP | FN | TN | "
        "Precision | Recall | F1 | Threshold |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    rows = [header]
    for item in summaries:
        rows.append(
            f"| {item.label} | {item.real_positives} | {item.real_negatives} | "
            f"{item.true_positives} | {item.false_positives} | "
            f"{item.false_negatives} | {item.true_negatives} | "
            f"{item.precision:.4f} | {item.recall:.4f} | {item.f1:.4f} | "
            f"{item.threshold:.1f} |"
        )
    return "\n".join(rows)


def write_report(
    output_path: Path,
    summaries: Sequence[LabelSummary],
    sample_count: int,
) -> None:
    """Grava um relatório curto, sem atribuir causas não verificadas."""

    by_false_negatives = sorted(
        summaries, key=lambda item: (-item.false_negatives, item.label)
    )
    by_false_positives = sorted(
        summaries, key=lambda item: (-item.false_positives, item.label)
    )
    by_total_errors = sorted(
        summaries,
        key=lambda item: (-(item.false_positives + item.false_negatives), item.label),
    )
    top_problematic = by_total_errors[:3]

    fn_text = ", ".join(
        f"{item.label} ({item.false_negatives})" for item in by_false_negatives[:3]
    )
    fp_text = ", ".join(
        f"{item.label} ({item.false_positives})" for item in by_false_positives[:3]
    )
    problematic_text = ", ".join(
        f"{item.label} ({item.false_positives + item.false_negatives} erros; "
        f"F1={item.f1:.4f})"
        for item in top_problematic
    )

    report = f"""# Análise de erros do MVP0

Análise executada sobre as {sample_count} amostras de `test.csv`, usando o
`best_model.pt` atual e os thresholds salvos no próprio checkpoint.

## Resumo por label

{_markdown_table(summaries)}

## Principais contagens

- Mais falsos negativos: {fn_text}.
- Mais falsos positivos: {fp_text}.
- Maior volume total de erros (FP + FN): {problematic_text}.

## Exemplos para inspeção

Foram copiados até 10 falsos positivos e até 10 falsos negativos por label.
Os falsos positivos foram priorizados pela maior probabilidade prevista; os
falsos negativos, pela menor probabilidade prevista. O arquivo `examples.csv`
liga cada exemplo ao filename original e à probabilidade produzida.

## Observação visual

As contagens e métricas não permitem determinar, por si sós, a causa dos erros.
Nenhuma causa visual é atribuída neste relatório automático; quando a causa não
for evidente após inspeção humana das imagens selecionadas, ela deve permanecer
registrada como não evidente.
"""
    output_path.write_text(report, encoding="utf-8")


def run_analysis(
    *,
    checkpoint_path: Path,
    test_csv: Path,
    image_directory: Path,
    output_directory: Path,
    batch_size: int,
    num_workers: int,
    example_limit: int,
) -> tuple[LabelSummary, ...]:
    """Executa inferência no teste e materializa os artefatos da análise."""

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    loader = create_test_dataloader(
        test_csv=test_csv,
        image_directory=image_directory,
        batch_size=batch_size,
        num_workers=num_workers,
    )
    if not isinstance(loader.dataset, ObstacleDataset):
        raise TypeError("O DataLoader de teste deve usar ObstacleDataset")

    model, thresholds = load_trained_model(checkpoint_path, device)
    probability_batches: list[torch.Tensor] = []
    target_batches: list[torch.Tensor] = []

    model.eval()
    with torch.inference_mode():
        for images, labels in loader:
            logits = model(images.to(device, non_blocking=True))
            probability_batches.append(torch.sigmoid(logits).cpu())
            target_batches.append(labels.cpu())

    probabilities = torch.cat(probability_batches)
    targets = torch.cat(target_batches)
    samples = loader.dataset.samples
    if len(samples) != probabilities.shape[0]:
        raise RuntimeError("Quantidade de predições diferente da quantidade de amostras")

    summaries = calculate_summaries(targets, probabilities, thresholds)
    examples = select_error_examples(
        samples,
        targets,
        probabilities,
        thresholds,
        limit=example_limit,
    )

    output_directory.mkdir(parents=True, exist_ok=True)
    for label in TARGET_LABELS:
        label_directory = output_directory / label
        if label_directory.exists():
            shutil.rmtree(label_directory)
    for filename in ("summary.csv", "examples.csv", "report.md"):
        path = output_directory / filename
        if path.exists():
            path.unlink()

    copy_error_examples(output_directory, image_directory, examples)
    write_summary_csv(output_directory / "summary.csv", summaries)
    write_examples_csv(output_directory / "examples.csv", examples)
    write_report(output_directory / "report.md", summaries, len(samples))

    print(f"Dispositivo: {device}")
    print(f"Amostras avaliadas: {len(samples)}")
    print(_markdown_table(summaries))
    print(f"\nArtefatos: {output_directory.resolve()}")
    return summaries


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analisa FP e FN do checkpoint atual no test.csv."
    )
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--test-csv", type=Path, default=DEFAULT_TEST_CSV)
    parser.add_argument(
        "--image-directory", type=Path, default=DEFAULT_IMAGE_DIRECTORY
    )
    parser.add_argument(
        "--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--example-limit", type=int, default=10)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.example_limit < 0:
        raise ValueError("example-limit não pode ser negativo")
    run_analysis(
        checkpoint_path=args.checkpoint,
        test_csv=args.test_csv,
        image_directory=args.image_directory,
        output_directory=args.output_directory,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        example_limit=args.example_limit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
