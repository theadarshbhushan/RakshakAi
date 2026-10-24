"""
Comprehensive Test Suite for Media Input & Live Analysis (/api/v1/analyze).
Tests:
- Upload validation: rejects .exe, rejects oversized payload (>200MB)
- RBAC: blocks guard from uploading (403 Forbidden)
- Tenant isolation: jobs created by Org A are not visible or accessible to Org B
- Live webcam / RTSP control: owner/admin permissions and start/stop
- Real Mode Integration tests:
  1. Upload intrusion_01.mp4 to cam_terrace at sim_start 23:40 -> job done -> zone_intrusion -> incident created -> annotated MP4 served -> raw upload deleted
  2. Upload distress scream WAV to terrace -> distress signal -> incident created
  3. Upload laughing WAV to terrace -> suppressed signal -> no incident created
"""
import asyncio
import io
import os
from pathlib import Path
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.detectors.synthetic_media import ensure_media_fixtures, generate_audio_file
from app.models.analysis import AnalysisJob
from app.models.incident import Incident
from app.models.signal import Signal


async def get_token(client: AsyncClient, email: str, password: str = "Owner@12345") -> str:
    """Helper to authenticate and retrieve access token."""
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["access_token"]


# =============================================================================
# 1. Unit Test: Upload validation rejects .exe and invalid content types
# =============================================================================
@pytest.mark.asyncio
async def test_upload_validation_rejects_exe(client: AsyncClient):
    token = await get_token(client, "owner@sunrise.demo")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Reject .exe file
    exe_file = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00malicious_binary")
    res = await client.post(
        "/api/v1/analyze/upload",
        files={"file": ("malware.exe", exe_file, "application/x-msdownload")},
        data={"camera_id": "cam_terrace"},
        headers=headers,
    )
    assert res.status_code == 400
    assert "Unsupported and unsafe file extension" in res.text

    # 2. Reject unsupported extension
    txt_file = io.BytesIO(b"hello world")
    res2 = await client.post(
        "/api/v1/analyze/upload",
        files={"file": ("notes.txt", txt_file, "text/plain")},
        data={"camera_id": "cam_terrace"},
        headers=headers,
    )
    assert res2.status_code == 400
    assert "Unsupported file format" in res2.text


# =============================================================================
# 2. Unit Test: Upload validation rejects oversized file (> MAX_UPLOAD_SIZE_MB)
# =============================================================================
@pytest.mark.asyncio
async def test_upload_validation_rejects_oversized_file(client: AsyncClient, monkeypatch):
    token = await get_token(client, "owner@sunrise.demo")
    headers = {"Authorization": f"Bearer {token}"}

    # Temporarily set max upload size to 1 MB for testing payload rejection
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)

    # 1.5 MB payload
    large_payload = io.BytesIO(b"0" * (1536 * 1024))
    res = await client.post(
        "/api/v1/analyze/upload",
        files={"file": ("oversized.mp4", large_payload, "video/mp4")},
        data={"camera_id": "cam_terrace"},
        headers=headers,
    )
    assert res.status_code == 413
    assert "exceeds maximum allowed size" in res.text


# =============================================================================
# 3. Unit Test: RBAC blocks guard from uploading (403 Forbidden)
# =============================================================================
@pytest.mark.asyncio
async def test_rbac_guard_cannot_upload(client: AsyncClient):
    guard_token = await get_token(client, "guard@sunrise.demo", "Guard@12345")
    headers = {"Authorization": f"Bearer {guard_token}"}

    dummy_video = io.BytesIO(b"dummy video data")
    res = await client.post(
        "/api/v1/analyze/upload",
        files={"file": ("sample.mp4", dummy_video, "video/mp4")},
        data={"camera_id": "cam_terrace"},
        headers=headers,
    )
    assert res.status_code == 403
    assert "Permission 'scenarios:run' required" in res.text


# =============================================================================
# 4. Unit Test: Strict tenant isolation on analysis jobs
# =============================================================================
@pytest.mark.asyncio
async def test_tenant_isolation_on_jobs(client: AsyncClient):
    # Tenant 1: Sunrise
    token_sunrise = await get_token(client, "owner@sunrise.demo")
    headers_sunrise = {"Authorization": f"Bearer {token_sunrise}"}

    # Tenant 2: Green Valley
    token_gv = await get_token(client, "owner@greenvalley.demo")
    headers_gv = {"Authorization": f"Bearer {token_gv}"}

    # Create dummy video upload in Sunrise
    video_bytes = io.BytesIO(b"fake mp4 header bytes")
    create_res = await client.post(
        "/api/v1/analyze/upload",
        files={"file": ("test_clip.mp4", video_bytes, "video/mp4")},
        data={"camera_id": "cam_terrace"},
        headers=headers_sunrise,
    )
    assert create_res.status_code == 202
    job_id = create_res.json()["job_id"]

    # Green Valley cannot access Sunrise's job by ID -> 404
    get_gv_res = await client.get(f"/api/v1/analyze/jobs/{job_id}", headers=headers_gv)
    assert get_gv_res.status_code == 404

    # Green Valley cannot cancel Sunrise's job -> 404
    del_gv_res = await client.delete(f"/api/v1/analyze/jobs/{job_id}", headers=headers_gv)
    assert del_gv_res.status_code == 404

    # Green Valley job list does not contain Sunrise job_id
    list_gv_res = await client.get("/api/v1/analyze/jobs", headers=headers_gv)
    assert list_gv_res.status_code == 200
    gv_job_ids = [j["job_id"] for j in list_gv_res.json()]
    assert job_id not in gv_job_ids


# =============================================================================
# 5. Live Analysis: Owner/Admin controls and guard blocking
# =============================================================================
@pytest.mark.asyncio
async def test_live_analysis_controls(client: AsyncClient):
    guard_token = await get_token(client, "guard@sunrise.demo", "Guard@12345")
    owner_token = await get_token(client, "owner@sunrise.demo")

    # Guard blocked from starting live analysis
    res_guard = await client.post(
        "/api/v1/analyze/live",
        json={"camera_id": "cam_terrace", "source": "webcam:0"},
        headers={"Authorization": f"Bearer {guard_token}"},
    )
    assert res_guard.status_code == 403

    # Owner can start live analysis
    res_owner = await client.post(
        "/api/v1/analyze/live",
        json={"camera_id": "cam_terrace", "source": "webcam:0"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res_owner.status_code == 200
    assert res_owner.json()["status"] == "started"

    # Owner can stop live analysis
    res_stop = await client.post(
        "/api/v1/analyze/live/cam_terrace/stop",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res_stop.status_code == 200
    assert res_stop.json()["status"] == "stopped"


# =============================================================================
# 6. Integration (Real Mode): Video Upload -> Intrusion -> Incident & Annotated MP4
# =============================================================================
@pytest.mark.asyncio
async def test_real_mode_video_upload_intrusion(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "DETECTOR_MODE", "real")
    ensure_media_fixtures(settings.DATA_DIR)

    video_fixture = settings.DATA_DIR / "videos" / "intrusion" / "intrusion_01.mp4"
    assert video_fixture.exists(), f"Fixture {video_fixture} missing"

    token = await get_token(client, "owner@sunrise.demo")
    headers = {"Authorization": f"Bearer {token}"}

    with open(video_fixture, "rb") as vf:
        upload_res = await client.post(
            "/api/v1/analyze/upload",
            files={"file": ("intrusion_01.mp4", vf, "video/mp4")},
            data={"camera_id": "cam_terrace", "sim_start": "23:40"},
            headers=headers,
        )
    assert upload_res.status_code == 202
    job_id = upload_res.json()["job_id"]

    # Poll job status until done or timeout (max 30s)
    for _ in range(60):
        await asyncio.sleep(0.5)
        st_res = await client.get(f"/api/v1/analyze/jobs/{job_id}", headers=headers)
        assert st_res.status_code == 200
        job_data = st_res.json()
        if job_data["status"] in ("done", "failed"):
            break

    assert job_data["status"] == "done", f"Job failed: {job_data.get('error')}"
    assert job_data["progress"] == 100
    assert job_data["signals_count"] > 0
    assert len(job_data["incident_ids"]) > 0

    # Verify incident created
    inc = await Incident.find_one({"_id": job_data["incident_ids"][0]})
    if not inc:
        # Search by string id if needed
        inc = await Incident.get(job_data["incident_ids"][0])
    assert inc is not None
    assert inc.zone_id == "terrace"
    assert inc.severity in ("medium", "high", "critical")

    # Verify annotated MP4 served via authenticated endpoint
    ann_res = await client.get(f"/api/v1/analyze/jobs/{job_id}/annotated", headers=headers)
    assert ann_res.status_code == 200
    assert ann_res.headers.get("content-type") == "video/mp4"
    assert len(ann_res.content) > 1000

    # Verify privacy enforcement: raw uploaded file deleted
    db_job = await AnalysisJob.find_one(AnalysisJob.job_id == job_id)
    assert db_job.stored_path is None


# =============================================================================
# 7. Integration (Real Mode): Scream Audio Upload -> Distress Signal & Incident
# =============================================================================
@pytest.mark.asyncio
async def test_real_mode_audio_upload_distress(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "DETECTOR_MODE", "real")
    ensure_media_fixtures(settings.DATA_DIR)

    distress_fixture = settings.DATA_DIR / "audio" / "distress" / "distress_01.wav"
    assert distress_fixture.exists()

    token = await get_token(client, "owner@sunrise.demo")
    headers = {"Authorization": f"Bearer {token}"}

    with open(distress_fixture, "rb") as af:
        upload_res = await client.post(
            "/api/v1/analyze/upload",
            files={"file": ("scream.wav", af, "audio/wav")},
            data={"zone_id": "terrace"},
            headers=headers,
        )
    assert upload_res.status_code == 202
    job_id = upload_res.json()["job_id"]

    for _ in range(40):
        await asyncio.sleep(0.5)
        st_res = await client.get(f"/api/v1/analyze/jobs/{job_id}", headers=headers)
        assert st_res.status_code == 200
        job_data = st_res.json()
        if job_data["status"] in ("done", "failed"):
            break

    assert job_data["status"] == "done", f"Job failed: {job_data.get('error')}"
    assert job_data["signals_count"] > 0
    assert len(job_data["incident_ids"]) > 0

    # Verify distress audio signal exists with source="upload"
    distress_sig = await Signal.find_one({
        "org_id": job_data["org_id"],
        "kind": "distress_audio",
        "source": "upload",
    })
    assert distress_sig is not None
    assert distress_sig.score >= 0.35


# =============================================================================
# 8. Integration (Real Mode): Laughing Audio Upload -> Suppressed -> No Incident
# =============================================================================
@pytest.mark.asyncio
async def test_real_mode_audio_upload_laughing_suppressed(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "DETECTOR_MODE", "real")

    # Generate a pure laughing WAV file
    laugh_fixture = settings.DATA_DIR / "audio" / "hard_negative" / "test_laughing.wav"
    generate_audio_file(laugh_fixture, sound_type="laughter", duration_s=3.0)

    token = await get_token(client, "owner@sunrise.demo")
    headers = {"Authorization": f"Bearer {token}"}

    with open(laugh_fixture, "rb") as af:
        upload_res = await client.post(
            "/api/v1/analyze/upload",
            files={"file": ("laughing.wav", af, "audio/wav")},
            data={"zone_id": "terrace"},
            headers=headers,
        )
    assert upload_res.status_code == 202
    job_id = upload_res.json()["job_id"]

    for _ in range(40):
        await asyncio.sleep(0.5)
        st_res = await client.get(f"/api/v1/analyze/jobs/{job_id}", headers=headers)
        assert st_res.status_code == 200
        job_data = st_res.json()
        if job_data["status"] in ("done", "failed"):
            break

    assert job_data["status"] == "done", f"Job failed: {job_data.get('error')}"
    # Suppressed audio signals do NOT create incidents!
    assert len(job_data["incident_ids"]) == 0
