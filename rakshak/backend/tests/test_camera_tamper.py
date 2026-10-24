"""
Integration and logic tests for Camera Tamper Detection, Health Monitoring,
and Blind-Spot Compensation.

1. Camera health: health_status (ok | degraded | tampered | offline), health_reason, last_frame_at.
   GET /api/v1/cameras includes it; WebSocket event camera.health_changed.
2. Blind-spot compensation:
   - While camera is tampered or offline, zone is marked as a blind spot.
   - Distress audio threshold temporarily lowered by 0.1 (floor 0.2) with reason "blind_spot_compensation".
   - Student SOS or access violation in blind spot zone treated as at least high severity.
   - Automatically reverted when camera recovers to "ok".
   - Never modifies permanent calibration history (ThresholdHistory).
3. Tamper incident narrative:
   "Camera cam_terrace covered (brightness 6). Zone Terrace is a blind spot; audio sensitivity raised and patrol priority increased."
4. Patrol plan: blind-spot zones go to top with reason "camera not functioning".
"""
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from app.models.incident import Incident, ThresholdHistory
from app.models.organization import Organization
from app.models.rules import RuleDocument
from app.models.signal import Signal
from app.models.zone import Camera, Zone
from app.fusion.corroboration import FusionEngine
from app.services.camera_health_service import CameraHealthService


@pytest.fixture(autouse=True)
async def cleanup_test_records():
    yield
    await Incident.find({"source": {"$in": ["test", "camera_tamper_test"]}}).delete()
    await Signal.find({"source": {"$in": ["test", "camera_tamper_test"]}}).delete()


@pytest.mark.asyncio
async def test_camera_health_update_and_listing(client: AsyncClient):
    """Camera health status update endpoint and GET /api/v1/cameras."""
    # 1. Login as Sunrise admin
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@sunrise.demo", "password": "Owner@12345"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    org = await Organization.find_one(Organization.slug == "sunrise")
    assert org is not None

    # 2. Get cameras
    get_res = await client.get("/api/v1/cameras", headers=headers)
    assert get_res.status_code == 200
    cameras = get_res.json()
    assert len(cameras) > 0
    cam = next((c for c in cameras if c["camera_id"] == "cam_terrace"), cameras[0])
    cam_id = cam["camera_id"]

    # 3. Update camera health to tampered
    now_iso = datetime.now(timezone.utc).isoformat()
    health_payload = {
        "health_status": "tampered",
        "health_reason": "dark",
        "last_frame_at": now_iso,
    }
    update_res = await client.post(
        f"/api/v1/cameras/{cam_id}/health",
        json=health_payload,
        headers=headers,
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["health_status"] == "tampered"
    assert updated_data["health_reason"] == "dark"

    # 4. Verify GET /api/v1/cameras reflects health
    get_res2 = await client.get("/api/v1/cameras", headers=headers)
    assert get_res2.status_code == 200
    cam_after = next(c for c in get_res2.json() if c["camera_id"] == cam_id)
    assert cam_after["health_status"] == "tampered"
    assert cam_after["health_reason"] == "dark"
    assert cam_after["last_frame_at"] is not None

    # Reset back to ok
    await client.post(
        f"/api/v1/cameras/{cam_id}/health",
        json={"health_status": "ok"},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_tamper_sets_blind_spot_and_lowers_threshold_and_recovery_reverts(client: AsyncClient):
    """
    Tamper sets blind spot and lowers distress_audio threshold by 0.1.
    Recovery reverts it back.
    ThresholdHistory is NEVER modified.
    """
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@sunrise.demo", "password": "Owner@12345"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    org = await Organization.find_one(Organization.slug == "sunrise")
    assert org is not None
    org_id = str(org.id)

    # Find terrace camera and zone
    camera = await Camera.find_one({"org_id": org_id, "camera_id": "cam_terrace"})
    assert camera is not None
    zone_id = camera.zone_id

    zone = await Zone.find_one({"org_id": org_id, "zone_id": zone_id})
    assert zone is not None

    # Ensure rule document exists for org
    rules_doc = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
    assert rules_doc is not None
    if zone_id not in rules_doc.zones:
        rules_doc.zones[zone_id] = {"thresholds": {"distress_audio": 0.35}}
        await rules_doc.save()

    orig_threshold = float(rules_doc.zones[zone_id].get("thresholds", {}).get("distress_audio", 0.35))

    # Baseline ThresholdHistory count
    initial_history_count = await ThresholdHistory.find(ThresholdHistory.org_id == org_id).count()

    # --- 1. SET CAMERA TO TAMPERED ---
    with patch("app.services.camera_health_service.ws_hub.broadcast_to_org", new_callable=AsyncMock) as mock_ws:
        await client.post(
            f"/api/v1/cameras/{camera.camera_id}/health",
            json={"health_status": "tampered", "health_reason": "dark"},
            headers=headers,
        )
        mock_ws.assert_called_once()
        call_kwargs = mock_ws.call_args.kwargs
        assert call_kwargs["event_type"] == "camera.health_changed"
        assert call_kwargs["data"]["health_status"] == "tampered"
        assert call_kwargs["data"]["is_blind_spot"] is True

    # Verify zone is marked as blind spot
    updated_zone = await Zone.find_one({"org_id": org_id, "zone_id": zone_id})
    assert updated_zone.is_blind_spot is True
    assert updated_zone.blind_spot_reason == "dark"
    assert updated_zone.blind_spot_adjustments is not None
    assert updated_zone.blind_spot_adjustments["reason"] == "blind_spot_compensation"

    # Verify threshold in RuleDocument lowered by 0.1
    updated_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
    z_conf = updated_rules.zones[zone_id]
    expected_lowered = max(0.20, round(orig_threshold - 0.10, 2))
    assert z_conf["thresholds"]["distress_audio"] == expected_lowered
    assert "blind_spot_compensation" in z_conf
    assert z_conf["blind_spot_compensation"]["reason"] == "blind_spot_compensation"

    # CRITICAL: ThresholdHistory count MUST NOT change
    mid_history_count = await ThresholdHistory.find(ThresholdHistory.org_id == org_id).count()
    assert mid_history_count == initial_history_count, "Blind spot compensation must NEVER modify ThresholdHistory!"

    # Verify GET /api/v1/zones returns blind spot
    zones_res = await client.get("/api/v1/zones", headers=headers)
    assert zones_res.status_code == 200
    z_res = next(z for z in zones_res.json() if z["zone_id"] == zone_id)
    assert z_res["is_blind_spot"] is True
    assert z_res["blind_spot_reason"] == "dark"

    # --- 2. RECOVERY: SET CAMERA BACK TO OK ---
    with patch("app.services.camera_health_service.ws_hub.broadcast_to_org", new_callable=AsyncMock) as mock_ws_rec:
        await client.post(
            f"/api/v1/cameras/{camera.camera_id}/health",
            json={"health_status": "ok"},
            headers=headers,
        )
        mock_ws_rec.assert_called_once()
        call_kwargs = mock_ws_rec.call_args.kwargs
        assert call_kwargs["event_type"] == "camera.health_changed"
        assert call_kwargs["data"]["health_status"] == "ok"
        assert call_kwargs["data"]["is_blind_spot"] is False

    # Verify zone is no longer blind spot
    recovered_zone = await Zone.find_one({"org_id": org_id, "zone_id": zone_id})
    assert recovered_zone.is_blind_spot is False
    assert recovered_zone.blind_spot_reason is None
    assert recovered_zone.blind_spot_adjustments is None

    # Verify threshold restored in RuleDocument
    recovered_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
    rec_conf = recovered_rules.zones[zone_id]
    assert rec_conf["thresholds"]["distress_audio"] == orig_threshold
    assert "blind_spot_compensation" not in rec_conf

    # CRITICAL: ThresholdHistory still NOT touched
    final_history_count = await ThresholdHistory.find(ThresholdHistory.org_id == org_id).count()
    assert final_history_count == initial_history_count, "Recovery must NEVER modify ThresholdHistory!"


@pytest.mark.asyncio
async def test_threshold_floor_enforcement():
    """Verify distress_audio threshold lowering respects the floor of 0.20."""
    org = await Organization.find_one(Organization.slug == "sunrise")
    assert org is not None
    org_id = str(org.id)

    camera = await Camera.find_one({"org_id": org_id, "camera_id": "cam_terrace"})
    assert camera is not None

    rules_doc = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
    assert rules_doc is not None
    # Set to 0.25 (lower by 0.1 -> 0.15, but floor is 0.20)
    rules_doc.zones[camera.zone_id] = {"thresholds": {"distress_audio": 0.25}}
    await rules_doc.save()

    await CameraHealthService.update_camera_health(
        org_id=org_id,
        camera_id=camera.camera_id,
        health_status="offline",
        health_reason="no frames",
    )

    updated_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
    assert updated_rules.zones[camera.zone_id]["thresholds"]["distress_audio"] == 0.20

    # Revert
    await CameraHealthService.update_camera_health(
        org_id=org_id,
        camera_id=camera.camera_id,
        health_status="ok",
    )
    reverted_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
    assert reverted_rules.zones[camera.zone_id]["thresholds"]["distress_audio"] == 0.25


@pytest.mark.asyncio
async def test_tamper_incident_explanation_and_blind_spot_severity():
    """
    3. Tamper incidents explain this:
       'Camera cam_terrace covered (brightness 6). Zone Terrace is a blind spot; audio sensitivity raised and patrol priority increased.'
    2. Student SOS or access violation in a blind spot treated as at least high severity.
    """
    org = await Organization.find_one(Organization.slug == "sunrise")
    assert org is not None
    org_id = str(org.id)

    zone = await Zone.find_one({"org_id": org_id, "zone_id": "terrace"})
    assert zone is not None
    orig_name = zone.name
    zone.name = "Terrace"
    await zone.save()

    # Clear any previous test signals/incidents in terrace zone
    await Signal.find({"org_id": org_id, "zone_id": "terrace"}).delete()
    await Incident.find({"org_id": org_id, "zone_id": "terrace"}).delete()

    fusion = FusionEngine(org_id=org_id, rules_config={})

    # Ingest camera_tamper signal
    now = datetime.now(timezone.utc)
    tamper_sig = Signal(
        org_id=org_id,
        ts=now,
        modality="video",
        kind="camera_tamper",
        zone_id="terrace",
        camera_id="cam_terrace",
        score=0.95,
        threshold=0.50,
        details={
            "tamper_type": "covered",
            "metric": "brightness 6",
        },
        source="camera_tamper_test",
    )

    incident = await fusion.ingest_signal(tamper_sig)
    assert incident is not None
    assert incident.explanation == "Camera cam_terrace covered (brightness 6). Zone Terrace is a blind spot; audio sensitivity raised and patrol priority increased."

    # While terrace is now marked as blind spot:
    zone = await Zone.find_one({"org_id": org_id, "zone_id": "terrace"})
    assert zone.is_blind_spot is True

    # Test student SOS in blind spot -> severity must be at least high
    sos_sig = Signal(
        org_id=org_id,
        ts=now,
        modality="report",
        kind="student_sos",
        zone_id="terrace",
        score=0.9,
        details={"type": "unsafe"},
        source="camera_tamper_test",
    )
    composite_sos = fusion.calculate_composite_score([sos_sig])
    sev_sos = fusion.determine_severity([sos_sig], composite_sos, is_blind_spot=True)
    assert sev_sos in ("high", "critical")

    # Test access violation (restricted_access, curfew_violation, tailgating) in blind spot -> at least high
    for kind in ["restricted_access", "curfew_violation", "tailgating"]:
        acc_sig = Signal(
            org_id=org_id,
            ts=now,
            modality="access",
            kind=kind,
            zone_id="terrace",
            score=0.7,
            source="camera_tamper_test",
        )
        comp_acc = fusion.calculate_composite_score([acc_sig])
        sev_acc = fusion.determine_severity([acc_sig], comp_acc, is_blind_spot=True)
        assert sev_acc in ("high", "critical"), f"{kind} in blind spot must be at least high, got {sev_acc}"

    # Clean up camera state and zone name
    zone.name = orig_name
    await zone.save()
    await CameraHealthService.update_camera_health(
        org_id=org_id,
        camera_id="cam_terrace",
        health_status="ok",
    )


@pytest.mark.asyncio
async def test_patrol_plan_blind_spot_at_top(client: AsyncClient):
    """
    4. Patrol plan: blind-spot zones go to the top with reason 'camera not functioning'.
    """
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@sunrise.demo", "password": "Owner@12345"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    org = await Organization.find_one(Organization.slug == "sunrise")
    assert org is not None
    org_id = str(org.id)

    # Set terrace camera to offline
    await CameraHealthService.update_camera_health(
        org_id=org_id,
        camera_id="cam_terrace",
        health_status="offline",
        health_reason="no frames",
    )

    # Request patrol plan
    plan_res = await client.get(
        "/api/v1/analytics/patrol-plan?shift_start=22:00&shift_end=06:00",
        headers=headers,
    )
    assert plan_res.status_code == 200
    data = plan_res.json()
    plan = data["plan"]
    assert len(plan) > 0

    # The top zone MUST be terrace and marked is_blind_spot=True
    top_zone = plan[0]
    assert top_zone["zone_id"] == "terrace"
    assert top_zone["is_blind_spot"] is True
    assert "camera not functioning" in top_zone["reason"]

    # Revert camera
    await CameraHealthService.update_camera_health(
        org_id=org_id,
        camera_id="cam_terrace",
        health_status="ok",
    )
