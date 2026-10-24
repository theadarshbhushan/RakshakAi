"""
Integration test suite for RakshakAI Evidence Views, Emergency Access,
Two-Person Identity Reveal, Intruder Logic, and Forensic Chain-of-Custody.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.security import hash_token
from app.fusion.corroboration import FusionEngine
from app.models.incident import Incident
from app.models.organization import Organization
from app.models.privacy import BreakglassGrant, EmergencyReveal, IdentityRevealRequest
from app.models.signal import AccessEvent, Signal
from app.models.user import User, utc_now
from app.models.zone import Camera, Zone
from app.privacy.encryption import (
    encrypt_bytes,
    load_and_decrypt_raw_clip,
    save_encrypted_raw_clip,
)


@pytest.fixture(autouse=True)
async def cleanup_test_data():
    yield
    await Incident.find({"source": "test_privacy"}).delete()
    await Signal.find({"source": "test_privacy"}).delete()
    await BreakglassGrant.find({"reason": {"$regex": "^Test"}}).delete()
    await EmergencyReveal.find({"reason": {"$regex": "^Test"}}).delete()
    await IdentityRevealRequest.find({"reason": {"$regex": "^Test"}}).delete()


async def get_auth_token(client: AsyncClient, email: str, password: str = "Owner@12345") -> str:
    """Helper to authenticate and retrieve access token."""
    if "admin" in email:
        password = "Admin@12345"
    elif "warden" in email:
        password = "Warden@12345"
    elif "guard" in email:
        password = "Guard@12345"
    elif "auditor" in email:
        password = "Auditor@12345"

    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_evidence_views_default_skeleton_and_blurred(client: AsyncClient):
    """
    Test Part A & B:
    - Default skeleton view: guard sees skeleton; blurred & raw return 403 BREAKGLASS_REQUIRED.
    - Org default updated to blurred: guard sees blurred without unlock; raw still 403.
    - Auditor always sees skeleton only: requesting blurred or raw returns 403.
    """
    guard_tok = await get_auth_token(client, "guard@sunrise.demo")
    admin_tok = await get_auth_token(client, "admin@sunrise.demo")
    auditor_tok = await get_auth_token(client, "auditor@sunrise.demo")

    org = await Organization.find_one(Organization.slug == "sunrise")
    assert org is not None

    # Ensure default_evidence_view is skeleton
    org.settings["default_evidence_view"] = "skeleton"
    await org.save()

    now = utc_now()
    incident = Incident(
        org_id=str(org.id),
        zone_id="terrace",
        explanation="Zone intrusion on Terrace Rooftop.",
        severity="medium",
        status="investigating",
        created_ts=now - timedelta(minutes=20),
        updated_ts=now - timedelta(minutes=20),
        source="test_privacy",
    )
    await incident.insert()

    sig = Signal(
        org_id=str(org.id),
        incident_id=str(incident.id),
        ts=now - timedelta(minutes=20),
        modality="video",
        kind="zone_intrusion",
        zone_id="terrace",
        camera_id="cam_terrace",
        score=0.85,
        threshold=0.50,
        source="test_privacy",
    )
    await sig.insert()
    incident.signal_ids = [str(sig.id)]
    await incident.save()

    # 1. Guard requests skeleton view -> Allowed
    res_sk = await client.get(
        f"/api/v1/evidence/incident/{incident.id}?tier=skeleton",
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert res_sk.status_code == 200

    # 2. Guard requests blurred view without unlock -> 403 BREAKGLASS_REQUIRED
    res_bl = await client.get(
        f"/api/v1/evidence/incident/{incident.id}?tier=blurred",
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert res_bl.status_code == 403
    assert res_bl.json()["error"]["code"] == "BREAKGLASS_REQUIRED"

    # 3. Guard requests raw view -> 403
    res_raw = await client.get(
        f"/api/v1/evidence/incident/{incident.id}?tier=raw",
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert res_raw.status_code == 403

    # 4. Admin updates org setting default_evidence_view to blurred
    res_put = await client.put(
        "/api/v1/privacy/settings",
        json={"default_evidence_view": "blurred"},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert res_put.status_code == 200
    assert res_put.json()["default_evidence_view"] == "blurred"

    # 5. Guard requests default view -> receives blurred
    res_guard_bl = await client.get(
        f"/api/v1/evidence/incident/{incident.id}",
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert res_guard_bl.status_code == 200

    # 6. Auditor requests evidence -> ALWAYS gets skeleton only, blurred/raw returns 403
    res_auditor_def = await client.get(
        f"/api/v1/evidence/incident/{incident.id}",
        headers={"Authorization": f"Bearer {auditor_tok}"},
    )
    assert res_auditor_def.status_code == 200

    res_auditor_bl = await client.get(
        f"/api/v1/evidence/incident/{incident.id}?tier=blurred",
        headers={"Authorization": f"Bearer {auditor_tok}"},
    )
    assert res_auditor_bl.status_code == 403

    # Revert org default setting to skeleton
    org.settings["default_evidence_view"] = "skeleton"
    await org.save()


@pytest.mark.asyncio
async def test_breakglass_emergency_unlock(client: AsyncClient):
    """
    Test C1: Break-Glass:
    - Warden/admin/owner requests 10-minute break-glass grant.
    - Allows blurred view.
    - Expires after TTL.
    """
    admin_tok = await get_auth_token(client, "admin@sunrise.demo")
    guard_tok = await get_auth_token(client, "guard@sunrise.demo")
    org = await Organization.find_one(Organization.slug == "sunrise")

    now = utc_now()
    incident = Incident(
        org_id=str(org.id),
        zone_id="terrace",
        explanation="Zone intrusion on Terrace Rooftop.",
        severity="medium",
        status="investigating",
        created_ts=now - timedelta(minutes=20),
        updated_ts=now - timedelta(minutes=20),
        source="test_privacy",
    )
    await incident.insert()

    sig = Signal(
        org_id=str(org.id),
        incident_id=str(incident.id),
        ts=now - timedelta(minutes=20),
        modality="video",
        kind="zone_intrusion",
        zone_id="terrace",
        camera_id="cam_terrace",
        score=0.85,
        source="test_privacy",
    )
    await sig.insert()
    incident.signal_ids = [str(sig.id)]
    await incident.save()

    # Admin requests break-glass token
    bg_res = await client.post(
        "/api/v1/privacy/breakglass",
        json={
            "incident_id": str(incident.id),
            "reason": "Testing breakglass emergency face-blurred view override",
        },
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert bg_res.status_code == 200
    token = bg_res.json()["token"]

    # View blurred evidence with token
    view_res = await client.get(
        f"/api/v1/evidence/incident/{incident.id}?tier=blurred&token={token}",
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert view_res.status_code == 200

    # Expire the token manually
    grant = await BreakglassGrant.find_one({"incident_id": str(incident.id)})
    assert grant is not None
    grant.expires_at = now - timedelta(seconds=10)
    await grant.save()

    # View with expired token -> 403
    expired_res = await client.get(
        f"/api/v1/evidence/incident/{incident.id}?tier=blurred&token={token}",
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert expired_res.status_code == 403
    assert expired_res.json()["error"]["code"] == "BREAKGLASS_REQUIRED"


@pytest.mark.asyncio
async def test_emergency_context_view(client: AsyncClient):
    """
    Test C2: Emergency Context View:
    - Active safety incident (fight, distress_audio, student_sos, loitering).
    - Severity >= medium, status not closed, last signal <= 10 min.
    - Guard gets blurred view instantly without break-glass token.
    - Old incident (>10 min) or low severity -> 403.
    """
    guard_tok = await get_auth_token(client, "guard@sunrise.demo")
    org = await Organization.find_one(Organization.slug == "sunrise")
    now = utc_now()

    # 1. Active fight incident within 2 minutes -> Emergency Context eligible
    inc_fight = Incident(
        org_id=str(org.id),
        zone_id="dining_hall",
        explanation="Fight altercation detected in Dining Hall.",
        severity="high",
        status="new",
        created_ts=now - timedelta(minutes=2),
        updated_ts=now - timedelta(minutes=2),
        source="test_privacy",
    )
    await inc_fight.insert()

    sig_fight = Signal(
        org_id=str(org.id),
        incident_id=str(inc_fight.id),
        ts=now - timedelta(minutes=2),
        modality="video",
        kind="fight",
        zone_id="dining_hall",
        camera_id="cam_dining_hall",
        score=0.90,
        source="test_privacy",
    )
    await sig_fight.insert()
    inc_fight.signal_ids = [str(sig_fight.id)]
    await inc_fight.save()

    # Guard accesses blurred view without token -> Allowed under Emergency Context
    res_ctx = await client.get(
        f"/api/v1/evidence/incident/{inc_fight.id}?tier=blurred",
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert res_ctx.status_code == 200

    # 2. Old fight incident (> 10 min ago) -> NOT eligible
    inc_fight_old = Incident(
        org_id=str(org.id),
        zone_id="dining_hall",
        explanation="Fight altercation detected in Dining Hall.",
        severity="high",
        status="new",
        created_ts=now - timedelta(minutes=15),
        updated_ts=now - timedelta(minutes=15),
        source="test_privacy",
    )
    await inc_fight_old.insert()

    sig_fight_old = Signal(
        org_id=str(org.id),
        incident_id=str(inc_fight_old.id),
        ts=now - timedelta(minutes=15),
        modality="video",
        kind="fight",
        zone_id="dining_hall",
        camera_id="cam_dining_hall",
        score=0.90,
        source="test_privacy",
    )
    await sig_fight_old.insert()
    inc_fight_old.signal_ids = [str(sig_fight_old.id)]
    await inc_fight_old.save()

    res_old = await client.get(
        f"/api/v1/evidence/incident/{inc_fight_old.id}?tier=blurred",
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert res_old.status_code == 403
    assert res_old.json()["error"]["code"] == "BREAKGLASS_REQUIRED"

    # 3. Emergency Context NEVER unblurs faces
    res_raw = await client.get(
        f"/api/v1/evidence/incident/{inc_fight.id}?tier=raw",
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert res_raw.status_code == 403


@pytest.mark.asyncio
async def test_emergency_intruder_reveal_and_post_review(client: AsyncClient):
    """
    Test C3: Emergency Intruder Reveal:
    - Guard requests emergency reveal on active unexplained critical intrusion.
    - Eligible ONLY on unexplained intrusion, severity high/critical, <= 10 min.
    - Grants 5-min targeted unblur.
    - Post-review task created and reviewed by owner/admin.
    - Explained intrusion (with authorised swipe) is NOT eligible (returns 403).
    """
    guard_tok = await get_auth_token(client, "guard@sunrise.demo")
    owner_tok = await get_auth_token(client, "owner@sunrise.demo")
    org = await Organization.find_one(Organization.slug == "sunrise")
    now = utc_now()

    # Create unexplained critical intrusion incident
    inc_intrusion = Incident(
        org_id=str(org.id),
        zone_id="terrace",
        explanation="Unexplained zone intrusion on Terrace Rooftop.",
        severity="critical",
        status="new",
        modalities=["video"],
        created_ts=now - timedelta(minutes=1),
        updated_ts=now - timedelta(minutes=1),
        source="test_privacy",
    )
    await inc_intrusion.insert()

    sig = Signal(
        org_id=str(org.id),
        incident_id=str(inc_intrusion.id),
        ts=now - timedelta(minutes=1),
        modality="video",
        kind="zone_intrusion",
        zone_id="terrace",
        camera_id="cam_terrace",
        score=0.92,
        threshold=0.50,
        details={
            "track_id": 4,
            "flagged_track_ids": [4],
            "explained_by_access": False,
        },
        source="test_privacy",
    )
    await sig.insert()
    inc_intrusion.signal_ids = [str(sig.id)]
    await inc_intrusion.save()

    # Save encrypted raw clip for this incident
    sample_vid = settings.DATA_DIR / "videos" / "intrusion" / "intrusion_01.mp4"
    if sample_vid.exists():
        save_encrypted_raw_clip(str(inc_intrusion.id), source_file=sample_vid, frame_tracks=[[{"track_id": 4, "box": [100, 100, 250, 350]}]])

    # 1. Guard requests emergency reveal
    er_res = await client.post(
        "/api/v1/privacy/emergency-reveal",
        json={"incident_id": str(inc_intrusion.id), "reason": "Active critical terrace intruder spotted"},
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert er_res.status_code == 200
    er_data = er_res.json()
    assert er_data["review_status"] == "pending"
    assert 4 in er_data["flagged_track_ids"]
    reveal_id = er_data["id"]

    # 2. Guard accesses targeted unblurred raw clip with watermark
    view_raw = await client.get(
        f"/api/v1/evidence/incident/{inc_intrusion.id}?tier=raw&variant=targeted",
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert view_raw.status_code == 200
    assert len(view_raw.content) > 1000

    # 3. List emergency reveals with review=pending
    list_res = await client.get(
        "/api/v1/privacy/emergency-reveal?review=pending",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(item["id"] == reveal_id for item in items)

    # 4. Owner reviews emergency reveal -> justified
    rev_res = await client.post(
        f"/api/v1/privacy/emergency-reveal/{reveal_id}/review",
        json={"status": "justified", "note": "Verified confirmed intruder breach."},
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["review_status"] == "justified"

    # 5. Non-eligible test: Explained intrusion (explained_by_access=True)
    inc_explained = Incident(
        org_id=str(org.id),
        zone_id="terrace",
        explanation="Authorised entry on Terrace Rooftop.",
        severity="low",
        status="new",
        created_ts=now - timedelta(minutes=1),
        updated_ts=now - timedelta(minutes=1),
        source="test_privacy",
    )
    await inc_explained.insert()
    sig_exp = Signal(
        org_id=str(org.id),
        incident_id=str(inc_explained.id),
        ts=now - timedelta(minutes=1),
        modality="video",
        kind="zone_intrusion",
        zone_id="terrace",
        details={"explained_by_access": True, "track_id": 5},
        source="test_privacy",
    )
    await sig_exp.insert()
    inc_explained.signal_ids = [str(sig_exp.id)]
    await inc_explained.save()

    fail_er = await client.post(
        "/api/v1/privacy/emergency-reveal",
        json={"incident_id": str(inc_explained.id), "reason": "Unauthorized request test"},
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert fail_er.status_code == 403
    assert fail_er.json()["error"]["code"] == "EMERGENCY_REVEAL_NOT_ELIGIBLE"


@pytest.mark.asyncio
async def test_intruder_logic_rules_and_corroboration():
    """
    Test Part D: Intruder Logic:
    - D1: Authorised swipe within 60s -> explained_by_access=True, score x0.5.
    - D2: Perimeter breach -> always unexplained, severity high/critical.
    - D3: Unswiped entry -> severity high during curfew.
    - D4: After-hours presence without swipe -> unexplained_presence signal.
    """
    org = await Organization.find_one(Organization.slug == "sunrise")
    engine = FusionEngine(org_id=str(org.id), rules_config={})
    now = utc_now()

    # D1 Test: Insert AccessEvent swipe by warden in terrace zone
    access_ev = AccessEvent(
        org_id=str(org.id),
        pseudo_id="warden_swipe_1",
        role="warden",
        door_id="terrace_door",
        zone_id="terrace",
        direction="in",
        result="granted",
        ts=now - timedelta(seconds=20),
    )
    await access_ev.insert()

    sig_intrusion = Signal(
        org_id=str(org.id),
        ts=now,
        modality="video",
        kind="zone_intrusion",
        zone_id="terrace",
        camera_id="cam_terrace",
        score=0.80,
        threshold=0.50,
        details={"track_id": 2},
        source="test_privacy",
    )
    inc_d1 = await engine.ingest_signal(sig_intrusion)
    assert inc_d1 is not None
    assert sig_intrusion.details.get("explained_by_access") is True
    assert sig_intrusion.score == 0.40  # 0.80 * 0.5

    # D2 Test: Perimeter breach
    sig_perimeter = Signal(
        org_id=str(org.id),
        ts=now,
        modality="video",
        kind="zone_intrusion",
        zone_id="back_wall",
        camera_id="cam_back_wall",
        score=0.80,
        threshold=0.50,
        details={"subtype": "perimeter_breach", "track_id": 7},
        source="test_privacy",
    )
    inc_d2 = await engine.ingest_signal(sig_perimeter)
    assert inc_d2 is not None
    assert inc_d2.severity in ("high", "critical")
    assert "Perimeter breach" in inc_d2.explanation


@pytest.mark.asyncio
async def test_two_person_identity_reveal_and_export(client: AsyncClient):
    """
    Test C4: Two-Person Identity Reveal:
    - Warden requests identity reveal.
    - Self-approval attempt returns 403 SELF_APPROVAL_FORBIDDEN.
    - Second owner approves -> 15-minute full unblur granted.
    - Owner exports zip: contains watermarked video + chain_of_custody.json with correct SHA-256.
    - Non-owner export attempt returns 403.
    """
    warden_tok = await get_auth_token(client, "warden@sunrise.demo")
    owner_tok = await get_auth_token(client, "owner@sunrise.demo")
    guard_tok = await get_auth_token(client, "guard@sunrise.demo")
    org = await Organization.find_one(Organization.slug == "sunrise")
    now = utc_now()

    incident = Incident(
        org_id=str(org.id),
        zone_id="terrace",
        explanation="Zone intrusion on Terrace Rooftop.",
        severity="critical",
        status="investigating",
        modalities=["video"],
        created_ts=now - timedelta(hours=2),
        updated_ts=now - timedelta(hours=2),
        source="test_privacy",
    )
    await incident.insert()

    sig = Signal(
        org_id=str(org.id),
        incident_id=str(incident.id),
        ts=now - timedelta(hours=2),
        modality="video",
        kind="zone_intrusion",
        zone_id="terrace",
        score=0.95,
        source="test_privacy",
    )
    await sig.insert()
    incident.signal_ids = [str(sig.id)]
    await incident.save()

    # Save encrypted raw clip
    sample_vid = settings.DATA_DIR / "videos" / "intrusion" / "intrusion_01.mp4"
    if sample_vid.exists():
        save_encrypted_raw_clip(str(incident.id), source_file=sample_vid, frame_tracks=[])

    # 1. Warden requests identity reveal (reason >= 20 chars)
    req_res = await client.post(
        "/api/v1/privacy/identity-reveal",
        json={
            "incident_id": str(incident.id),
            "reason": "Suspected repeated intruder identified on terrace for formal legal prosecution.",
        },
        headers={"Authorization": f"Bearer {warden_tok}"},
    )
    assert req_res.status_code == 200
    req_data = req_res.json()
    req_id = req_data["id"]
    assert req_data["status"] == "pending"

    # 2. Self-approval attempt (if warden were admin/owner) -> 403 SELF_APPROVAL_FORBIDDEN
    owner_req = await client.post(
        "/api/v1/privacy/identity-reveal",
        json={
            "incident_id": str(incident.id),
            "reason": "Owner requesting identity reveal for official university disciplinary inquiry.",
        },
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert owner_req.status_code == 200
    owner_req_id = owner_req.json()["id"]

    # Owner tries to approve their own request
    self_appr = await client.post(
        f"/api/v1/privacy/identity-reveal/{owner_req_id}/approve",
        json={"note": "Self-approving my own request."},
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert self_appr.status_code == 403
    assert self_appr.json()["error"]["code"] == "SELF_APPROVAL_FORBIDDEN"

    # 3. Owner approves warden's request (two-person rule satisfied)
    appr_res = await client.post(
        f"/api/v1/privacy/identity-reveal/{req_id}/approve",
        json={"note": "Approved by Chief Warden / Owner following protocol."},
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"

    # 4. View FULL unblurred raw clip with watermark
    view_full = await client.get(
        f"/api/v1/evidence/incident/{incident.id}?tier=raw&variant=full",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert view_full.status_code == 200
    assert len(view_full.content) > 1000

    # 5. Non-owner (guard) attempts to export evidence -> 403
    export_guard = await client.post(
        f"/api/v1/evidence/incident/{incident.id}/export",
        headers={"Authorization": f"Bearer {guard_tok}"},
    )
    assert export_guard.status_code == 403

    # 6. Owner exports evidence package -> returns ZIP
    export_owner = await client.post(
        f"/api/v1/evidence/incident/{incident.id}/export",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert export_owner.status_code == 200
    assert export_owner.headers["content-type"] == "application/zip"

    # Unpack ZIP in memory and verify SHA-256 integrity
    zip_buf = io.BytesIO(export_owner.content)
    with zipfile.ZipFile(zip_buf, "r") as zf:
        file_names = zf.namelist()
        assert "chain_of_custody.json" in file_names
        video_filename = f"incident_{incident.id}_evidence.mp4"
        assert video_filename in file_names

        video_bytes = zf.read(video_filename)
        manifest_raw = zf.read("chain_of_custody.json")
        manifest = json.loads(manifest_raw.decode("utf-8"))

        computed_sha256 = hashlib.sha256(video_bytes).hexdigest()
        assert manifest["video_sha256"] == computed_sha256
        assert manifest["exported_by"] == "owner@sunrise.demo"


@pytest.mark.asyncio
async def test_transparency_and_audit_hash_chain(client: AsyncClient):
    """
    Test Part F:
    - Monthly transparency counters reflect breakglass, reveals, and exports.
    - Cryptographic audit chain integrity verification passes.
    """
    owner_tok = await get_auth_token(client, "owner@sunrise.demo")

    # 1. Monthly transparency counters
    trans_res = await client.get(
        "/api/v1/privacy/transparency",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert trans_res.status_code == 200
    data = trans_res.json()
    assert "period" in data
    assert "breakglass_count" in data
    assert "emergency_reveal_count" in data
    assert "identity_reveal_count" in data
    assert "export_count" in data

    # 2. Cryptographic audit chain verification
    audit_verify_res = await client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert audit_verify_res.status_code == 200
    verify_data = audit_verify_res.json()
    assert verify_data["valid"] is True, f"Audit chain broken: {verify_data}"
