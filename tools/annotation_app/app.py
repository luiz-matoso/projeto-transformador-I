"""Interface Streamlit compacta para anotar características de transitabilidade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image

from tools.annotation_app.coherence import find_coherence_warnings
from tools.annotation_app.core import (
    AnnotationFileError,
    AnnotationValidationError,
    FieldDefinition,
    ImageItem,
    annotation_file_version,
    discover_images,
    load_annotations,
    load_schema,
    save_annotation,
)
from tools.annotation_app.original_metadata import (
    OriginalMetadata,
    find_pilot_manifest,
    load_pilot_manifest,
)
from tools.annotation_app.presentation import (
    FIELD_GROUPS,
    completion_status,
    field_help,
    option_label,
    validate_presentation,
)
from tools.annotation_app.spatial import (
    circulation_path_to_fabric_json,
    fabric_json_to_circulation_path,
    fit_canvas_size,
)
from tools.annotation_app.suggestions import (
    annotation_origin,
    annotation_state,
    should_offer_suggestion,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "annotations" / "annotation-schema.yaml"
GUIDELINES_PATH = SCHEMA_PATH.parent / "annotation-guidelines.md"
STYLE_PATH = Path(__file__).with_name("style.css")
DEFAULT_IMAGE_DIRECTORY = PROJECT_ROOT / "data" / "obstacles" / "crops"
DEFAULT_ANNOTATION_CSV = PROJECT_ROOT / "annotations" / "transitability_annotations.csv"
SEGFORMER_CHECKPOINT = PROJECT_ROOT / "artifacts" / "segmentation" / "best_segformer.pt"
SEGMENTATION_SPLITS = PROJECT_ROOT / "artifacts" / "segmentation" / "splits.csv"
EMPTY_SENTINEL = "__explicit_empty__"
SPATIAL_STATUS_LABELS = {
    "annotated": "Identificada",
    "absent": "Ausente",
    "unknown": "Não é possível determinar",
}

FILTER_LABELS = {
    "Todas": "all",
    "Não anotadas": "unannotated",
    "Anotadas": "annotated",
    "Confiança baixa": "low_confidence",
}


@st.cache_resource
def cached_schema():
    return load_schema(SCHEMA_PATH)


def resolve_local_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@st.cache_data(show_spinner=False)
def original_image_size(path: str, modified_ns: int) -> tuple[int, int]:
    """Lê dimensões originais; modified_ns invalida o cache se o arquivo mudar."""
    del modified_ns
    with Image.open(path) as image:
        return image.size


@st.cache_resource(show_spinner=False)
def cached_segformer_predictor(checkpoint_path: str, modified_ns: int):
    """Carrega uma única instância por checkpoint durante a sessão Streamlit."""

    del modified_ns
    from ml.segmentation.predict import load_segformer_predictor

    return load_segformer_predictor(checkpoint_path)


@st.cache_data(show_spinner=False)
def frozen_test_filenames(path: str, modified_ns: int) -> frozenset[str]:
    del modified_ns
    import csv

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return frozenset(
            row["filename"]
            for row in csv.DictReader(handle)
            if row.get("split") == "test"
        )


def filter_images(
    images: tuple[ImageItem, ...],
    annotations: dict[str, dict[str, Any]],
    filter_name: str,
    annotation_keys: dict[str, str] | None = None,
    original_metadata: dict[str, OriginalMetadata] | None = None,
    subset: str = "all",
) -> tuple[ImageItem, ...]:
    keys = annotation_keys or {}
    metadata = original_metadata or {}
    annotation_key = lambda image: keys.get(image.filename, image.filename)
    if subset != "all":
        images = tuple(
            image
            for image in images
            if metadata.get(image.filename)
            and metadata[image.filename].subset == subset
        )
    if filter_name == "unannotated":
        return tuple(
            image
            for image in images
            if annotation_state(annotation_key(image), annotations) == "pending"
        )
    if filter_name == "annotated":
        return tuple(
            image
            for image in images
            if annotation_state(annotation_key(image), annotations) == "annotated"
        )
    if filter_name == "low_confidence":
        return tuple(
            image
            for image in images
            if annotations.get(annotation_key(image), {}).get("annotation_confidence") == "low"
        )
    return images


def initialize_state() -> None:
    defaults: dict[str, Any] = {
        "images": (),
        "annotations": {},
        "original_metadata": {},
        "annotation_keys": {},
        "image_root": None,
        "annotation_csv": None,
        "current_filename": None,
        "dataset_token": 0,
        "form_revision": 0,
        "editing_filename": None,
        "filter_name": "all",
        "filter_label": "Todas",
        "subset_filter": "all",
        "image_directory_input": str(DEFAULT_IMAGE_DIRECTORY),
        "annotation_csv_input": str(DEFAULT_ANNOTATION_CSV),
        "recursive_input": True,
        "notice": None,
        "segformer_suggestions": {},
        "segformer_generated": set(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def leave_edit_mode() -> None:
    st.session_state.editing_filename = None
    st.session_state.form_revision += 1


def move_selection(images: tuple[ImageItem, ...], delta: int) -> None:
    if not images:
        return
    names = [image.filename for image in images]
    current = st.session_state.current_filename
    index = names.index(current) if current in names else 0
    index = max(0, min(len(images) - 1, index + delta))
    st.session_state.current_filename = images[index].filename
    leave_edit_mode()


def next_after_save(
    previous_images: tuple[ImageItem, ...],
    updated_images: tuple[ImageItem, ...],
    current_filename: str,
) -> None:
    if not updated_images:
        st.session_state.current_filename = None
        return
    previous_names = [image.filename for image in previous_images]
    previous_index = previous_names.index(current_filename) if current_filename in previous_names else 0
    updated_names = [image.filename for image in updated_images]
    if current_filename in updated_names:
        new_index = min(updated_names.index(current_filename) + 1, len(updated_names) - 1)
    else:
        new_index = min(previous_index, len(updated_names) - 1)
    st.session_state.current_filename = updated_names[new_index]


def render_field_header(field: FieldDefinition) -> None:
    with st.container(
        key=f"field_header_{field.name}",
        horizontal=True,
        vertical_alignment="center",
    ):
        st.markdown(f"**{field.display_name}**")
        with st.popover("ⓘ", type="tertiary", help=f"Ajuda: {field.display_name}"):
            st.markdown(field_help(field))


def render_field(
    field: FieldDefinition,
    current_value: Any,
    form_key: str,
) -> tuple[Any, bool]:
    render_field_header(field)
    if field.kind == "single-label":
        selected = st.pills(
            field.display_name,
            field.option_values,
            default=current_value if current_value in field.option_values else None,
            format_func=lambda value, name=field.name: option_label(name, value),
            label_visibility="collapsed",
            key=f"{form_key}_{field.name}",
            width="stretch",
            wrap=True,
        )
        return selected, False

    defaults = list(current_value or ())
    choices = (EMPTY_SENTINEL, *field.option_values)
    widget_key = f"{form_key}_{field.name}"
    selected = st.pills(
        field.display_name,
        choices,
        selection_mode="multi",
        default=defaults if defaults else [EMPTY_SENTINEL] if current_value is not None else [],
        format_func=lambda value, name=field.name: (
            "Nenhum relevante" if value == EMPTY_SENTINEL else option_label(name, value)
        ),
        label_visibility="collapsed",
        key=widget_key,
        on_change=enforce_multilabel_exclusivity,
        args=(widget_key,),
        width="stretch",
        wrap=True,
    )
    explicit_empty = EMPTY_SENTINEL in selected
    values = [value for value in selected if value != EMPTY_SENTINEL]
    st.session_state[f"{widget_key}_previous"] = list(selected)
    return values, explicit_empty


def enforce_multilabel_exclusivity(widget_key: str) -> None:
    """Mantém a pill de conjunto vazio mutuamente exclusiva com os itens."""
    selected = list(st.session_state.get(widget_key, ()))
    previous = list(st.session_state.get(f"{widget_key}_previous", ()))
    if EMPTY_SENTINEL in selected and len(selected) > 1:
        st.session_state[widget_key] = (
            [EMPTY_SENTINEL]
            if EMPTY_SENTINEL not in previous
            else [value for value in selected if value != EMPTY_SENTINEL]
        )


def render_spatial_panel(
    current_image: ImageItem,
    existing: dict[str, Any] | None,
    is_editing: bool,
) -> str:
    """Renderiza status/canvas e publica um rascunho independente do Fabric.js."""

    image_width, image_height = original_image_size(
        str(current_image.path), current_image.path.stat().st_mtime_ns
    )
    base_key = (
        f"spatial_{st.session_state.dataset_token}_{st.session_state.form_revision}_"
        f"{current_image.filename.replace('/', '_')}"
    )
    status_key = f"{base_key}_status"
    draft_key = f"{base_key}_draft"
    saved_status = existing.get("circulation_path_status") if existing else None
    saved_geometry = existing.get("circulation_path", ()) if existing else ()
    reset_key = f"{base_key}_reset_revision"
    editor_geometry_key = f"{base_key}_editor_geometry"
    suggestion_key = (
        st.session_state.dataset_token,
        current_image.filename,
    )
    suggestion = st.session_state.segformer_suggestions.get(suggestion_key)
    if reset_key not in st.session_state:
        st.session_state[reset_key] = 0
    if editor_geometry_key not in st.session_state:
        st.session_state[editor_geometry_key] = saved_geometry

    st.caption("FAIXA DE CIRCULAÇÃO")
    if should_offer_suggestion(existing, is_editing=is_editing):
        generate_column, restore_column, clear_column = st.columns(3)
        checkpoint_available = SEGFORMER_CHECKPOINT.is_file()
        with generate_column:
            generate_clicked = st.button(
                "Gerar sugestão SegFormer",
                disabled=not checkpoint_available,
                width="stretch",
                key=f"{base_key}_generate_suggestion",
            )
        with restore_column:
            restore_clicked = st.button(
                "Restaurar sugestão",
                disabled=suggestion is None,
                width="stretch",
                key=f"{base_key}_restore_suggestion",
            )
        with clear_column:
            clear_clicked = st.button(
                "Limpar",
                width="stretch",
                key=f"{base_key}_clear_geometry",
            )
        if not checkpoint_available:
            st.caption(
                "SegFormer indisponível: checkpoint não encontrado. "
                "A anotação manual continua disponível."
            )
        if generate_clicked:
            try:
                from ml.segmentation.predict import predict_circulation_path

                predictor = cached_segformer_predictor(
                    str(SEGFORMER_CHECKPOINT),
                    SEGFORMER_CHECKPOINT.stat().st_mtime_ns,
                )
                with Image.open(current_image.path) as source:
                    generated = predict_circulation_path(
                        predictor, source.convert("RGB")
                    )
                if not generated.polygons:
                    raise ValueError("o modelo não produziu uma região editável")
            except Exception as error:
                st.error(
                    "Não foi possível gerar a sugestão. "
                    f"A anotação manual permanece disponível: {error}"
                )
            else:
                st.session_state.segformer_suggestions[suggestion_key] = generated.polygons
                st.session_state.segformer_generated.add(suggestion_key)
                st.session_state[editor_geometry_key] = generated.polygons
                st.session_state[status_key] = "annotated"
                st.session_state[reset_key] += 1
                st.session_state.notice = (
                    "Sugestão SegFormer gerada em "
                    f"{generated.inference_seconds:.2f}s; revise antes de salvar."
                )
                st.rerun()
        if restore_clicked and suggestion is not None:
            st.session_state[editor_geometry_key] = suggestion
            st.session_state[status_key] = "annotated"
            st.session_state[reset_key] += 1
            st.rerun()
        if clear_clicked:
            st.session_state[editor_geometry_key] = ()
            st.session_state[reset_key] += 1
            st.rerun()
        if suggestion is not None:
            st.info(
                "SegFormer v1 · sugestão automática — revisar antes de salvar"
            )
    status = st.pills(
        "Status da faixa principal de circulação",
        tuple(SPATIAL_STATUS_LABELS),
        default=saved_status,
        format_func=lambda value: SPATIAL_STATUS_LABELS[value],
        key=status_key,
        disabled=existing is not None and not is_editing,
        width="stretch",
        wrap=True,
    )

    geometry = ()
    spatial_error: str | None = None
    if status == "annotated":
        from streamlit_drawable_canvas import st_canvas

        canvas_width, canvas_height = fit_canvas_size(image_width, image_height)
        initial_drawing = circulation_path_to_fabric_json(
            st.session_state[editor_geometry_key],
            canvas_width,
            canvas_height,
        )
        st.caption(
            "Clique nos vértices e feche clicando no primeiro ponto. "
            "O polígono deve atravessar obstáculos internos, sem contorná-los."
        )
        result = st_canvas(
            fill_color="rgba(0, 174, 239, 0.22)",
            stroke_width=3,
            stroke_color="#00AEEF",
            background_image=current_image.path,
            update_streamlit=True,
            height=canvas_height,
            width=canvas_width,
            drawing_mode="polygon",
            initial_drawing=initial_drawing,
            return_image_data=False,
            disabled=existing is not None and not is_editing,
            background_image_fit="stretch",
            key=f"{base_key}_canvas_{st.session_state[reset_key]}",
        )
        drawing = result.json_data if result.json_data is not None else initial_drawing
        try:
            geometry = fabric_json_to_circulation_path(
                drawing,
                canvas_width,
                canvas_height,
            )
            st.session_state[editor_geometry_key] = geometry
        except AnnotationValidationError as error:
            spatial_error = str(error)
            st.error(f"Polígono inválido: {error}")
        if existing is not None and is_editing:
            if st.button(
                "Restaurar polígono salvo",
                disabled=not bool(saved_geometry),
                width="stretch",
                key=f"{base_key}_restore",
            ):
                st.session_state[reset_key] += 1
                st.rerun()
        if geometry:
            st.caption(f"{len(geometry)} polígono(s) · coordenadas normalizadas ao salvar")
    else:
        st.image(str(current_image.path), width="stretch")

    st.session_state[draft_key] = {
        "circulation_path_status": status,
        "circulation_path": geometry if status == "annotated" else (),
        "image_width": image_width,
        "image_height": image_height,
        "circulation_path_origin": annotation_origin(
            geometry if status == "annotated" else (),
            suggestion
            if suggestion_key in st.session_state.segformer_generated
            else None,
            existing_origin=existing.get("circulation_path_origin") if existing else None,
        ),
        "error": spatial_error,
    }
    return draft_key


def render_original_metadata(metadata: OriginalMetadata | None) -> None:
    if metadata is None:
        return
    tags = ", ".join(f"`{label}`" for label in metadata.original_labels) or "nenhuma tag positiva"
    with st.container(key="original_metadata"):
        st.caption("DADOS ORIGINAIS DO PROJECT SIDEWALK")
        st.markdown(
            f"**Project Sidewalk · {metadata.subset}** · split `{metadata.original_split}`  \n"
            f"**Tags:** {tags}  \n"
            f"**Ponto normalizado:** ({metadata.normalized_x:.3f}, {metadata.normalized_y:.3f})"
        )
        st.caption("Somente referência; nenhum campo humano é preenchido automaticamente.")


def render_existing_summary(existing: dict[str, Any], schema, local_filename: str) -> None:
    st.markdown("#### Anotação existente")
    spatial_status = existing["circulation_path_status"]
    st.markdown(
        f"- **Faixa de circulação:** {SPATIAL_STATUS_LABELS[spatial_status]}"
        f" · {len(existing['circulation_path'])} polígono(s)"
        f" · {existing['image_width']}×{existing['image_height']} px"
    )
    for group_name, field_names in FIELD_GROUPS:
        st.caption(group_name)
        lines = []
        for field_name in field_names:
            field = schema.field(field_name)
            raw = existing[field_name]
            if field.kind == "multilabel":
                shown = ", ".join(option_label(field_name, value) for value in raw)
                shown = shown or "Nenhum relevante"
            else:
                shown = option_label(field_name, raw)
            lines.append(f"- **{field.display_name}:** {shown}")
        st.markdown("\n".join(lines))
    if existing.get("comment"):
        st.markdown(f"**Comentário:** {existing['comment']}")
    if st.button("Editar anotação", type="primary", width="stretch"):
        st.session_state.editing_filename = local_filename
        st.session_state.form_revision += 1
        st.rerun()


@st.fragment
def render_annotation_editor(
    schema,
    existing: dict[str, Any] | None,
    current_filename: str,
    annotation_filename: str,
    visible_images: tuple[ImageItem, ...],
    spatial_draft_key: str,
) -> None:
    """Reroda somente o formulário, preservando imagem, posição e scroll."""
    st.markdown("#### Nova anotação" if existing is None else "#### Editando anotação")
    form_key = f"annotation_{st.session_state.dataset_token}_{st.session_state.form_revision}_{current_filename.replace('/', '_')}"

    with st.container(key="sticky_actions"):
        status_column, save_column, save_next_column = st.columns(
            [1.45, 1, 1.25], vertical_alignment="center"
        )
        with status_column:
            status_slot = st.empty()
        with save_column:
            save_clicked = st.button("Salvar", width="stretch")
        with save_next_column:
            save_next_clicked = st.button(
                "Salvar e próxima →", type="primary", width="stretch"
            )
        cancel_clicked = False
        if existing:
            cancel_clicked = st.button(
                "Cancelar edição", type="tertiary", width="stretch"
            )

    spatial = st.session_state.get(spatial_draft_key, {})
    values: dict[str, Any] = {
        "filename": annotation_filename,
        "circulation_path_status": spatial.get("circulation_path_status"),
        "circulation_path": spatial.get("circulation_path", ()),
        "image_width": spatial.get("image_width"),
        "image_height": spatial.get("image_height"),
        "circulation_path_origin": spatial.get(
            "circulation_path_origin", "manual"
        ),
    }
    empty_confirmations: dict[str, bool] = {}
    for group_name, field_names in FIELD_GROUPS:
        with st.container(key=f"field_group_{group_name.lower()}"):
            st.caption(group_name)
            for field_name in field_names:
                field = schema.field(field_name)
                current_value = existing.get(field.name) if existing else None
                value, explicit_empty = render_field(field, current_value, form_key)
                values[field.name] = value
                if field.kind == "multilabel":
                    empty_confirmations[field.name] = explicit_empty

    values["comment"] = st.text_area(
        "Comentário opcional",
        value=existing.get("comment", "") if existing else "",
        max_chars=500,
        height=84,
        placeholder="Observação breve quando necessário",
        key=f"{form_key}_comment",
    )
    coherence_warnings = find_coherence_warnings(values)
    if coherence_warnings:
        st.warning(
            "**Revise estas combinações antes de salvar:**\n\n"
            + "\n".join(f"- {warning.message}" for warning in coherence_warnings)
        )
    status = completion_status(schema, values, empty_confirmations)
    spatial_pending = (
        spatial.get("error")
        or values["circulation_path_status"] not in SPATIAL_STATUS_LABELS
        or (
            values["circulation_path_status"] == "annotated"
            and not values["circulation_path"]
        )
    )
    completed_count = status.completed + (0 if spatial_pending else 1)
    total_count = status.total + 1
    with status_slot.container():
        if status.is_complete and not spatial_pending:
            st.markdown(f"✓ **{completed_count}/{total_count} completos**")
        else:
            pending_count = len(status.pending) + (1 if spatial_pending else 0)
            st.markdown(
                f"**{completed_count}/{total_count} preenchidos** · "
                f"⚠ {pending_count} pendente(s)"
            )

    if cancel_clicked:
        leave_edit_mode()
        st.session_state.notice = "Edição cancelada; nenhuma alteração foi gravada."
        st.rerun()

    if save_clicked or save_next_clicked:
        pending_fields = list(status.pending)
        if spatial_pending:
            pending_fields.insert(0, "Faixa principal de circulação")
        if pending_fields:
            st.error("Campos pendentes: " + ", ".join(pending_fields))
            return
        try:
            saved = save_annotation(
                st.session_state.annotation_csv,
                values,
                schema,
            )
        except (AnnotationValidationError, AnnotationFileError, OSError) as error:
            st.error(f"Anotação não salva: {error}")
            return

        st.session_state.annotations[annotation_filename] = saved
        leave_edit_mode()
        st.session_state.notice = "Anotação salva com escrita atômica."
        if save_next_clicked:
            updated_visible = filter_images(
                st.session_state.images,
                st.session_state.annotations,
                st.session_state.filter_name,
                st.session_state.annotation_keys,
                st.session_state.original_metadata,
                st.session_state.subset_filter,
            )
            next_after_save(visible_images, updated_visible, current_filename)
        st.rerun()


st.set_page_config(
    page_title="Anotação de transitabilidade",
    page_icon="♿",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
initialize_state()

try:
    schema = cached_schema()
    validate_presentation(schema)
except (FileNotFoundError, ValueError) as error:
    st.error(f"Não foi possível carregar a configuração: {error}")
    st.stop()

with st.sidebar:
    st.markdown("### Anotação")
    st.caption(f"Schema v{schema.version} · diretório de imagens genérico")
    st.text_input("Diretório de imagens", key="image_directory_input", help="Caminhos relativos usam a raiz do projeto.")
    st.checkbox("Incluir subdiretórios", key="recursive_input")
    st.text_input("CSV de anotações", key="annotation_csv_input", help="Use um CSV existente para continuar ou um novo caminho para iniciar.")
    if st.button("Carregar", type="primary", width="stretch"):
        try:
            image_root = resolve_local_path(st.session_state.image_directory_input)
            annotation_csv = resolve_local_path(st.session_state.annotation_csv_input)
            images = discover_images(image_root, recursive=st.session_state.recursive_input)
            manifest_path = find_pilot_manifest(image_root)
            original_metadata = (
                load_pilot_manifest(manifest_path, image_root) if manifest_path else {}
            )
            annotation_keys = {
                image.filename: original_metadata[image.filename].annotation_filename
                if image.filename in original_metadata
                else image.filename
                for image in images
            }
            file_version = annotation_file_version(annotation_csv, schema)
            if file_version in {1, 2}:
                annotations = load_annotations(
                    annotation_csv,
                    schema,
                    allow_missing=True,
                    image_root=image_root,
                )
                migration_notice = (
                    f" CSV v{file_version} carregado de forma compatível; "
                    "a migração para v3 ocorrerá somente no próximo save."
                )
            else:
                annotations = load_annotations(annotation_csv, schema, allow_missing=True)
                migration_notice = ""
        except (OSError, ValueError) as error:
            st.error(str(error))
        else:
            st.session_state.images = images
            st.session_state.annotations = annotations
            st.session_state.original_metadata = original_metadata
            st.session_state.annotation_keys = annotation_keys
            st.session_state.image_root = image_root
            st.session_state.annotation_csv = annotation_csv
            st.session_state.current_filename = images[0].filename if images else None
            st.session_state.dataset_token += 1
            leave_edit_mode()
            st.session_state.notice = (
                f"{len(images)} imagem(ns) carregada(s).{migration_notice}"
            )
            st.rerun()

    images: tuple[ImageItem, ...] = st.session_state.images
    annotations: dict[str, dict[str, Any]] = st.session_state.annotations
    if images:
        available_subsets = sorted(
            {metadata.subset for metadata in st.session_state.original_metadata.values()}
        )
        if available_subsets:
            st.selectbox(
                "Subset",
                ("all", *available_subsets),
                format_func=lambda value: "Todos" if value == "all" else value,
                key="subset_filter",
            )
        subset_images = filter_images(
            images,
            annotations,
            "all",
            st.session_state.annotation_keys,
            st.session_state.original_metadata,
            st.session_state.subset_filter,
        )
        annotated_count = sum(
            st.session_state.annotation_keys.get(image.filename, image.filename) in annotations
            for image in subset_images
        )
        pending_count = len(subset_images) - annotated_count
        st.caption(
            f"{len(subset_images)} imagens neste subset · "
            f"{annotated_count} anotadas"
        )
        st.markdown(f"**Pendentes neste filtro: {pending_count}**")
        if subset_images:
            st.progress(
                annotated_count / len(subset_images),
                text=(
                    f"{annotated_count}/{len(subset_images)} · "
                    f"{annotated_count / len(subset_images):.1%}"
                ),
            )
        selected_filter = st.segmented_control(
            "Filtro",
            FILTER_LABELS,
            key="filter_label",
            width="stretch",
        )
        new_filter = FILTER_LABELS[selected_filter] if selected_filter else "all"
        if new_filter != st.session_state.filter_name:
            st.session_state.filter_name = new_filter
            leave_edit_mode()
    annotation_csv = st.session_state.annotation_csv
    if annotation_csv is not None and annotation_csv.is_file():
        st.download_button("Exportar CSV", data=annotation_csv.read_bytes(), file_name=annotation_csv.name, mime="text/csv", width="stretch")
    st.markdown(f"[Abrir guidelines]({GUIDELINES_PATH.as_uri()})")
    st.caption("Persistência somente ao salvar; escrita atômica.")

notice = st.session_state.pop("notice", None)
if notice:
    st.toast(notice, icon="✅")

images = st.session_state.images
annotations = st.session_state.annotations
if not images:
    st.info("Selecione o diretório e o CSV na barra lateral e clique em **Carregar**.")
    st.stop()

visible_images = filter_images(
    images,
    annotations,
    st.session_state.filter_name,
    st.session_state.annotation_keys,
    st.session_state.original_metadata,
    st.session_state.subset_filter,
)
if not visible_images:
    st.success("Nenhuma imagem corresponde ao filtro atual.")
    st.stop()

visible_names = [image.filename for image in visible_images]
if st.session_state.current_filename not in visible_names:
    st.session_state.current_filename = visible_names[0]
    leave_edit_mode()
current_filename = st.session_state.current_filename
current_index = visible_names.index(current_filename)
current_image = visible_images[current_index]
annotation_filename = st.session_state.annotation_keys.get(current_filename, current_filename)
existing = annotations.get(annotation_filename)
is_editing = existing is None or st.session_state.editing_filename == current_filename

image_column, form_column = st.columns([1.22, 1], gap="large")
with image_column:
    with st.container(key="sticky_image_panel"):
        st.markdown(f"**Imagem {current_index + 1} de {len(visible_images)} neste filtro**  \n`{current_image.filename}`")
        if existing and is_editing:
            st.warning("Status: Editando · alterações só serão gravadas ao salvar")
        elif existing:
            st.success("Status: Anotada")
        else:
            st.info("Status: Não anotada · preenchimento ainda não salvo")
        render_original_metadata(st.session_state.original_metadata.get(current_filename))
        if SEGMENTATION_SPLITS.is_file():
            frozen_test = frozen_test_filenames(
                str(SEGMENTATION_SPLITS), SEGMENTATION_SPLITS.stat().st_mtime_ns
            )
            if current_filename in frozen_test:
                st.warning(
                    "Esta imagem pertence ao test congelado do SegFormer v1. "
                    "Pode ser revisada, mas não deve entrar no próximo treino."
                )
        try:
            spatial_draft_key = render_spatial_panel(
                current_image,
                existing,
                is_editing,
            )
        except Exception as error:  # Streamlit/Pillow apresentam tipos diferentes.
            spatial_draft_key = f"spatial_error_{current_filename}"
            st.session_state[spatial_draft_key] = {"error": str(error)}
            st.error(f"Não foi possível abrir o editor espacial: {error}")
        previous_column, skip_column, next_column = st.columns(3)
        with previous_column:
            if st.button("← Anterior", disabled=current_index == 0, width="stretch"):
                move_selection(visible_images, -1)
                st.rerun()
        with skip_column:
            if st.button("Pular", disabled=current_index == len(visible_images) - 1, width="stretch", help="Avança sem salvar ou alterar a anotação."):
                move_selection(visible_images, 1)
                st.rerun()
        with next_column:
            if st.button("Próxima →", disabled=current_index == len(visible_images) - 1, width="stretch", help="Navega sem salvar. Use “Salvar e próxima” para persistir."):
                move_selection(visible_images, 1)
                st.rerun()

with form_column:
    if existing and not is_editing:
        render_existing_summary(existing, schema, current_filename)
        st.stop()
    render_annotation_editor(
        schema,
        existing,
        current_filename,
        annotation_filename,
        visible_images,
        spatial_draft_key,
    )
