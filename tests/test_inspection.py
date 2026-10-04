"""Testes do inspetor de datasets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.dataset.gallery import create_gallery
from scripts.dataset.inspect_obstacles import format_split_comparison
from scripts.dataset.inspection import inspect_csv


class InspectCsvTests(unittest.TestCase):
    def _write_csv(self, content: str) -> Path:
        # Um arquivo direto na raiz evita problemas de ACL que algumas
        # sandboxes do Windows aplicam a diretórios criados por tempfile.
        temporary_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            dir=Path.cwd(),
            encoding="utf-8",
            newline="",
            delete=False,
        )
        with temporary_file:
            temporary_file.write(content)
        path = Path(temporary_file.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def _create_image(self) -> Path:
        temporary_file = tempfile.NamedTemporaryFile(
            suffix=".png", dir=Path.cwd(), delete=False
        )
        temporary_file.write(b"not-a-real-image")
        temporary_file.close()
        path = Path(temporary_file.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_computes_multilabel_statistics(self) -> None:
        path = self._write_csv(
            "filename,normalized_x,normalized_y,label-a,label-b\n"
            "a.png,0.1,0.2,1,0\n"
            "b.png,0.3,0.4,1,1\n"
            "c.png,0.5,0.6,0,0\n"
        )

        report = inspect_csv(path)

        self.assertEqual(report.sample_count, 3)
        self.assertEqual(report.label_columns, ("label-a", "label-b"))
        self.assertEqual(report.positive_counts, {"label-a": 2, "label-b": 1})
        self.assertEqual(report.positives_per_sample, {0: 1, 1: 1, 2: 1})
        self.assertAlmostEqual(report.mean_positives_per_sample, 1.0)
        self.assertEqual(report.total_missing, 0)
        self.assertEqual(report.total_unexpected, 0)

    def test_reports_missing_and_unexpected_values(self) -> None:
        path = self._write_csv(
            "filename,normalized_x,normalized_y,label-a\n"
            ",1.5,nope,2\n"
            "b.png,0.3,0.4,\n"
        )

        report = inspect_csv(path)

        self.assertEqual(report.sample_count, 2)
        self.assertEqual(report.total_missing, 2)
        self.assertEqual(report.total_unexpected, 3)
        self.assertEqual(report.positive_counts["label-a"], 0)

    def test_rejects_missing_required_metadata_column(self) -> None:
        path = self._write_csv("filename,normalized_x,label-a\na.png,0.1,1\n")

        with self.assertRaisesRegex(ValueError, "normalized_y"):
            inspect_csv(path)

    def test_checks_filenames_duplicates_images_and_positive_examples(self) -> None:
        image = self._create_image()
        missing_name = "missing-image.png"
        path = self._write_csv(
            "filename,normalized_x,normalized_y,narrow,tree\n"
            f"{image.name},0.1,0.2,1,1\n"
            f"{image.name},0.3,0.4,1,0\n"
            f"{missing_name},0.5,0.6,0,1\n"
        )

        report = inspect_csv(path, image_directory=Path.cwd())

        self.assertEqual(report.unique_filename_count, 2)
        self.assertEqual(report.duplicate_filenames, {image.name: 2})
        self.assertEqual(report.duplicate_occurrence_count, 1)
        self.assertEqual(report.missing_image_counts, {missing_name: 1})
        self.assertEqual(len(report.positive_examples["narrow"]), 2)
        self.assertEqual(
            report.positive_examples["narrow"][0].positive_labels,
            ("narrow", "tree"),
        )

    def test_compares_overlap_and_narrow_distribution(self) -> None:
        train = self._write_csv(
            "filename,normalized_x,normalized_y,narrow\n"
            "shared.png,0.1,0.2,1\n"
            "train.png,0.3,0.4,1\n"
        )
        test = self._write_csv(
            "filename,normalized_x,normalized_y,narrow\n"
            "shared.png,0.5,0.6,0\n"
        )
        reports = (inspect_csv(train), inspect_csv(test))

        comparison, has_overlap = format_split_comparison(reports)

        self.assertTrue(has_overlap)
        self.assertIn("Sobreposição de filenames", comparison)
        self.assertIn("shared.png", comparison)
        self.assertIn("-100.00 p.p.", comparison)

    def test_creates_gallery_with_requested_metadata(self) -> None:
        image = self._create_image()
        path = self._write_csv(
            "filename,normalized_x,normalized_y,narrow,tree\n"
            f"{image.name},0.1,0.2,1,1\n"
        )
        report = inspect_csv(path, image_directory=Path.cwd())
        destination = self._write_csv("").with_suffix(".html")
        self.addCleanup(destination.unlink, missing_ok=True)

        create_gallery((report,), ("narrow",), destination, limit=1)

        html = destination.read_text(encoding="utf-8")
        self.assertIn(image.name, html)
        self.assertIn("x=0.1", html)
        self.assertIn("y=0.2", html)
        self.assertIn("narrow", html)
        self.assertIn("tree", html)


if __name__ == "__main__":
    unittest.main()

