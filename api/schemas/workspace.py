from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from api.schemas.transitability import ProfileInput, TransitabilityOutput, FunctionalProfileInput

class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    name: str = Field(min_length=1, max_length=80)
    requirements: ProfileInput | None = None
    functional: FunctionalProfileInput | None = None

    @model_validator(mode="after")
    def translate(self):
        if self.functional is not None:
            from dataclasses import asdict
            from ml.functional_profile import functional_requirements
            expected = ProfileInput(**asdict(functional_requirements(self.functional.model_dump())))
            if self.requirements is not None and self.requirements != expected:
                raise ValueError("Requisitos incompatíveis com as respostas funcionais")
            self.requirements = expected
        if self.requirements is None:
            raise ValueError("Informe respostas funcionais ou preserve os requisitos anteriores")
        return self

    @field_validator("requirements")
    @classmethod
    def active_only(cls, value):
        if value is not None and any(getattr(value, name) is not None for name in ("requires_ramp_for_transition", "slope_tolerance", "accepts_detour")):
            raise ValueError("Campo ainda não suportado pelo Workspace")
        return value

class ProfileRecord(ProfileWrite):
    model_config = ConfigDict(extra="ignore")
    created_at: datetime
    updated_at: datetime

class AnalysisWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    profiles: list[ProfileWrite] = Field(min_length=2, max_length=2)
    result: TransitabilityOutput

    @field_validator("result")
    @classmethod
    def pair(cls, value):
        if len(value.assessments) != 2 or [a.profile_index for a in value.assessments] != [0, 1]:
            raise ValueError("São necessárias duas avaliações ordenadas")
        if not value.observation.is_valid and (value.mask is not None or value.features or value.predictions):
            raise ValueError("Observação inválida não pode conter inferência")
        return value

class AnalysisSaved(BaseModel):
    id: UUID
    status: Literal["complete"]

class AnalysisSummary(BaseModel):
    id: UUID
    created_at: datetime
    profiles: list[ProfileWrite]
    status: Literal["complete", "deleting"]

class AnalysisDetail(BaseModel):
    id: UUID
    created_at: datetime
    profiles: list[ProfileWrite]
    result: TransitabilityOutput
    model_versions: dict[str, dict[str, str]]
    image_url: str
    mask_url: str | None
