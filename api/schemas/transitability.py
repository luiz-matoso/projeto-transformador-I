from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_passage_width: Literal["wide", "adequate", "narrow"]
    surface_tolerance: Literal["regular_only", "minor_problems", "major_problems"]
    level_change_tolerance: Literal["none", "minor", "step"]
    accepts_partial_obstruction: StrictBool
    requires_ramp_for_transition: StrictBool | None = None
    slope_tolerance: Literal["flat_gentle", "inclined", "steep"] | None = None
    accepts_detour: StrictBool | None = None


class ObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=200)
    observed_at: str | None = Field(default=None, max_length=100)


class TransitabilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profiles: list[ProfileInput] = Field(min_length=1, max_length=8)
    observation: ObservationInput
    validity_hours: float = Field(default=24, gt=0, le=8760, allow_inf_nan=False)


class ReasonOutput(BaseModel):
    feature: str
    observed: Any
    requirement: Any
    impact: Literal["none", "moderate", "critical"]
    code: str
    message: str
    evaluated: bool


class ValidityOutput(BaseModel):
    source: str | None
    observed_at: str | None
    evaluated_at: str
    expires_at: str | None
    validity_seconds: float
    is_valid: bool
    code: str
    message: str


class AssessmentOutput(BaseModel):
    profile_index: int
    profile: ProfileInput
    classification: Literal["transitable", "partially_transitable", "non_transitable", "undetermined"]
    severity: Literal["none", "moderate", "critical"]
    reasons: list[ReasonOutput]
    requires_review: bool
    unassessed_features: list[str]


class MaskOutput(BaseModel):
    encoding: Literal["base64_png"] = "base64_png"
    media_type: Literal["image/png"] = "image/png"
    width: int
    height: int
    data: str


class TransitabilityOutput(BaseModel):
    mask: MaskOutput | None
    features: dict[str, str | list[str]]
    predictions: dict[str, dict[str, Any]]
    observation: ValidityOutput
    not_modeled: dict[str, dict[str, Any]]
    inactive_features: list[str]
    assessments: list[AssessmentOutput]


class HealthOutput(BaseModel):
    status: Literal["ready", "unavailable"]
    models_loaded: bool
    device: str | None
