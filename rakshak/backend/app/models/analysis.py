"""
Analysis Job Document model for on-demand media uploads and live stream analysis.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisJob(Document):
    org_id: str = Field(..., description="Parent organization ID")
    job_id: str = Field(default_factory=lambda: uuid4().hex, description="Unique job identifier")
    type: str = Field(..., description="video | audio | live")
    camera_id: Optional[str] = Field(default=None, description="Camera ID for video / live analysis")
    zone_id: Optional[str] = Field(default=None, description="Zone ID for audio / live analysis")
    status: str = Field(default="queued", description="queued | running | done | failed | cancelled")
    progress: int = Field(default=0, ge=0, le=100, description="Job progress percentage 0-100")
    signals_count: int = Field(default=0, description="Number of security signals emitted")
    incident_ids: List[str] = Field(default_factory=list, description="IDs of incidents created or updated")
    annotated_video_path: Optional[str] = Field(default=None, description="Relative path to annotated skeleton MP4")
    original_filename: Optional[str] = Field(default=None, description="Sanitized original filename")
    stored_path: Optional[str] = Field(default=None, description="Internal storage path on disk")
    error: Optional[str] = Field(default=None, description="Failure reason if failed")
    created_by: str = Field(..., description="Email of user who submitted the job")
    created_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Settings:
        name = "analysis_jobs"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("job_id", ASCENDING)], unique=True),
            IndexModel([("org_id", ASCENDING), ("created_at", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
        ]
