import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest

from tools.annotation_app.core import (
    AnnotationFileError,
    AnnotationValidationError,
    annotation_file_version,
    annotation_to_row,
    deserialize_circulation_path,
    deserialize_multilabel,
    discover_images,
    load_annotations,
    load_schema,
    migrate_annotation_file,
    migrate_annotation_file_v1_to_v2,
    normalize_multilabel,
    save_annotation,
    serialize_circulation_path,
    serialize_multilabel,
    validate_annotation,
    validate_circulation_path,
    write_annotations_atomic,
)
from tools.annotation_app.spatial import (
    circulation_path_to_fabric_json,
    fabric_json_to_circulation_path,
    fit_canvas_size,
)
from tools.annotation_app.presentation import (
    completion_status,
    option_label,
    validate_presentation,
)
from tools.annotation_app.suggestions import (
    ACCEPTED_ORIGIN,
    CORRECTED_ORIGIN,
    MANUAL_ORIGIN,
    annotation_origin,
    annotation_state,
    should_offer_suggestion,
)


SCHEMA_PATH = Path("annotations/annotation-schema.yaml")


class AnnotationToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_schema(SCHEMA_PATH)

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def valid_annotation(self, filename: str = "image.png") -> dict:
        return {
            "filename": filename,
            "passage_width": "adequate",
            "obstruction": "none",
            "obstacle_type": [],
            "surface_condition": "regular",
            "surface_obstacle": [],
            "level_change": "none",
            "ramp_condition": "not_applicable",
            "curb_access": "not_applicable",
            "detour": "not_needed",
            "path_continuity": "continuous",
            "slope": "flat_gentle",
            "annotation_confidence": "high",
            "circulation_path_status": "unknown",
            "circulation_path": [],
            "image_width": 640,
            "image_height": 480,
            "comment": "",
        }

    def test_loads_versioned_schema_and_output_metadata(self) -> None:
        self.assertEqual(self.schema.version, 3)
        self.assertEqual(len(self.schema.fields), 12)
        self.assertEqual(self.schema.field("obstacle_type").kind, "multilabel")
        self.assertEqual(self.schema.field("surface_obstacle").kind, "multilabel")
        self.assertEqual(
            self.schema.field("passage_width").unknown_value,
            "unknown",
        )
        self.assertIn(
            "not_applicable",
            self.schema.field("ramp_condition").not_applicable_values,
        )
        self.assertFalse(self.schema.field("annotation_confidence").model_output)
        self.assertEqual(
            self.schema.spatial.status_values,
            ("annotated", "absent", "unknown"),
        )

    def test_validates_single_label_and_rejects_unknown_value(self) -> None:
        annotation = self.valid_annotation()
        annotation["passage_width"] = "wide"
        normalized = validate_annotation(annotation, self.schema)
        self.assertEqual(normalized["passage_width"], "wide")

        annotation["passage_width"] = "enormous"
        with self.assertRaisesRegex(AnnotationValidationError, "passage_width"):
            validate_annotation(annotation, self.schema)

    def test_validates_multilabel_and_uses_schema_order(self) -> None:
        field = self.schema.field("obstacle_type")
        normalized = normalize_multilabel(["tree", "vehicle"], field)
        self.assertEqual(normalized, ("vehicle", "tree"))

        with self.assertRaisesRegex(AnnotationValidationError, "desconhecidos"):
            normalize_multilabel(["vehicle", "spaceship"], field)
        with self.assertRaisesRegex(AnnotationValidationError, "duplicados"):
            normalize_multilabel(["vehicle", "vehicle"], field)

    def test_accepts_unknown_only_where_declared(self) -> None:
        annotation = self.valid_annotation()
        annotation["passage_width"] = "unknown"
        normalized = validate_annotation(annotation, self.schema)
        self.assertEqual(normalized["passage_width"], "unknown")

        annotation["annotation_confidence"] = "unknown"
        with self.assertRaisesRegex(AnnotationValidationError, "annotation_confidence"):
            validate_annotation(annotation, self.schema)

    def test_serializes_and_deserializes_multilabel_as_json_array(self) -> None:
        field = self.schema.field("surface_obstacle")
        serialized = serialize_multilabel(["debris", "cracks"], field)
        self.assertEqual(serialized, '["cracks","debris"]')
        self.assertEqual(
            deserialize_multilabel(serialized, field),
            ("cracks", "debris"),
        )

    def test_persists_atomically_and_preserves_existing_annotations(self) -> None:
        path = self.root / "nested" / "annotations.csv"
        first = save_annotation(path, self.valid_annotation("a.png"), self.schema)
        second_annotation = self.valid_annotation("b.png")
        second_annotation["obstacle_type"] = ["pole", "vehicle"]
        save_annotation(path, second_annotation, self.schema)

        loaded = load_annotations(path, self.schema)
        self.assertEqual(tuple(loaded), ("a.png", "b.png"))
        self.assertEqual(loaded["a.png"], first)
        self.assertEqual(loaded["b.png"]["obstacle_type"], ("vehicle", "pole"))
        self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_loads_and_updates_existing_annotation_explicitly(self) -> None:
        path = self.root / "annotations.csv"
        save_annotation(path, self.valid_annotation(), self.schema)
        updated = self.valid_annotation()
        updated["passage_width"] = "narrow"
        updated["comment"] = "revisada"
        save_annotation(path, updated, self.schema)

        loaded = load_annotations(path, self.schema)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded["image.png"]["passage_width"], "narrow")
        self.assertEqual(loaded["image.png"]["comment"], "revisada")

    def test_rejects_invalid_value_from_existing_csv(self) -> None:
        path = self.root / "annotations.csv"
        saved = save_annotation(path, self.valid_annotation(), self.schema)
        row = annotation_to_row(saved, self.schema)
        row["slope"] = "vertical"
        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.schema.csv_columns)
            writer.writeheader()
            writer.writerow(row)

        with self.assertRaisesRegex(AnnotationFileError, "slope"):
            load_annotations(path, self.schema)

    def test_rejects_incompatible_schema_version(self) -> None:
        path = self.root / "annotations.csv"
        saved = save_annotation(path, self.valid_annotation(), self.schema)
        row = annotation_to_row(saved, self.schema)
        row["schema_version"] = "999"
        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.schema.csv_columns)
            writer.writeheader()
            writer.writerow(row)

        with self.assertRaisesRegex(AnnotationFileError, "schema_version"):
            load_annotations(path, self.schema)

    def test_missing_and_empty_annotation_files_are_supported(self) -> None:
        missing = self.root / "missing.csv"
        self.assertEqual(load_annotations(missing, self.schema), {})
        with self.assertRaises(FileNotFoundError):
            load_annotations(missing, self.schema, allow_missing=False)

        empty = self.root / "empty.csv"
        empty.touch()
        self.assertEqual(load_annotations(empty, self.schema), {})

    def test_rejects_duplicate_filename_in_csv(self) -> None:
        path = self.root / "duplicates.csv"
        saved = save_annotation(path, self.valid_annotation(), self.schema)
        row = annotation_to_row(saved, self.schema)
        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.schema.csv_columns)
            writer.writeheader()
            writer.writerow(row)
            writer.writerow(row)

        with self.assertRaisesRegex(AnnotationFileError, "duplicado"):
            load_annotations(path, self.schema)

    def test_write_rejects_duplicate_filename(self) -> None:
        path = self.root / "duplicates.csv"
        first = self.valid_annotation()
        first["annotation_timestamp"] = "2026-10-18T00:00:00+00:00"
        first["schema_version"] = self.schema.version
        with self.assertRaisesRegex(AnnotationFileError, "duplicado"):
            write_annotations_atomic(path, [first, first], self.schema)

    def test_discovers_images_in_any_directory_without_subset_assumption(self) -> None:
        custom_directory = self.root / "my-custom-images" / "nested"
        custom_directory.mkdir(parents=True)
        Image.new("RGB", (8, 8), color=(30, 60, 90)).save(
            custom_directory / "example.PNG"
        )
        (custom_directory / "notes.txt").write_text("ignore", encoding="utf-8")

        images = discover_images(self.root / "my-custom-images")

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].filename, "nested/example.PNG")

    def test_discover_images_handles_empty_and_missing_directory(self) -> None:
        empty = self.root / "empty-images"
        empty.mkdir()
        self.assertEqual(discover_images(empty), ())
        with self.assertRaises(FileNotFoundError):
            discover_images(self.root / "does-not-exist")

    def test_streamlit_app_starts_without_exception(self) -> None:
        app_path = (
            Path(__file__).resolve().parents[1]
            / "tools"
            / "annotation_app"
            / "app.py"
        )
        app = AppTest.from_file(app_path)

        app.run(timeout=10)

        self.assertFalse(app.exception)

    def test_visual_configuration_covers_schema_without_changing_values(self) -> None:
        validate_presentation(self.schema)
        self.assertEqual(option_label("obstruction", "partial"), "Parcial")
        self.assertEqual(option_label("obstruction", "unknown"), "Não é possível determinar")
        self.assertEqual(option_label("future_field", "raw_value"), "raw_value")

    def test_completion_status_requires_values_or_explicit_empty_multilabel(self) -> None:
        values = self.valid_annotation()
        empty_confirmations = {"obstacle_type": True, "surface_obstacle": True}
        complete = completion_status(self.schema, values, empty_confirmations)
        self.assertTrue(complete.is_complete)
        self.assertEqual((complete.completed, complete.total), (12, 12))

        values["slope"] = None
        empty_confirmations["surface_obstacle"] = False
        pending = completion_status(self.schema, values, empty_confirmations)
        self.assertEqual(pending.completed, 10)
        self.assertIn("Inclinação longitudinal aparente", pending.pending)
        self.assertIn("Problemas específicos da superfície", pending.pending)

    def test_validates_and_serializes_normalized_circulation_path(self) -> None:
        geometry = [[[0.21, 0.76], [0.37, 0.48], [0.84, 0.77]]]
        normalized = validate_circulation_path(geometry)
        self.assertEqual(
            normalized,
            (((0.21, 0.76), (0.37, 0.48), (0.84, 0.77)),),
        )
        serialized = serialize_circulation_path(geometry)
        self.assertEqual(serialized, '[[[0.21,0.76],[0.37,0.48],[0.84,0.77]]]')
        self.assertEqual(deserialize_circulation_path(serialized), normalized)

    def test_rejects_invalid_circulation_path_structures_and_coordinates(self) -> None:
        invalid_values = (
            "not-json-geometry",
            [[[0.1, 0.2], [0.3, 0.4]]],
            [[[0.1, 0.2], [0.3, 0.4], [1.1, 0.5]]],
            [[[0.1, 0.2], [0.3, 0.4], [float("nan"), 0.5]]],
            [[[0.1, 0.2], [0.3, 0.4], [float("inf"), 0.5]]],
            [[[0.1, 0.2], [0.3, 0.4], ["x", 0.5]]],
            [[[0.1, 0.2], [0.3, 0.4], [0.5]]],
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(AnnotationValidationError):
                    validate_circulation_path(value)

    def test_status_and_geometry_rules_are_enforced(self) -> None:
        polygon = [[[0.1, 0.8], [0.4, 0.2], [0.9, 0.8]]]
        annotation = self.valid_annotation()
        annotation["circulation_path_status"] = "annotated"
        with self.assertRaisesRegex(AnnotationValidationError, "exige"):
            validate_annotation(annotation, self.schema)

        for status in ("absent", "unknown"):
            annotation = self.valid_annotation()
            annotation["circulation_path_status"] = status
            annotation["circulation_path"] = polygon
            with self.subTest(status=status):
                with self.assertRaisesRegex(AnnotationValidationError, "vazia"):
                    validate_annotation(annotation, self.schema)

        annotation = self.valid_annotation()
        annotation["circulation_path_status"] = "annotated"
        annotation["circulation_path"] = polygon
        self.assertEqual(
            validate_annotation(annotation, self.schema)["circulation_path"],
            validate_circulation_path(polygon),
        )

    def test_requires_positive_original_image_dimensions(self) -> None:
        for field, value in (("image_width", 0), ("image_height", -1), ("image_width", "x")):
            annotation = self.valid_annotation()
            annotation[field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(AnnotationValidationError, field):
                    validate_annotation(annotation, self.schema)

    def test_csv_round_trip_reopens_geometry_and_dimensions(self) -> None:
        path = self.root / "spatial.csv"
        annotation = self.valid_annotation()
        annotation["circulation_path_status"] = "annotated"
        annotation["circulation_path"] = [
            [[0.1, 0.9], [0.35, 0.25], [0.65, 0.25], [0.9, 0.9]]
        ]
        save_annotation(path, annotation, self.schema)
        reopened = load_annotations(path, self.schema)["image.png"]
        self.assertEqual(reopened["circulation_path"], validate_circulation_path(annotation["circulation_path"]))
        self.assertEqual((reopened["image_width"], reopened["image_height"]), (640, 480))
        self.assertEqual(annotation_file_version(path, self.schema), 3)

    def test_migrates_v1_to_current_preserving_existing_labels(self) -> None:
        image_path = self.root / "image.png"
        Image.new("RGB", (321, 123), color=(10, 20, 30)).save(image_path)
        csv_path = self.root / "legacy.csv"
        original = self.valid_annotation()
        row = {"filename": "image.png"}
        for field in self.schema.fields:
            value = original[field.name]
            row[field.name] = (
                serialize_multilabel(value, field)
                if field.kind == "multilabel"
                else value
            )
        row.update(
            {
                "comment": "preservar",
                "annotation_timestamp": "2026-10-19T12:00:00+00:00",
                "schema_version": "1",
            }
        )
        with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.schema.legacy_csv_columns)
            writer.writeheader()
            writer.writerow(row)

        migrated = migrate_annotation_file_v1_to_v2(csv_path, self.schema, self.root)
        item = migrated["image.png"]
        self.assertEqual(annotation_file_version(csv_path, self.schema), 3)
        self.assertEqual(item["passage_width"], original["passage_width"])
        self.assertEqual(item["comment"], "preservar")
        self.assertEqual(item["circulation_path_status"], "unknown")
        self.assertEqual(item["circulation_path"], ())
        self.assertEqual((item["image_width"], item["image_height"]), (321, 123))
        self.assertEqual(item["circulation_path_origin"], MANUAL_ORIGIN)

    def test_loads_and_migrates_v2_with_manual_origin(self) -> None:
        path = self.root / "v2.csv"
        annotation = self.valid_annotation()
        annotation.update(
            {
                "annotation_timestamp": "2026-10-20T00:00:00+00:00",
                "schema_version": 2,
            }
        )
        current = validate_annotation(
            {**annotation, "schema_version": 3}, self.schema, require_metadata=True
        )
        row = annotation_to_row(current, self.schema)
        row.pop("circulation_path_origin")
        row["schema_version"] = "2"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.schema.spatial_v2_csv_columns)
            writer.writeheader()
            writer.writerow(row)

        loaded = load_annotations(path, self.schema)
        self.assertEqual(annotation_file_version(path, self.schema), 2)
        self.assertEqual(loaded["image.png"]["circulation_path_origin"], MANUAL_ORIGIN)
        migrate_annotation_file(path, self.schema, self.root)
        self.assertEqual(annotation_file_version(path, self.schema), 3)

    def test_suggestion_provenance_and_existing_annotation_protection(self) -> None:
        suggestion = (((0.1, 0.8), (0.5, 0.2), (0.9, 0.8)),)
        corrected = (((0.1, 0.8), (0.5, 0.25), (0.9, 0.8)),)
        self.assertEqual(annotation_origin(suggestion, suggestion), ACCEPTED_ORIGIN)
        self.assertEqual(annotation_origin(corrected, suggestion), CORRECTED_ORIGIN)
        self.assertEqual(annotation_origin(corrected, None), MANUAL_ORIGIN)
        self.assertFalse(should_offer_suggestion({"circulation_path_status": "annotated"}, is_editing=False))
        self.assertTrue(should_offer_suggestion({"circulation_path_status": "annotated"}, is_editing=True))

    def test_annotation_state_distinguishes_pending_and_annotated(self) -> None:
        annotations = {"saved.png": {"circulation_path_status": "annotated"}}
        self.assertEqual(annotation_state("saved.png", annotations), "annotated")
        self.assertEqual(annotation_state("new.png", annotations), "pending")

    def test_fabric_adapter_round_trips_and_rescales_saved_polygon(self) -> None:
        geometry = (((0.1, 0.8), (0.4, 0.2), (0.9, 0.8)),)
        drawing = circulation_path_to_fabric_json(geometry, 800, 600)
        self.assertEqual(
            fabric_json_to_circulation_path(drawing, 800, 600),
            geometry,
        )
        resized = circulation_path_to_fabric_json(geometry, 400, 300)
        self.assertEqual(
            fabric_json_to_circulation_path(resized, 400, 300),
            geometry,
        )
        self.assertEqual(fit_canvas_size(1600, 900), (760, 428))

    def test_reads_fabric_7_polygon_without_explicit_path_offset(self) -> None:
        drawing = {
            "version": "7.4.0",
            "objects": [
                {
                    "type": "Polygon",
                    "originX": "center",
                    "originY": "center",
                    "left": 380,
                    "top": 240,
                    "width": 456,
                    "height": 280,
                    "scaleX": 1,
                    "scaleY": 1,
                    "angle": 0,
                    "skewX": 0,
                    "skewY": 0,
                    "points": [
                        {"x": 152, "y": 100},
                        {"x": 608, "y": 100},
                        {"x": 608, "y": 380},
                        {"x": 152, "y": 380},
                    ],
                }
            ],
        }

        self.assertEqual(
            fabric_json_to_circulation_path(drawing, 760, 500),
            validate_circulation_path(
                [[(0.2, 0.2), (0.8, 0.2), (0.8, 0.76), (0.2, 0.76)]]
            ),
        )


if __name__ == "__main__":
    unittest.main()
