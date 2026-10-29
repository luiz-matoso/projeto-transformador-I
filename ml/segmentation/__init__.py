"""Segmentação binária da faixa principal de circulação."""

MODEL_NAME = "nvidia/segformer-b0-finetuned-cityscapes-1024-1024"
ID2LABEL = {0: "background", 1: "circulation_path"}
LABEL2ID = {label: index for index, label in ID2LABEL.items()}

