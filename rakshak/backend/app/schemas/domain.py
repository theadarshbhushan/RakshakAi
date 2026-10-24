"""
Pydantic schemas for Signals, Incidents, Calibration, Privacy, Audit, Usage, and Pagination.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    next_cursor: Optional[str] = None
    total: Optional[int] = None


# Signal Schemas
class SignalCreateRequest(BaseModel):
    modality: str = Field(..., description="video | audio | access")
    kind: str = Field(..., description="zone_intrusion | fight | line_crossing | tailgating | distress_audio | curfew_violation | restricted_access")
    zone_id: str
    site_id: Optional[str] = None
    camera_id: Optional[str] = None
    score: float = 1.0
    threshold: float = 0.5
    details: Dict[str, Any] = Field(default_factory=dict)
    suppressed: bool = False
    suppress_reason: Optional[str] = None
    evidence_path: Optional[str] = None
    source: str = Field(default="edge_device")


class SignalResponse(BaseModel):
    id: str
    org_id: str
    site_id: Optional[str] = None
    ts: datetime
    modality: str
    kind: str
    zone_id: str
    camera_id: Optional[str] = None
    score: float
    threshold: float
    details: Dict[str, Any]
    suppressed: bool
    suppress_reason: Optional[str] = None
    evidence_path: Optional[str] = None
    incident_id: Optional[str] = None
    source: str


# Incident Schemas
class IncidentReviewRequest(BaseModel):
    label: str = Field(..., description="confirmed | false_alarm | investigating")
    note: Optional[str] = Field(None, description="Required for confirmed and false_alarm")


class IncidentResponse(BaseModel):
    id: str
    org_id: str
    site_id: Optional[str] = None
    created_ts: datetime
    updated_ts: datetime
    zone_id: str
    severity: str
    composite_score: float
    modalities: List[str]
    signal_ids: List[str]
    explanation: str
    status: str
    acknowledged_by: Optional[str] = None
    acknowledged_ts: Optional[datetime] = None
    escalated: bool
    reviewer: Optional[str] = None
    review_note: Optional[str] = None
    reviewed_ts: Optional[datetime] = None
    signals: Optional[List[SignalResponse]] = None
    access_events: Optional[List[Dict[str, Any]]] = None


# Calibration Schemas
class ThresholdHistoryResponse(BaseModel):
    id: str
    zone_id: str
    detector: str
    old_value: float
    new_value: float
    reason: str
    ts: datetime
    reverted: bool
    changed_by: Optional[str] = None


class CalibrationOverviewResponse(BaseModel):
    thresholds: Dict[str, Dict[str, float]]
    history: List[ThresholdHistoryResponse]


# Privacy & Breakglass Schemas
class BreakglassRequest(BaseModel):
    incident_id: str
    reason: str = Field(..., min_length=10, description="Audit justification (min 10 chars)")


class BreakglassResponse(BaseModel):
    token: str
    expires_at: datetime
    incident_id: str


class PrivacySettingsRequest(BaseModel):
    retention_days: int = Field(..., ge=1, le=365)


class PrivacyInventoryResponse(BaseModel):
    document_counts: Dict[str, int]
    evidence_storage: Dict[str, Any]
    timestamp: str


# Audit Schemas
class AuditLogResponse(BaseModel):
    seq: int
    ts: datetime
    actor: Dict[str, Any]
    action: str
    target: str
    reason: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    prev_hash: str
    hash: str


class AuditVerifyResponse(BaseModel):
    valid: bool
    total_records: int
    broken_at_seq: Optional[int] = None
    message: str


# Usage & Plans Schemas
class UsageResponse(BaseModel):
    plan: str
    limits: Dict[str, Any]
    current_counts: Dict[str, int]
    incidents_this_month: int
    signals_this_month: int
