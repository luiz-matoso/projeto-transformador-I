"""DINOv2 congelado com uma head independente para cada propriedade."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import torch
from torch import nn

from ml.dinov2 import MODEL_NAME


class DinoV2MultiTask(nn.Module):
    def __init__(
        self,
        classes: Mapping[str, Sequence[str]],
        *,
        backbone: nn.Module | None = None,
        model_name: str = MODEL_NAME,
        freeze_backbone: bool = True,
    ) -> None:
        super().__init__()
        if backbone is None:
            from transformers import AutoModel

            backbone = AutoModel.from_pretrained(model_name)
        self.backbone = backbone
        self.model_name = model_name
        self.freeze_backbone = freeze_backbone
        hidden_size = int(self.backbone.config.hidden_size)
        self.embedding_size = hidden_size
        self.classes = {head: tuple(values) for head, values in classes.items()}
        self.heads = nn.ModuleDict(
            {head: nn.Linear(hidden_size, len(values)) for head, values in self.classes.items()}
        )
        if freeze_backbone:
            for parameter in self.backbone.parameters():
                parameter.requires_grad = False
            self.backbone.eval()

    def train(self, mode: bool = True):
        super().train(mode)
        if self.freeze_backbone:
            self.backbone.eval()
        return self

    def forward(self, pixel_values: torch.Tensor) -> dict[str, torch.Tensor]:
        context: Any
        if self.freeze_backbone:
            with torch.no_grad():
                context = self.backbone(pixel_values=pixel_values)
        else:
            context = self.backbone(pixel_values=pixel_values)
        # DINOv2 foi treinado com token CLS; o primeiro token é a representação
        # global compartilhada recomendada para classificação linear.
        embedding = context.last_hidden_state[:, 0]
        return {head: layer(embedding) for head, layer in self.heads.items()}
