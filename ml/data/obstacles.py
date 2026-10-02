"""Dataset multilabel de obstáculos para uso futuro com modelos PyTorch."""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import torch
from PIL import Image
from torch import Tensor
from torch.utils.data import DataLoader, Dataset, Subset
from torchvision import transforms
from torchvision.transforms import InterpolationMode

TARGET_LABELS = (
    "construction",
    "height-difference",
    "parked-car",
    "pole",
    "trash-recycling-can",
    "tree",
    "vegetation",
)

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
DEFAULT_SPLIT_SEED = 42
DEFAULT_VALIDATION_FRACTION = 0.2


@dataclass(frozen=True)
class ObstacleSample:
    """Referência de uma imagem e seu vetor multilabel."""

    filename: str
    labels: tuple[float, ...]


@dataclass(frozen=True)
class BatchSummary:
    """Resumo de um batch validado."""

    batch_size: int
    image_shape: tuple[int, ...]
    label_shape: tuple[int, ...]
    image_dtype: torch.dtype
    label_dtype: torch.dtype


@dataclass(frozen=True)
class ObstacleDataLoaders:
    """DataLoaders de treino e teste com a mesma ordem de labels."""

    train: DataLoader[tuple[Tensor, Tensor]]
    test: DataLoader[tuple[Tensor, Tensor]]
    labels: tuple[str, ...] = TARGET_LABELS


@dataclass(frozen=True)
class TrainingDataLoaders:
    """DataLoaders derivados exclusivamente do CSV de treino."""

    train: DataLoader[tuple[Tensor, Tensor]]
    validation: DataLoader[tuple[Tensor, Tensor]]
    labels: tuple[str, ...] = TARGET_LABELS


def build_image_transform(*, train: bool, image_size: int = 224) -> Callable:
    """Cria transformações compatíveis com backbones pré-treinados no ImageNet."""

    if image_size <= 0:
        raise ValueError("image_size deve ser maior que zero")

    operations: list[Callable] = []
    if train:
        operations.append(transforms.RandomHorizontalFlip())
    operations.extend(
        [
            transforms.Resize(
                (image_size, image_size),
                interpolation=InterpolationMode.BILINEAR,
                antialias=True,
            ),
            transforms.ToTensor(),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )
    return transforms.Compose(operations)


class ObstacleDataset(Dataset[tuple[Tensor, Tensor]]):
    """Lê imagens e sete labels binárias sem modificar os arquivos de origem."""

    def __init__(
        self,
        csv_path: str | Path,
        image_directory: str | Path,
        *,
        transform: Callable | None = None,
        verify_images: bool = True,
    ) -> None:
        self.csv_path = Path(csv_path)
        self.image_directory = Path(image_directory)
        self.transform = transform or build_image_transform(train=False)
        self.samples = self._read_samples()

        if verify_images:
            missing_images = sorted(
                sample.filename
                for sample in self.samples
                if not (self.image_directory / sample.filename).is_file()
            )
            if missing_images:
                preview = ", ".join(missing_images[:5])
                remainder = len(missing_images) - 5
                suffix = f" e mais {remainder}" if remainder > 0 else ""
                raise FileNotFoundError(
                    f"{len(missing_images)} imagem(ns) não encontrada(s): "
                    f"{preview}{suffix}"
                )

    def _read_samples(self) -> tuple[ObstacleSample, ...]:
        samples: list[ObstacleSample] = []
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                raise ValueError(f"CSV sem cabeçalho: {self.csv_path}")

            required_columns = ("filename", *TARGET_LABELS)
            missing_columns = [
                column for column in required_columns if column not in reader.fieldnames
            ]
            if missing_columns:
                raise ValueError(
                    "Colunas obrigatórias ausentes: " + ", ".join(missing_columns)
                )

            for line_number, row in enumerate(reader, start=2):
                filename = (row.get("filename") or "").strip()
                if not filename:
                    raise ValueError(f"Filename ausente na linha {line_number}")

                labels: list[float] = []
                for label in TARGET_LABELS:
                    value = (row.get(label) or "").strip()
                    if value not in {"0", "1"}:
                        raise ValueError(
                            f"Label {label!r} inválida na linha {line_number}: "
                            f"{value!r}"
                        )
                    labels.append(float(value))

                samples.append(
                    ObstacleSample(filename=filename, labels=tuple(labels))
                )

        if not samples:
            raise ValueError(f"Dataset vazio: {self.csv_path}")
        return tuple(samples)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        sample = self.samples[index]
        image_path = self.image_directory / sample.filename
        with Image.open(image_path) as source_image:
            rgb_image = source_image.convert("RGB")
            image = self.transform(rgb_image)

        if not isinstance(image, Tensor):
            raise TypeError("A transformação da imagem deve retornar um torch.Tensor")

        labels = torch.tensor(sample.labels, dtype=torch.float32)
        return image, labels


def create_obstacle_dataloaders(
    *,
    train_csv: str | Path = "data/obstacles/train.csv",
    test_csv: str | Path = "data/obstacles/test.csv",
    image_directory: str | Path = "data/obstacles/crops",
    batch_size: int = 32,
    image_size: int = 224,
    num_workers: int = 0,
    pin_memory: bool | None = None,
) -> ObstacleDataLoaders:
    """Instancia DataLoaders prontos para treino e avaliação multilabel."""

    if batch_size <= 0:
        raise ValueError("batch_size deve ser maior que zero")
    if num_workers < 0:
        raise ValueError("num_workers não pode ser negativo")

    train_dataset = ObstacleDataset(
        train_csv,
        image_directory,
        transform=build_image_transform(train=True, image_size=image_size),
    )
    test_dataset = ObstacleDataset(
        test_csv,
        image_directory,
        transform=build_image_transform(train=False, image_size=image_size),
    )
    use_pin_memory = torch.cuda.is_available() if pin_memory is None else pin_memory
    common_options = {
        "batch_size": batch_size,
        "num_workers": num_workers,
        "pin_memory": use_pin_memory,
        "persistent_workers": num_workers > 0,
    }
    return ObstacleDataLoaders(
        train=DataLoader(train_dataset, shuffle=True, **common_options),
        test=DataLoader(test_dataset, shuffle=False, **common_options),
    )


def split_train_validation_indices(
    sample_count: int,
    *,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    seed: int = DEFAULT_SPLIT_SEED,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Gera índices distintos e reproduzíveis para treino e validação."""

    if sample_count < 2:
        raise ValueError("São necessárias ao menos duas amostras para a divisão")
    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction deve estar entre 0 e 1")

    validation_size = max(1, round(sample_count * validation_fraction))
    if validation_size >= sample_count:
        validation_size = sample_count - 1

    generator = torch.Generator().manual_seed(seed)
    shuffled_indices = torch.randperm(sample_count, generator=generator).tolist()
    validation_indices = tuple(shuffled_indices[:validation_size])
    train_indices = tuple(shuffled_indices[validation_size:])
    return train_indices, validation_indices


def create_training_dataloaders(
    *,
    train_csv: str | Path = "data/obstacles/train.csv",
    image_directory: str | Path = "data/obstacles/crops",
    batch_size: int = 32,
    image_size: int = 224,
    num_workers: int = 0,
    pin_memory: bool | None = None,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    seed: int = DEFAULT_SPLIT_SEED,
) -> TrainingDataLoaders:
    """Divide o CSV de treino em loaders de treino e validação."""

    if batch_size <= 0:
        raise ValueError("batch_size deve ser maior que zero")
    if num_workers < 0:
        raise ValueError("num_workers não pode ser negativo")

    train_dataset = ObstacleDataset(
        train_csv,
        image_directory,
        transform=build_image_transform(train=True, image_size=image_size),
    )
    validation_dataset = ObstacleDataset(
        train_csv,
        image_directory,
        transform=build_image_transform(train=False, image_size=image_size),
        verify_images=False,
    )
    train_indices, validation_indices = split_train_validation_indices(
        len(train_dataset),
        validation_fraction=validation_fraction,
        seed=seed,
    )
    use_pin_memory = torch.cuda.is_available() if pin_memory is None else pin_memory
    common_options = {
        "batch_size": batch_size,
        "num_workers": num_workers,
        "pin_memory": use_pin_memory,
        "persistent_workers": num_workers > 0,
    }
    shuffle_generator = torch.Generator().manual_seed(seed)
    return TrainingDataLoaders(
        train=DataLoader(
            Subset(train_dataset, train_indices),
            shuffle=True,
            generator=shuffle_generator,
            **common_options,
        ),
        validation=DataLoader(
            Subset(validation_dataset, validation_indices),
            shuffle=False,
            **common_options,
        ),
    )


def create_test_dataloader(
    *,
    test_csv: str | Path = "data/obstacles/test.csv",
    image_directory: str | Path = "data/obstacles/crops",
    batch_size: int = 32,
    image_size: int = 224,
    num_workers: int = 0,
    pin_memory: bool | None = None,
) -> DataLoader[tuple[Tensor, Tensor]]:
    """Cria somente o DataLoader de teste para avaliação final."""

    if batch_size <= 0:
        raise ValueError("batch_size deve ser maior que zero")
    if num_workers < 0:
        raise ValueError("num_workers não pode ser negativo")

    dataset = ObstacleDataset(
        test_csv,
        image_directory,
        transform=build_image_transform(train=False, image_size=image_size),
    )
    use_pin_memory = torch.cuda.is_available() if pin_memory is None else pin_memory
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=use_pin_memory,
        persistent_workers=num_workers > 0,
    )


def validate_batch(loader: DataLoader[tuple[Tensor, Tensor]]) -> BatchSummary:
    """Obtém e valida um batch de imagens e labels binárias float32."""

    try:
        images, labels = next(iter(loader))
    except StopIteration as error:
        raise ValueError("O DataLoader está vazio") from error

    if images.ndim != 4 or images.shape[1] != 3:
        raise ValueError(
            f"Formato de imagens inválido: esperado [B, 3, H, W], "
            f"recebido {tuple(images.shape)}"
        )
    if images.dtype != torch.float32:
        raise TypeError(f"Imagens devem ser float32, recebido {images.dtype}")
    if labels.ndim != 2 or labels.shape[1] != len(TARGET_LABELS):
        raise ValueError(
            f"Formato de labels inválido: esperado [B, {len(TARGET_LABELS)}], "
            f"recebido {tuple(labels.shape)}"
        )
    if labels.dtype != torch.float32:
        raise TypeError(f"Labels devem ser float32, recebido {labels.dtype}")
    if images.shape[0] != labels.shape[0]:
        raise ValueError(
            "Imagens e labels possuem tamanhos de batch diferentes: "
            f"{images.shape[0]} e {labels.shape[0]}"
        )
    if not torch.isfinite(images).all():
        raise ValueError("O batch de imagens contém valores não finitos")
    if not torch.all((labels == 0) | (labels == 1)):
        raise ValueError("O batch contém labels diferentes de 0 ou 1")

    return BatchSummary(
        batch_size=images.shape[0],
        image_shape=tuple(images.shape),
        label_shape=tuple(labels.shape),
        image_dtype=images.dtype,
        label_dtype=labels.dtype,
    )

