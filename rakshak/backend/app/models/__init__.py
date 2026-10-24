"""
All Beanie Document models for RakshakAI multi-tenant platform.
"""
from app.models.audit import AuditLog
from app.models.incident import Feedback, Incident, ThresholdHistory
from app.models.organization import Organization, Site
from app.models.privacy import BreakglassGrant
from app.models.rules import RuleDocument
from app.models.signal import AccessEvent, Signal
from app.models.user import (
    ApiKey,
    Invitation,
    PasswordResetToken,
    RefreshSession,
    User,
)
from app.models.zone import Camera, Zone

ALL_DOCUMENT_MODELS = [
    Organization,
    Site,
    User,
    RefreshSession,
    Invitation,
    PasswordResetToken,
    ApiKey,
    Zone,
    Camera,
    Signal,
    AccessEvent,
    Incident,
    Feedback,
    ThresholdHistory,
    RuleDocument,
    BreakglassGrant,
    AuditLog,
]

__all__ = [
    "Organization",
    "Site",
    "User",
    "RefreshSession",
    "Invitation",
    "PasswordResetToken",
    "ApiKey",
    "Zone",
    "Camera",
    "Signal",
    "AccessEvent",
    "Incident",
    "Feedback",
    "ThresholdHistory",
    "RuleDocument",
    "BreakglassGrant",
    "AuditLog",
    "ALL_DOCUMENT_MODELS",
]
