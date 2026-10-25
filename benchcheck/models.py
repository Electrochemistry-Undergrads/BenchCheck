"""Request/response models shared by the API and the analysis code."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RequestModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_max_length=500)


class ColumnMapping(RequestModel):
    potential: str
    current: str
    time: str | None = None

    @model_validator(mode="after")
    def distinct(self):
        roles = [self.potential, self.current] + ([self.time] if self.time else [])
        if len(set(roles)) != len(roles):
            raise ValueError("mapping potential, current and time must use different columns")
        return self


class Units(RequestModel):
    potential: str | None = None
    current: str | None = None
    time: str | None = None


class Quantity(RequestModel):
    value: float | None = Field(None, gt=0)
    unit: str | None = None


ProcessType = Literal["electrode_material", "dissolved_species", "unknown"]
Solvent = Literal["aqueous", "non-aqueous", "unknown"]


class ExperimentMetadata(RequestModel):
    electrode_material: str | None = None
    process_type: ProcessType = "unknown"
    analyte: str | None = None
    electrolyte: str | None = None  # free text, e.g. "1 M LiCl"
    solvent: Solvent = "unknown"
    reference_electrode: str | None = None  # key of REFERENCE_ELECTRODES
    reference_detail: str | None = None
    scan_rate: Quantity | None = None  # unit "mV/s" or "V/s"
    analyte_concentration: Quantity | None = None  # unit "mM" or "M" (dissolved species)
    active_mass_mg: float | None = Field(None, gt=0)  # electrode materials
    electrode_area_cm2: float | None = Field(None, gt=0)
    temperature_c: float | None = Field(None, gt=-273.15)
    ph: float | None = None
    counter_electrode: str | None = None
    ir_compensation: str | None = None
    diffusion_coefficient_cm2_s: float | None = Field(None, gt=0)
    electrons_n: int | None = Field(None, ge=1)
    notes: str | None = None

    @field_validator("reference_electrode")
    @classmethod
    def known_reference(cls, value):
        from .cv.reference import REFERENCE_ELECTRODES
        if value and value not in REFERENCE_ELECTRODES:
            raise ValueError(f"Unknown reference electrode {value!r}")
        return value

    @field_validator("scan_rate", "analyte_concentration")
    @classmethod
    def quantity_unit(cls, value, info):
        if value and value.value is not None:
            allowed = {"V/s", "mV/s"} if info.field_name == "scan_rate" else {"M", "mM", "µM", "μM", "uM", "nM", "mol/L", "mmol/L"}
            if value.unit not in allowed:
                raise ValueError(f"{info.field_name}.unit must be one of {', '.join(sorted(allowed))}")
        return value


class ReferenceConversion(RequestModel):
    target: Literal["SHE", "RHE", "custom"]
    offset_v: float | None = Field(None, ge=-5, le=5)  # only for target == "custom"
    description: str | None = None
    confirmed: bool = False

    @model_validator(mode="after")
    def offset_for_custom_only(self):
        if self.target != "custom" and self.offset_v is not None:
            raise ValueError("reference_conversion.offset_v is only allowed for a custom conversion")
        return self


class Processing(RequestModel):
    smoothing_mv: float = Field(10.0, ge=0, le=100)
    baseline: Literal["flat_prewave", "linear_prewave", "zero"] = "flat_prewave"


class AnalysisConfig(RequestModel):
    mapping: ColumnMapping
    units: Units | None = Field(default_factory=Units)
    current_convention: Literal["iupac", "cathodic_positive"] = "iupac"
    forward_direction: Literal["auto", "positive", "negative"] = "auto"
    selected_cycle: int | None = None
    processing: Processing = Processing()
    metadata: ExperimentMetadata = ExperimentMetadata()
    reference_conversion: ReferenceConversion | None = None
    normalize_by_area: bool = False
    normalize_by_area_confirmed: bool = False
    example_id: str | None = None


class EvidenceContext(RequestModel):
    """What the evidence endpoints need to know about the experiment."""

    metadata: ExperimentMetadata
    hypothesis_ids: list[str] = []
    measured_scan_rate_v_s: float | None = None


class SearchRequest(RequestModel):
    analysis_id: str | None = None
    query_id: str
    query: str = Field(min_length=1, max_length=300)

    @field_validator("query", mode="before")
    @classmethod
    def trim_query(cls, value):
        return value.strip() if isinstance(value, str) else value
    purpose: str | None = None
    hypothesis_ids: list[str] = []
    context: EvidenceContext
    prefer_cache: bool = False


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_id: str = Field(min_length=1, max_length=200)
    title: str = Field(max_length=2000)
    link: str | None = Field(None, max_length=3000)


class SelectRequest(RequestModel):
    analysis_id: str | None = None
    sources: list[SourceInput] = Field(max_length=100)
    context: EvidenceContext


class ExtractRequest(RequestModel):
    analysis_id: str | None = None
    source: SourceInput
    context: EvidenceContext
    prefer_cache: bool = False


class ConversionPreviewRequest(RequestModel):
    from_: str | None = Field(None, alias="from")
    target: Literal["SHE", "RHE", "custom"] = "SHE"
    ph: float | None = None
    temperature_c: float | None = Field(None, gt=-273.15)
    offset_v: float | None = Field(None, ge=-5, le=5)
    description: str | None = None

    _known_reference = field_validator("from_")(classmethod(ExperimentMetadata.known_reference.__func__))

    @model_validator(mode="after")
    def offset_for_custom_only(self):
        if self.target != "custom" and self.offset_v is not None:
            raise ValueError("offset_v is only allowed for a custom conversion")
        return self


class ReportRequest(RequestModel):
    analysis_id: str | None = None
    analysis: dict = {}
    evidence: dict = {}
