"""All Pydantic/dataclass models for the entire system."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class RequirementType(str, Enum):
    FEATURE = "feature"
    CONSTRAINT = "constraint"
    DATA_MODEL = "data_model"
    API_CHANGE = "api_change"
    BEHAVIOUR = "behaviour"


class RequirementStatus(str, Enum):
    FULLY_EXISTS = "FULLY_EXISTS"
    PARTIALLY_EXISTS = "PARTIALLY_EXISTS"
    MISSING = "MISSING"
    CONFLICTED = "CONFLICTED"


class Requirement(BaseModel):
    id: str
    description: str
    requirement_type: RequirementType
    priority: Literal["high", "medium", "low"]
    raw_text: str


class SearchResult(BaseModel):
    file_path: str
    chunk_type: str
    name: str
    start_line: int
    end_line: int
    similarity_score: float
    content: str


class ConflictResult(BaseModel):
    affected_files: list[str]
    conflict_severity: Literal["high", "medium", "low"]
    explanation: str


class RequirementAnalysis(BaseModel):
    requirement: Requirement
    status: RequirementStatus
    matched_files: list[str]
    matched_functions: list[str]
    conflict_details: ConflictResult | None = None
    classification_reason: str


class EdgeCase(BaseModel):
    description: str
    related_requirement_id: str | None = None
    severity: Literal["must_discuss", "should_discuss"]


class DataModel(BaseModel):
    name: str
    description: str
    fields: list[str]
    is_new: bool


class APIChange(BaseModel):
    endpoint: str
    method: str
    description: str
    is_new: bool


class IndexResult(BaseModel):
    files_indexed: int
    chunks_created: int
    files_skipped: int
    duration_seconds: float


class EffortEstimate(BaseModel):
    conflict_resolution_hours: float
    extension_hours: float
    net_new_hours: float
    testing_hours: float
    total_days: float
    confidence: Literal["low", "medium", "high"]
    notes: str


class GapReport(BaseModel):
    spec_source: str
    reuse: list[RequirementAnalysis]
    extend: list[RequirementAnalysis]
    conflicts: list[RequirementAnalysis]
    net_new: list[RequirementAnalysis]
    edge_cases: list[EdgeCase]
    data_models: list[DataModel]
    api_changes: list[APIChange]
    implementation_order: list[str]
    effort_estimate: EffortEstimate
    generated_at: datetime = Field(default_factory=datetime.now)
