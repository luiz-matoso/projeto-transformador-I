from dataclasses import dataclass
from typing import Any

from tools.annotation_app.core import AnnotationSchema, FieldDefinition


FIELD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PASSAGEM", ("passage_width", "obstruction", "obstacle_type")),
    ("SUPERFÍCIE", ("surface_condition", "surface_obstacle", "level_change")),
    ("ACESSO", ("ramp_condition", "curb_access")),
    ("ROTA", ("detour", "path_continuity", "slope")),
    ("ANOTAÇÃO", ("annotation_confidence",)),
)

# Somente apresentação: as chaves continuam sendo os valores do schema/CSV.
OPTION_LABELS: dict[str, dict[str, str]] = {
    "passage_width": {"wide": "Ampla", "adequate": "Adequada", "narrow": "Estreita", "very_narrow": "Muito estreita", "blocked": "Bloqueada", "unknown": "Não é possível determinar"},
    "obstruction": {"none": "Nenhuma", "partial": "Parcial", "full": "Total", "unknown": "Não é possível determinar"},
    "obstacle_type": {"vehicle": "Veículo", "bike_scooter": "Bicicleta / patinete", "pole": "Poste", "sign": "Placa", "tree": "Árvore", "vegetation": "Vegetação", "trash_container": "Lixeira", "construction": "Obra", "stairs": "Escada / degraus", "litter_debris": "Lixo / entulho", "utility": "Equipamento urbano", "street_furniture": "Mobiliário urbano", "other": "Outro"},
    "surface_condition": {"regular": "Regular", "minor_problem": "Problema leve", "major_problem": "Problema grave", "unknown": "Não é possível determinar"},
    "surface_obstacle": {"cracks": "Rachaduras", "bumpy": "Piso irregular", "uneven_slanted": "Desnivelado / inclinado", "height_difference": "Diferença de altura", "very_broken": "Muito quebrado", "grass": "Grama", "sand_gravel": "Areia / cascalho", "brick_cobblestone": "Tijolo / paralelepípedo", "pooled_water": "Água acumulada", "rail_track": "Trilho", "utility_panel": "Tampa / caixa de utilidade", "debris": "Detritos", "other": "Outro"},
    "level_change": {"none": "Nenhuma", "minor": "Pequena", "step": "Degrau / meio-fio", "unknown": "Não é possível determinar"},
    "ramp_condition": {"not_applicable": "Não se aplica", "clear": "Livre", "problematic": "Com problema", "blocked": "Bloqueada", "missing_required": "Necessária e ausente", "unknown": "Não é possível determinar"},
    "curb_access": {"not_applicable": "Não se aplica", "level": "Nivelado", "ramp": "Com rampa", "raised_no_ramp": "Elevado sem rampa", "blocked": "Bloqueado", "unknown": "Não é possível determinar"},
    "detour": {"not_needed": "Não necessário", "available": "Disponível", "unavailable": "Indisponível", "unknown": "Não é possível determinar"},
    "path_continuity": {"continuous": "Contínua", "restricted": "Restrita", "interrupted": "Interrompida", "unknown": "Não é possível determinar"},
    "slope": {"flat_gentle": "Plana / suave", "inclined": "Inclinada", "steep": "Íngreme", "unknown": "Não é possível determinar"},
    "annotation_confidence": {"high": "Alta", "medium": "Média", "low": "Baixa"},
}


@dataclass(frozen=True)
class CompletionStatus:
    completed: int
    total: int
    pending: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return not self.pending


def option_label(field_name: str, value: str) -> str:
    return OPTION_LABELS.get(field_name, {}).get(value, value)


def validate_presentation(schema: AnnotationSchema) -> None:
    """Garante que grupos e traduções acompanham exatamente o schema atual."""
    grouped = tuple(name for _, names in FIELD_GROUPS for name in names)
    if grouped != schema.field_names:
        raise ValueError("Os grupos visuais não correspondem à ordem do schema")
    for field in schema.fields:
        translated = OPTION_LABELS.get(field.name, {})
        if set(translated) != set(field.option_values):
            raise ValueError(f"Mapeamento visual incompleto ou excedente para {field.name}")


def completion_status(
    schema: AnnotationSchema,
    values: dict[str, Any],
    empty_confirmations: dict[str, bool],
) -> CompletionStatus:
    """Resume campos obrigatórios preenchidos sem alterar a validação de domínio."""
    pending: list[str] = []
    required_fields = tuple(field for field in schema.fields if field.required)
    for field in required_fields:
        value = values.get(field.name)
        complete = (
            value in field.option_values
            if field.kind == "single-label"
            else bool(value) or bool(empty_confirmations.get(field.name))
        )
        if not complete:
            pending.append(field.display_name)
    return CompletionStatus(
        completed=len(required_fields) - len(pending),
        total=len(required_fields),
        pending=tuple(pending),
    )


def field_help(field: FieldDefinition) -> str:
    lines = [field.description, ""]
    lines.extend(
        f"- **{option_label(field.name, option.value)}:** {option.definition}"
        for option in field.options
    )
    if field.empty_means:
        lines.append(f"- **Nenhum:** {field.empty_means}")
    return "\n".join(lines)
