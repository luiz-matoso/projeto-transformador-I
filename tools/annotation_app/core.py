import csv
import json
import math
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from PIL import Image


SUPPORTED_IMAGE_EXTENSIONS = frozenset(
    {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
)
PROVENANCE_COLUMNS = ("circulation_path_origin",)
METADATA_COLUMNS = (*PROVENANCE_COLUMNS, "comment", "annotation_timestamp", "schema_version")
SPATIAL_COLUMNS = (
    "circulation_path_status",
    "circulation_path",
    "image_width",
    "image_height",
)
LEGACY_SCHEMA_VERSION = 1
SPATIAL_SCHEMA_VERSION = 2
VALID_CIRCULATION_PATH_ORIGINS = {
    "manual",
    "segformer_v1_accepted",
    "segformer_v1_corrected",
}


class SchemaError(ValueError):
    pass


class AnnotationValidationError(ValueError):
    pass


class AnnotationFileError(ValueError):
    pass


@dataclass(frozen=True)
class OptionDefinition:
    value: str
    definition: str


@dataclass(frozen=True)
class FieldDefinition:
    name: str
    display_name: str
    kind: str
    required: bool
    model_output: bool
    description: str
    options: tuple[OptionDefinition, ...]
    unknown_value: str | None
    not_applicable_values: tuple[str, ...]
    empty_means: str | None = None

    @property
    def option_values(self) -> tuple[str, ...]:
        return tuple(option.value for option in self.options)

    def option_definition(self, value: str) -> str:
        return next(option.definition for option in self.options if option.value == value)


@dataclass(frozen=True)
class SpatialAnnotationDefinition:
    name: str
    display_name: str
    description: str
    status_field: str
    geometry_field: str
    image_width_field: str
    image_height_field: str
    status_options: tuple[OptionDefinition, ...]

    @property
    def status_values(self) -> tuple[str, ...]:
        return tuple(option.value for option in self.status_options)


@dataclass(frozen=True)
class AnnotationSchema:
    version: int
    name: str
    description: str
    fields: tuple[FieldDefinition, ...]
    spatial: SpatialAnnotationDefinition

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)

    @property
    def csv_columns(self) -> tuple[str, ...]:
        return ("filename", *self.field_names, *SPATIAL_COLUMNS, *METADATA_COLUMNS)

    @property
    def legacy_csv_columns(self) -> tuple[str, ...]:
        return (
            "filename",
            *self.field_names,
            "comment",
            "annotation_timestamp",
            "schema_version",
        )

    @property
    def spatial_v2_csv_columns(self) -> tuple[str, ...]:
        return (
            "filename",
            *self.field_names,
            *SPATIAL_COLUMNS,
            "comment",
            "annotation_timestamp",
            "schema_version",
        )

    def field(self, name: str) -> FieldDefinition:
        try:
            return next(field for field in self.fields if field.name == name)
        except StopIteration as error:
            raise KeyError(f"Label desconhecida no schema: {name}") from error


@dataclass(frozen=True)
class ImageItem:
    filename: str
    path: Path


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaError(f"{context} deve ser um objeto YAML")
    return value


def _require_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{context} deve ser texto não vazio")
    return value.strip()


def _parse_options(value: Any, context: str) -> tuple[OptionDefinition, ...]:
    if not isinstance(value, list) or not value:
        raise SchemaError(f"{context} deve ser uma lista não vazia")
    options: list[OptionDefinition] = []
    for index, item in enumerate(value):
        raw = _require_mapping(item, f"{context} opção {index}")
        options.append(
            OptionDefinition(
                value=_require_string(raw.get("value"), f"{context} option.value"),
                definition=_require_string(
                    raw.get("definition"), f"{context} option.definition"
                ),
            )
        )
    option_values = tuple(option.value for option in options)
    if len(option_values) != len(set(option_values)):
        raise SchemaError(f"{context}: opções duplicadas")
    return tuple(options)


def _parse_field(field_name: Any, value: Any) -> FieldDefinition:
    name = _require_string(field_name, "Nome da label")
    context = f"Label {name}"
    raw = _require_mapping(value, context)
    kind = raw.get("type")
    if kind not in {"single-label", "multilabel"}:
        raise SchemaError(f"{context}: type deve ser single-label ou multilabel")

    required = raw.get("required")
    model_output = raw.get("model_output")
    if not isinstance(required, bool) or not isinstance(model_output, bool):
        raise SchemaError(f"{context}: required e model_output devem ser booleanos")

    options = _parse_options(raw.get("options"), f"{context}: options")
    option_values = tuple(option.value for option in options)
    unknown_value = raw.get("unknown_value")
    if unknown_value is not None:
        unknown_value = _require_string(unknown_value, f"{context} unknown_value")
        if unknown_value not in option_values:
            raise SchemaError(f"{context}: unknown_value não pertence às opções")

    raw_not_applicable = raw.get("not_applicable_values", [])
    if not isinstance(raw_not_applicable, list) or any(
        not isinstance(item, str) for item in raw_not_applicable
    ):
        raise SchemaError(f"{context}: not_applicable_values deve ser uma lista")
    not_applicable = tuple(raw_not_applicable)
    if any(item not in option_values for item in not_applicable):
        raise SchemaError(f"{context}: not_applicable_values contém valor inválido")

    empty_means = raw.get("empty_means")
    if empty_means is not None:
        empty_means = _require_string(empty_means, f"{context} empty_means")
    if kind == "multilabel" and empty_means is None:
        raise SchemaError(f"{context}: multilabel exige empty_means")

    return FieldDefinition(
        name=name,
        display_name=_require_string(raw.get("display_name"), f"{context} display_name"),
        kind=kind,
        required=required,
        model_output=model_output,
        description=_require_string(raw.get("description"), f"{context} description"),
        options=options,
        unknown_value=unknown_value,
        not_applicable_values=not_applicable,
        empty_means=empty_means,
    )


def _parse_spatial_annotation(value: Any) -> SpatialAnnotationDefinition:
    raw = _require_mapping(value, "spatial_annotation")
    status_options = _parse_options(
        raw.get("status_options"), "spatial_annotation.status_options"
    )
    if tuple(option.value for option in status_options) != (
        "annotated",
        "absent",
        "unknown",
    ):
        raise SchemaError(
            "spatial_annotation.status_options deve preservar annotated, absent, unknown"
        )
    spatial = SpatialAnnotationDefinition(
        name=_require_string(raw.get("name"), "spatial_annotation.name"),
        display_name=_require_string(
            raw.get("display_name"), "spatial_annotation.display_name"
        ),
        description=_require_string(
            raw.get("description"), "spatial_annotation.description"
        ),
        status_field=_require_string(
            raw.get("status_field"), "spatial_annotation.status_field"
        ),
        geometry_field=_require_string(
            raw.get("geometry_field"), "spatial_annotation.geometry_field"
        ),
        image_width_field=_require_string(
            raw.get("image_width_field"), "spatial_annotation.image_width_field"
        ),
        image_height_field=_require_string(
            raw.get("image_height_field"), "spatial_annotation.image_height_field"
        ),
        status_options=status_options,
    )
    spatial_columns = (
        spatial.status_field,
        spatial.geometry_field,
        spatial.image_width_field,
        spatial.image_height_field,
    )
    if spatial_columns != SPATIAL_COLUMNS:
        raise SchemaError("Os campos espaciais não correspondem ao formato CSV v2")
    return spatial


def load_schema(path: str | Path) -> AnnotationSchema:
    """Carrega e valida o schema declarativo YAML."""
    schema_path = Path(path)
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema não encontrado: {schema_path}")
    try:
        raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise SchemaError(f"YAML inválido em {schema_path}: {error}") from error

    root = _require_mapping(raw, "Raiz do schema")
    version = root.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SchemaError("schema_version deve ser um inteiro positivo")
    if version != 3:
        raise SchemaError("O annotation tool atual exige schema_version 3")

    labels = _require_mapping(root.get("labels"), "labels")
    if not labels:
        raise SchemaError("O schema deve conter ao menos uma label")
    fields = tuple(_parse_field(name, value) for name, value in labels.items())
    schema = AnnotationSchema(
        version=version,
        name=_require_string(root.get("schema_name"), "schema_name"),
        description=_require_string(root.get("description"), "description"),
        fields=fields,
        spatial=_parse_spatial_annotation(root.get("spatial_annotation")),
    )
    try:
        confidence = schema.field("annotation_confidence")
    except KeyError as error:
        raise SchemaError("O schema deve conter annotation_confidence") from error
    if confidence.model_output:
        raise SchemaError("annotation_confidence não pode ser output do modelo")
    return schema


def normalize_filename(filename: Any) -> str:
    """Normaliza um caminho relativo de imagem para o formato POSIX."""

    if not isinstance(filename, str) or not filename.strip():
        raise AnnotationValidationError("filename deve ser texto não vazio")
    normalized = filename.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or path.parts[0].endswith(":"):
        raise AnnotationValidationError("filename deve ser relativo ao diretório de imagens")
    if normalized.endswith("/"):
        raise AnnotationValidationError("filename deve apontar para um arquivo")
    return path.as_posix()


def normalize_multilabel(
    values: Any,
    field: FieldDefinition,
) -> tuple[str, ...]:
    """Valida multilabel e devolve valores na ordem declarada pelo schema."""

    if isinstance(values, str) or not isinstance(values, Sequence):
        raise AnnotationValidationError(f"{field.name} deve ser uma lista")
    if any(not isinstance(value, str) for value in values):
        raise AnnotationValidationError(f"{field.name} contém valor não textual")
    if len(values) != len(set(values)):
        raise AnnotationValidationError(f"{field.name} contém valores duplicados")
    unknown = set(values) - set(field.option_values)
    if unknown:
        raise AnnotationValidationError(
            f"{field.name} contém valores desconhecidos: {', '.join(sorted(unknown))}"
        )
    selected = set(values)
    return tuple(value for value in field.option_values if value in selected)


def validate_circulation_path(value: Any) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Valida uma lista de polígonos em coordenadas normalizadas."""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AnnotationValidationError("circulation_path deve ser uma lista de polígonos")
    polygons: list[tuple[tuple[float, float], ...]] = []
    for polygon_index, polygon in enumerate(value):
        if isinstance(polygon, (str, bytes)) or not isinstance(polygon, Sequence):
            raise AnnotationValidationError(
                f"circulation_path[{polygon_index}] deve ser uma lista de vértices"
            )
        if len(polygon) < 3:
            raise AnnotationValidationError(
                f"circulation_path[{polygon_index}] deve ter pelo menos 3 vértices"
            )
        vertices: list[tuple[float, float]] = []
        for vertex_index, vertex in enumerate(polygon):
            if (
                isinstance(vertex, (str, bytes))
                or not isinstance(vertex, Sequence)
                or len(vertex) != 2
            ):
                raise AnnotationValidationError(
                    f"Vértice inválido em circulation_path[{polygon_index}][{vertex_index}]"
                )
            coordinates: list[float] = []
            for coordinate in vertex:
                if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
                    raise AnnotationValidationError("Coordenada espacial deve ser numérica")
                normalized_coordinate = float(coordinate)
                if not math.isfinite(normalized_coordinate):
                    raise AnnotationValidationError("Coordenada espacial deve ser finita")
                if not 0.0 <= normalized_coordinate <= 1.0:
                    raise AnnotationValidationError(
                        "Coordenada espacial deve estar entre 0 e 1"
                    )
                coordinates.append(normalized_coordinate)
            vertices.append((coordinates[0], coordinates[1]))
        polygons.append(tuple(vertices))
    return tuple(polygons)


def serialize_circulation_path(value: Any) -> str:
    """Serializa geometria normalizada como JSON compacto e determinístico."""

    normalized = validate_circulation_path(value)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def deserialize_circulation_path(serialized: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Desserializa e valida o formato oficial de geometria do projeto."""

    if not isinstance(serialized, str) or not serialized.strip():
        raise AnnotationValidationError("circulation_path deve conter um JSON array")
    try:
        value = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise AnnotationValidationError(
            f"JSON inválido para circulation_path: {serialized!r}"
        ) from error
    return validate_circulation_path(value)


def _positive_image_dimension(value: Any, field_name: str) -> int:
    try:
        dimension = int(value)
    except (TypeError, ValueError) as error:
        raise AnnotationValidationError(f"{field_name} deve ser inteiro positivo") from error
    if isinstance(value, bool) or dimension <= 0 or str(value).strip() != str(dimension):
        raise AnnotationValidationError(f"{field_name} deve ser inteiro positivo")
    return dimension


def validate_annotation(
    annotation: Mapping[str, Any],
    schema: AnnotationSchema,
    *,
    require_metadata: bool = False,
) -> dict[str, Any]:
    """Valida e normaliza uma anotação completa."""

    normalized: dict[str, Any] = {
        "filename": normalize_filename(annotation.get("filename"))
    }
    allowed_keys = set(schema.csv_columns)
    unexpected = set(annotation) - allowed_keys
    if unexpected:
        raise AnnotationValidationError(
            "Campos desconhecidos: " + ", ".join(sorted(unexpected))
        )

    for field in schema.fields:
        value = annotation.get(field.name)
        if field.kind == "single-label":
            if value in (None, ""):
                if field.required:
                    raise AnnotationValidationError(
                        f"Campo obrigatório não preenchido: {field.name}"
                    )
                normalized[field.name] = ""
                continue
            if not isinstance(value, str) or value not in field.option_values:
                raise AnnotationValidationError(
                    f"Valor inválido para {field.name}: {value!r}"
                )
            normalized[field.name] = value
        else:
            if value is None:
                if field.required:
                    raise AnnotationValidationError(
                        f"Campo multilabel não confirmado: {field.name}"
                    )
                value = []
            normalized[field.name] = normalize_multilabel(value, field)

    status = annotation.get(schema.spatial.status_field)
    if status not in schema.spatial.status_values:
        raise AnnotationValidationError(
            f"Valor inválido para {schema.spatial.status_field}: {status!r}"
        )
    geometry = validate_circulation_path(
        annotation.get(schema.spatial.geometry_field)
    )
    if status == "annotated" and not geometry:
        raise AnnotationValidationError(
            "circulation_path_status annotated exige pelo menos um polígono"
        )
    if status in {"absent", "unknown"} and geometry:
        raise AnnotationValidationError(
            f"circulation_path_status {status} exige geometria vazia"
        )
    normalized[schema.spatial.status_field] = status
    normalized[schema.spatial.geometry_field] = geometry
    normalized[schema.spatial.image_width_field] = _positive_image_dimension(
        annotation.get(schema.spatial.image_width_field),
        schema.spatial.image_width_field,
    )
    normalized[schema.spatial.image_height_field] = _positive_image_dimension(
        annotation.get(schema.spatial.image_height_field),
        schema.spatial.image_height_field,
    )

    origin = annotation.get("circulation_path_origin", "manual") or "manual"
    if origin not in VALID_CIRCULATION_PATH_ORIGINS:
        raise AnnotationValidationError(
            f"circulation_path_origin inválida: {origin!r}"
        )
    normalized["circulation_path_origin"] = origin

    comment = annotation.get("comment", "")
    if not isinstance(comment, str):
        raise AnnotationValidationError("comment deve ser texto")
    normalized["comment"] = comment.strip()

    timestamp = annotation.get("annotation_timestamp")
    if require_metadata and (not isinstance(timestamp, str) or not timestamp.strip()):
        raise AnnotationValidationError("annotation_timestamp ausente")
    normalized["annotation_timestamp"] = timestamp.strip() if isinstance(timestamp, str) else ""

    raw_version = annotation.get("schema_version")
    if require_metadata:
        try:
            version = int(raw_version)
        except (TypeError, ValueError) as error:
            raise AnnotationValidationError("schema_version inválido") from error
        if version != schema.version:
            raise AnnotationValidationError(
                f"schema_version incompatível: {version}; esperado {schema.version}"
            )
    normalized["schema_version"] = schema.version
    return normalized


def serialize_multilabel(values: Sequence[str], field: FieldDefinition) -> str:
    normalized = normalize_multilabel(values, field)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def deserialize_multilabel(serialized: str, field: FieldDefinition) -> tuple[str, ...]:
    if not isinstance(serialized, str) or not serialized.strip():
        raise AnnotationValidationError(f"{field.name} deve conter um JSON array")
    try:
        values = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise AnnotationValidationError(
            f"JSON inválido para {field.name}: {serialized!r}"
        ) from error
    return normalize_multilabel(values, field)


def annotation_to_row(
    annotation: Mapping[str, Any], schema: AnnotationSchema
) -> dict[str, str]:
    normalized = validate_annotation(annotation, schema, require_metadata=True)
    row: dict[str, str] = {"filename": normalized["filename"]}
    for field in schema.fields:
        value = normalized[field.name]
        row[field.name] = (
            serialize_multilabel(value, field) if field.kind == "multilabel" else value
        )
    row[schema.spatial.status_field] = normalized[schema.spatial.status_field]
    row[schema.spatial.geometry_field] = serialize_circulation_path(
        normalized[schema.spatial.geometry_field]
    )
    row[schema.spatial.image_width_field] = str(
        normalized[schema.spatial.image_width_field]
    )
    row[schema.spatial.image_height_field] = str(
        normalized[schema.spatial.image_height_field]
    )
    row["circulation_path_origin"] = normalized["circulation_path_origin"]
    row["comment"] = normalized["comment"]
    row["annotation_timestamp"] = normalized["annotation_timestamp"]
    row["schema_version"] = str(schema.version)
    return row


def row_to_annotation(
    row: Mapping[str, str], schema: AnnotationSchema
) -> dict[str, Any]:
    annotation: dict[str, Any] = {"filename": row.get("filename", "")}
    for field in schema.fields:
        raw_value = row.get(field.name, "")
        annotation[field.name] = (
            deserialize_multilabel(raw_value, field)
            if field.kind == "multilabel"
            else raw_value
        )
    annotation[schema.spatial.status_field] = row.get(schema.spatial.status_field, "")
    annotation[schema.spatial.geometry_field] = deserialize_circulation_path(
        row.get(schema.spatial.geometry_field, "")
    )
    annotation[schema.spatial.image_width_field] = row.get(
        schema.spatial.image_width_field, ""
    )
    annotation[schema.spatial.image_height_field] = row.get(
        schema.spatial.image_height_field, ""
    )
    annotation["circulation_path_origin"] = row.get(
        "circulation_path_origin", "manual"
    )
    annotation["comment"] = row.get("comment", "")
    annotation["annotation_timestamp"] = row.get("annotation_timestamp", "")
    annotation["schema_version"] = row.get("schema_version", "")
    return validate_annotation(annotation, schema, require_metadata=True)


def annotation_file_version(path: str | Path, schema: AnnotationSchema) -> int | None:
    """Identifica CSV vazio, v1, v2 ou atual apenas pelo cabeçalho."""

    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return None
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.reader(csv_file)
        header = tuple(next(reader, ()))
    if header == schema.csv_columns:
        return schema.version
    if header == schema.spatial_v2_csv_columns:
        return SPATIAL_SCHEMA_VERSION
    if header == schema.legacy_csv_columns:
        return LEGACY_SCHEMA_VERSION
    raise AnnotationFileError("Cabeçalho incompatível: " + ",".join(header))


def _legacy_row_to_annotation(
    row: Mapping[str, str],
    schema: AnnotationSchema,
    image_root: Path,
) -> dict[str, Any]:
    filename = normalize_filename(row.get("filename"))
    image_path = image_root / Path(*PurePosixPath(filename).parts)
    if not image_path.is_file():
        raise AnnotationFileError(
            f"Imagem necessária para migrar CSV v1 não encontrada: {image_path}"
        )
    try:
        with Image.open(image_path) as image:
            image_width, image_height = image.size
    except OSError as error:
        raise AnnotationFileError(
            f"Não foi possível ler dimensões para migrar {filename}: {error}"
        ) from error

    annotation: dict[str, Any] = {"filename": filename}
    for field in schema.fields:
        raw_value = row.get(field.name, "")
        annotation[field.name] = (
            deserialize_multilabel(raw_value, field)
            if field.kind == "multilabel"
            else raw_value
        )
    annotation.update(
        {
            schema.spatial.status_field: "unknown",
            schema.spatial.geometry_field: (),
            schema.spatial.image_width_field: image_width,
            schema.spatial.image_height_field: image_height,
            "comment": row.get("comment", ""),
            "annotation_timestamp": row.get("annotation_timestamp", ""),
            "schema_version": schema.version,
        }
    )
    if str(row.get("schema_version", "")).strip() != str(LEGACY_SCHEMA_VERSION):
        raise AnnotationValidationError("CSV legado deve declarar schema_version 1")
    return validate_annotation(annotation, schema, require_metadata=True)


def _spatial_v2_row_to_annotation(
    row: Mapping[str, str], schema: AnnotationSchema
) -> dict[str, Any]:
    """Migra em memória uma linha v2, preservando a geometria humana."""

    if str(row.get("schema_version", "")).strip() != str(SPATIAL_SCHEMA_VERSION):
        raise AnnotationValidationError("CSV espacial legado deve declarar schema_version 2")
    prepared = dict(row)
    prepared["circulation_path_origin"] = "manual"
    prepared["schema_version"] = str(schema.version)
    return row_to_annotation(prepared, schema)


def load_annotations(
    path: str | Path,
    schema: AnnotationSchema,
    *,
    allow_missing: bool = True,
    image_root: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Carrega o CSV atual ou migra v1/v2 em memória de forma compatível."""

    csv_path = Path(path)
    if not csv_path.exists():
        if allow_missing:
            return {}
        raise FileNotFoundError(f"CSV de anotações não encontrado: {csv_path}")
    if not csv_path.is_file():
        raise AnnotationFileError(f"Caminho de anotações não é arquivo: {csv_path}")
    if csv_path.stat().st_size == 0:
        return {}

    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            return {}
        fieldnames = tuple(reader.fieldnames)
        is_legacy = fieldnames == schema.legacy_csv_columns
        is_spatial_v2 = fieldnames == schema.spatial_v2_csv_columns
        if fieldnames != schema.csv_columns and not is_legacy and not is_spatial_v2:
            raise AnnotationFileError(
                "Cabeçalho incompatível. Esperado: " + ",".join(schema.csv_columns)
            )
        if is_legacy and image_root is None:
            raise AnnotationFileError(
                "CSV schema_version 1 requer image_root para migração segura"
            )
        annotations: dict[str, dict[str, Any]] = {}
        for line_number, row in enumerate(reader, start=2):
            try:
                annotation = (
                    _legacy_row_to_annotation(row, schema, Path(image_root))
                    if is_legacy
                    else _spatial_v2_row_to_annotation(row, schema)
                    if is_spatial_v2
                    else row_to_annotation(row, schema)
                )
            except AnnotationValidationError as error:
                raise AnnotationFileError(
                    f"Anotação inválida na linha {line_number}: {error}"
                ) from error
            filename = annotation["filename"]
            if filename in annotations:
                raise AnnotationFileError(
                    f"Filename duplicado na linha {line_number}: {filename}"
                )
            annotations[filename] = annotation
    return annotations


def migrate_annotation_file(
    path: str | Path,
    schema: AnnotationSchema,
    image_root: str | Path,
) -> dict[str, dict[str, Any]]:
    """Migra um CSV v1/v2 validado para a versão atual atomicamente."""

    version = annotation_file_version(path, schema)
    if version in (None, schema.version):
        return load_annotations(path, schema, allow_missing=True)
    if version not in {LEGACY_SCHEMA_VERSION, SPATIAL_SCHEMA_VERSION}:
        raise AnnotationFileError(f"Versão de CSV não suportada: {version}")
    migrated = load_annotations(
        path,
        schema,
        allow_missing=False,
        image_root=image_root,
    )
    write_annotations_atomic(path, migrated.values(), schema)
    return migrated


def migrate_annotation_file_v1_to_v2(
    path: str | Path,
    schema: AnnotationSchema,
    image_root: str | Path,
) -> dict[str, dict[str, Any]]:
    """Alias compatível; migra qualquer versão antiga para a versão atual."""

    return migrate_annotation_file(path, schema, image_root)


def write_annotations_atomic(
    path: str | Path,
    annotations: Iterable[Mapping[str, Any]],
    schema: AnnotationSchema,
) -> None:
    """Valida tudo e substitui o CSV atomicamente por uma versão completa."""

    destination = Path(path)
    if destination.exists() and not destination.is_file():
        raise AnnotationFileError(f"Destino não é arquivo: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for annotation in annotations:
        item = validate_annotation(annotation, schema, require_metadata=True)
        if item["filename"] in seen:
            raise AnnotationFileError(f"Filename duplicado: {item['filename']}")
        seen.add(item["filename"])
        normalized.append(item)
    normalized.sort(key=lambda item: item["filename"].casefold())

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            writer = csv.DictWriter(temporary_file, fieldnames=schema.csv_columns)
            writer.writeheader()
            for annotation in normalized:
                writer.writerow(annotation_to_row(annotation, schema))
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def save_annotation(
    path: str | Path,
    annotation: Mapping[str, Any],
    schema: AnnotationSchema,
) -> dict[str, Any]:
    """Insere ou atualiza explicitamente uma anotação e preserva as demais."""

    prepared = dict(annotation)
    prepared["annotation_timestamp"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )
    prepared["schema_version"] = schema.version
    normalized = validate_annotation(prepared, schema, require_metadata=True)
    existing = load_annotations(path, schema, allow_missing=True)
    existing[normalized["filename"]] = normalized
    write_annotations_atomic(path, existing.values(), schema)
    return normalized


def discover_images(
    directory: str | Path,
    *,
    recursive: bool = True,
) -> tuple[ImageItem, ...]:
    """Descobre imagens em qualquer diretório sem assumir subset ou CSV."""

    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"Diretório de imagens não encontrado: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Caminho não é um diretório: {root}")
    candidates = root.rglob("*") if recursive else root.iterdir()
    images = [
        ImageItem(path.relative_to(root).as_posix(), path)
        for path in candidates
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    images.sort(key=lambda item: item.filename.casefold())
    casefolded = [item.filename.casefold() for item in images]
    if len(casefolded) != len(set(casefolded)):
        raise AnnotationFileError(
            "O diretório contém filenames relativos duplicados sem distinção de caixa"
        )
    return tuple(images)
