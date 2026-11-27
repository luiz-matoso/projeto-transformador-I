"""Functional questionnaire v1: explicit ordinal translation, separate from visual labels."""
from collections.abc import Mapping
from ml.mobility_profile import MobilityProfile

ABILITIES = ("without_difficulty", "with_difficulty", "unable")
QUESTIONS = {
    "narrow_spaces": "Consegue circular por espaços estreitos?",
    "uneven_surfaces": "Consegue circular sobre pisos irregulares?",
    "small_level_changes": "Consegue superar pequenos desníveis?",
    "steps": "Consegue transpor degraus?",
    "tight_maneuvers": "Consegue realizar manobras em espaços reduzidos?",
    "obstacle_avoidance": "Consegue contornar obstáculos durante o percurso?",
    "inclines": "Consegue circular por superfícies inclinadas?",
}
WIDTH = dict(zip(ABILITIES, ("narrow", "adequate", "wide")))
SURFACE = dict(zip(ABILITIES, ("major_problems", "minor_problems", "regular_only")))
COMPLEMENTARY = ("tight_maneuvers", "requires_ramps", "inclines", "accepts_detours")
TRANSLATION_NOTES = (
    "Tradução qualitativa experimental, sem medidas físicas ou garantia de acessibilidade.",
    "Para contornar obstáculos e transpor um mesmo nível, Sem dificuldade e Com dificuldade compartilham o limite atual; dificuldades observadas continuam sendo registradas pelo motor.",
)

def functional_requirements(answers: Mapping) -> MobilityProfile:
    expected = {"schema_version", "wheelchair_type", "assistance", *QUESTIONS, "requires_ramps", "accepts_detours"}
    if set(answers) != expected or type(answers.get("schema_version")) is not int or answers["schema_version"] != 1:
        raise ValueError("Questionário funcional incompleto ou incompatível")
    if answers["wheelchair_type"] not in ("manual", "powered") or answers["assistance"] not in ("none", "partial", "constant"):
        raise ValueError("Identificação funcional inválida")
    if any(answers[k] not in ABILITIES for k in QUESTIONS):
        raise ValueError("Resposta funcional inválida")
    if any(type(answers[k]) is not bool for k in ("requires_ramps", "accepts_detours")):
        raise ValueError("As necessidades complementares exigem Sim ou Não")
    small, steps = answers["small_level_changes"], answers["steps"]
    if small == "unable" and steps != "unable":
        raise ValueError("Revise as respostas: transpor degraus pressupõe conseguir superar pequenos desníveis neste perfil ordinal")
    level = "none" if small == "unable" else "minor" if steps == "unable" else "step"
    return MobilityProfile(WIDTH[answers["narrow_spaces"]], SURFACE[answers["uneven_surfaces"]], level,
                           answers["obstacle_avoidance"] != "unable")

def functional_spec():
    return {"version": 1, "questions": QUESTIONS,
            "abilities": dict(zip(ABILITIES, ("Sem dificuldade", "Com dificuldade", "Não consegue"))),
            "wheelchair_types": {"manual": "Manual", "powered": "Motorizada"},
            "assistance": {"none": "Nenhuma", "partial": "Parcial", "constant": "Constante"},
            "complementary": list(COMPLEMENTARY), "notes": list(TRANSLATION_NOTES),
            "mapping": {"minimum_passage_width": WIDTH, "surface_tolerance": SURFACE,
                        "level_change_tolerance": "Não supera pequenos desníveis → nenhum; supera pequenos, mas não degraus → pequeno; supera ambos → degrau",
                        "accepts_partial_obstruction": "Não consegue contornar → não aceita; demais respostas → aceita com dificuldade moderada quando observada"}}
