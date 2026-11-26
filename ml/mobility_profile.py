from dataclasses import dataclass


@dataclass(frozen=True)
class MobilityProfile:
    minimum_passage_width: str
    surface_tolerance: str
    level_change_tolerance: str
    accepts_partial_obstruction: bool
    requires_ramp_for_transition: bool | None = None
    slope_tolerance: str | None = None
    accepts_detour: bool | None = None

    def __post_init__(self):
        options = {
            "minimum_passage_width": ("wide", "adequate", "narrow"),
            "surface_tolerance": ("regular_only", "minor_problems", "major_problems"),
            "level_change_tolerance": ("none", "minor", "step"),
            "slope_tolerance": (None, "flat_gentle", "inclined", "steep"),
        }
        for name, allowed in options.items():
            if getattr(self, name) not in allowed:
                raise ValueError(f"Valor inválido no perfil: {name}")
        if type(self.accepts_partial_obstruction) is not bool:
            raise ValueError("accepts_partial_obstruction deve ser booleano")
        for name in ("requires_ramp_for_transition", "accepts_detour"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise ValueError(f"{name} deve ser booleano ou None")
