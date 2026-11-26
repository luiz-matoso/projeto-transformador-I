import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import torch
from torch import nn

from ml.dinov2 import CATEGORICAL_HEADS, MULTILABEL_HEADS
from ml.dinov2.dataset import load_dinov2_records
from ml.dinov2.model import DinoV2MultiTask
from ml.dinov2.train_v2 import (MULTILABEL_TARGETS, build_model, build_optimizer,
                                calculate_loss, compute_weights, configure_backbone,
                                load_checkpoint, load_frozen_split, save_checkpoint,
                                select_targets)


class Backbone(nn.Module):
    def __init__(self):
        super().__init__()
        self.config = SimpleNamespace(hidden_size=4)
        self.encoder = nn.Module()
        self.encoder.layer = nn.ModuleList([nn.Linear(4, 4) for _ in range(4)])
        self.layernorm = nn.LayerNorm(4)
        self.embedding = nn.Linear(4, 4)

    def forward(self, *, pixel_values):
        x = self.embedding(pixel_values)
        for layer in self.encoder.layer:
            x = layer(x)
        return SimpleNamespace(last_hidden_state=self.layernorm(x).unsqueeze(1))


class DinoV2InfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_real_split(self):
        split = load_frozen_split()
        self.assertEqual({name: list(split.values()).count(name) for name in ("train", "validation", "test")},
                         {"train": 134, "validation": 29, "test": 29})

    def test_rejects_wrong_sizes_and_duplicate_image(self):
        path = self.path / "split.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["filename", "split"])
            writer.writerow(["a.png", "train"])
        with self.assertRaisesRegex(ValueError, "Tamanhos"):
            load_frozen_split(path)
        with path.open("a", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(["a.png", "test"])
        with self.assertRaisesRegex(ValueError, "duplicada"):
            load_frozen_split(path)

    def test_modes_and_gradients(self):
        for mode in ("frozen", "partial"):
            with self.subTest(mode=mode):
                model = build_model({"head": ("a", "b")}, mode, backbone=Backbone())
                if mode == "partial":
                    self.assertFalse(any(p.requires_grad for p in model.backbone.parameters()))
                    configure_backbone(model, mode)
                names = {name for name, p in model.backbone.named_parameters() if p.requires_grad}
                expected = {name for name, _ in model.backbone.named_parameters()
                            if name.startswith(("encoder.layer.2.", "encoder.layer.3.", "layernorm."))}
                self.assertEqual(names, expected if mode == "partial" else set())
                model.train()
                model(torch.randn(2, 4))["head"].sum().backward()
                self.assertTrue(all(p.grad is not None for p in model.heads.parameters()))
                if mode == "partial":
                    self.assertTrue(all(p.grad is not None for p in model.backbone.parameters() if p.requires_grad))

    def test_checkpoint_roundtrip(self):
        for mode in ("frozen", "partial"):
            with self.subTest(mode=mode):
                model = build_model({"head": ("a", "b")}, mode, backbone=Backbone())
                model.eval()
                inputs = torch.randn(2, 4)
                expected = model(inputs)["head"]
                path = self.path / f"{mode}.pt"
                save_checkpoint(path, model, {"mode": mode, "seed": 42}, 3, 0.45)
                restored, checkpoint = load_checkpoint(path, backbone=Backbone())
                restored.eval()
                torch.testing.assert_close(restored(inputs)["head"], expected)
                self.assertEqual((checkpoint["epoch"], checkpoint["best_validation_metric"]), (3, 0.45))
                self.assertEqual(checkpoint["config"]["seed"], 42)
                self.assertTrue(checkpoint["config"]["backbone_warmup"])

    def test_partial_warmup_transition_and_checkpoint(self):
        model = build_model({"head": ("a", "b")}, "partial", backbone=Backbone())
        optimizer = build_optimizer(model, "partial")
        configure_backbone(model, "partial", warmup=True)
        self.assertFalse(any(p.requires_grad for p in model.backbone.parameters()))
        configure_backbone(model, "partial", warmup=False)
        trainable = {id(p) for p in model.backbone.parameters() if p.requires_grad}
        self.assertEqual(trainable, {id(p) for p in optimizer.param_groups[1]["params"]})
        path = self.path / "partial_unfrozen.pt"
        with torch.no_grad():
            model.backbone.layernorm.bias.add_(0.2)
        save_checkpoint(path, model, {"mode": "partial"}, 3, 0.4)
        restored, checkpoint = load_checkpoint(path, backbone=Backbone())
        self.assertFalse(checkpoint["config"]["backbone_warmup"])
        self.assertFalse(restored.freeze_backbone)
        torch.testing.assert_close(restored.backbone.layernorm.bias, model.backbone.layernorm.bias)

    def test_targets_and_output_shapes_on_frozen_split(self):
        records, classes, _ = load_dinov2_records("annotations/transitability_annotations.csv", "data/annotation-pilot", "annotations/annotation-schema.yaml")
        assignments = load_frozen_split()
        train = [record for record in records if assignments[record.filename] == "train"]
        targets, excluded = select_targets(classes, train)
        self.assertEqual({head: targets[head] for head in MULTILABEL_HEADS}, MULTILABEL_TARGETS)
        self.assertTrue(all(item["reason"] == "insufficient_support" for group in excluded.values() for item in group.values()))
        model = build_model(targets, "frozen", backbone=Backbone())
        outputs = model(torch.randn(2, 4))
        self.assertEqual(sum(value.shape[1] for value in outputs.values()), 31)
        self.assertTrue(all(isinstance(head[0], nn.Dropout) and head[0].p == 0.30 for head in model.heads.values()))
        self.assertTrue(all(isinstance(head, nn.Linear) for head in DinoV2MultiTask(targets, backbone=Backbone()).heads.values()))

    def test_weights_losses_and_optimizer_groups(self):
        classes = {head: ("a", "b") for head in CATEGORICAL_HEADS}
        classes.update({head: ("rare", "common") for head in MULTILABEL_HEADS})
        records = [SimpleNamespace(categorical={head: "a" if i < 75 else "b" for head in CATEGORICAL_HEADS},
                                   multilabel={head: (("rare", "common") if i == 0 else ("common",) if i < 25 else ()) for head in MULTILABEL_HEADS}) for i in range(100)]
        cat, multi = compute_weights(records, classes)
        torch.testing.assert_close(cat[CATEGORICAL_HEADS[0]], torch.sqrt(torch.tensor([100/150, 2.0])))
        torch.testing.assert_close(multi[MULTILABEL_HEADS[0]], torch.tensor([8.0, 3.0**0.5]))
        batch = {"categorical_targets": {h: torch.tensor([0, 1]) for h in CATEGORICAL_HEADS},
                 "categorical_masks": {h: torch.tensor([True, True]) for h in CATEGORICAL_HEADS},
                 "multilabel_targets": {h: torch.zeros(2, 2) for h in MULTILABEL_HEADS}}
        outputs = {h: torch.zeros(2, 2) for h in classes}
        loss, individual = calculate_loss(outputs, batch, cat, multi)
        self.assertEqual(set(individual), set(classes))
        torch.testing.assert_close(loss, torch.stack(list(individual.values())).mean())
        model = build_model(classes, "partial", backbone=Backbone())
        optimizer = build_optimizer(model, "partial")
        self.assertEqual([(g["lr"], g["weight_decay"]) for g in optimizer.param_groups], [(1e-4, 0.01), (1e-5, 0.05)])
        self.assertEqual(len(build_optimizer(model, "frozen").param_groups), 1)


if __name__ == "__main__":
    unittest.main()
