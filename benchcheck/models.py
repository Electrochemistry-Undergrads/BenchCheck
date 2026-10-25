"""Request/response models shared by the API and the analysis code."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ColumnMapping(BaseModel):
    potential: str
    current: str
    time: str | None = None


class Units(BaseModel):
    potential: str = "V"
    current: str = "A"
    time: str = "s"


class Quantity(BaseModel):
    value: float | None = None
    unit: str | None = None


ProcessType = Literal["electrode_material", "dissolved_species", "unknown"]
Solvent = Literal["aqueous", "non-aqueous", "unknown"]


class ExperimentMetadata(BaseModel):
    electrode_material: str | None = None
    process_type: ProcessType = "unknown"
    analyte: str | None = None
    electrolyte: str | None = None  # free text, e.g. "1 M LiCl"
    solvent: Solvent = "unknown"
    reference_electrode: str | None = None  # key of REFERENCE_ELECTRODES
    reference_detail: str | None = None
    scan_rate: Quantity | None = None  # unit "mV/s" or "V/s"
    analyte_concentration: Quantity | None = None  # unit "mM" or "M" (dissolved species)
    active_mass_mg: float | None = None  # electrode materials
    electrode_area_cm2: float | None = None
    temperature_c: float | None = None
    ph: float | None = None
    counter_electrode: str | None = None
    ir_compensation: str | None = None
    diffusion_coefficient_cm2_s: float | None = None
    electrons_n: int | None = None
    notes: str | None = None


class ReferenceConversion(BaseModel):
    target: Literal["SHE", "RHE", "custom"]
    offset_v: float | None = None  # only for target == "custom"
    description: str | None = None
    confirmed: bool = False


class Processing(BaseModel):
    smoothing_mv: float = Field(10.0, ge=0, le=100)
    baseline: Literal["flat_prewave", "linear_prewave", "zero"] = "flat_prewave"


class AnalysisConfig(BaseModel):
    mapping: ColumnMapping
    units: Units = Units()
    current_convention: Literal["iupac", "cathodic_positive"] = "iupac"
    forward_direction: Literal["auto", "positive", "negative"] = "auto"
    selected_cycle: int | None = None
    processing: Processing = Processing()
    metadata: ExperimentMetadata = ExperimentMetadata()
    reference_conversion: ReferenceConversion | None = None
    normalize_by_area: bool = False
    normalize_by_area_confirmed: bool = False
    example_id: str | None = None


class EvidenceContext(BaseModel):
    """What the evidence endpoints need to know about the experiment."""

    metadata: ExperimentMetadata
    hypothesis_ids: list[str] = []
    measured_scan_rate_v_s: float | None = None


class SearchRequest(BaseModel):
    query_id: str
    query: str
    purpose: str | None = None
    hypothesis_ids: list[str] = []
    context: EvidenceContext
    prefer_cache: bool = False


class SelectRequest(BaseModel):
    sources: list[dict]
    context: EvidenceContext


class ExtractRequest(BaseModel):
    source: dict
    context: EvidenceContext
    prefer_cache: bool = False


class ReportRequest(BaseModel):
    analysis: dict
    evidence: dict = {}
