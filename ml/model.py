"""Modelo multilabel do MVP0."""

from __future__ import annotations

from torch import nn
from torchvision.models import ResNet18_Weights, resnet18

from ml.data.obstacles import TARGET_LABELS


def create_model(*, pretrained: bool = True) -> nn.Module:
    """Cria uma ResNet18 com uma saída para cada label do dataset."""

    weights = ResNet18_Weights.DEFAULT if pretrained else None
    model = resnet18(weights=weights)
    model.fc = nn.Linear(model.fc.in_features, len(TARGET_LABELS))
    return model

