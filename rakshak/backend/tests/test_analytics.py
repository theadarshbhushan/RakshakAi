"""
Integration tests for Risk Analytics:
1. False alarms reduce risk score (severity_weight x review_weight: confirmed=1.0 vs false_alarm=0.1)
2. Strict tenant isolation between organizations (Sunrise vs Green Valley)
3. Patrol plan ordering based on shift risk and real-time boosts (open incidents, camera tamper, SOS)
4. Historical demo retention and removable via POST /scenarios/reset?include_history=true
5. Summary metrics (SLA averages, false-alarm rate, top incident kinds)
"""
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient

from app.models.incident import Incident
from app.models.organization import Organization
from app.models.signal import Signal
from app.models.zone import Zone
from scripts.seed_history import seed_history


@pytest.fixture(autouse=True)
async def cleanup_history_after_test():
    yield
    await Incident.find({"source": {"$in": ["seed_history", "test"]}}).delete()
    await Signal.find({"source": {"$in": ["seed_history", "test"]}}).delete()


@pytest.mark.asyncio
async def test_false_alarms_reduce_risk_score(client: AsyncClient):
    # Authenticate as Sunrise owner
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@sunrise.demo", "password": "Owner@12345"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Fetch sunrise org and a zone
    org = await Organization.find_one(Organization.slug == "sunrise")
    assert org is not None
    zone = await Zone.find_one(Zone.org_id == str(org.id))
    assert zone is not None

    # Clear previous test incidents in this zone
    await Incident.find({"org_id": str(org.id), "zone_id": zone.zone_id}).delete()

    now = datetime.now(timezone.utc)

    # 1. Test Confirmed Incident: critical (4.0) * confirmed (1.0) = 4.0
    inc_confirmed = Incident(
        org_id=str(org.id),
        zone_id=zone.zone_id,
        severity="critical",
        status="confirmed",
        created_ts=now,
        updated_ts=now,
        source="test",
    )
    await inc_confirmed.insert()

    res1 = await client.get("/api/v1/analytics/heatmap?days=1", headers=auth_headers)
    assert res1.status_code == 200
    data1 = res1.json()
    zone_data1 = data1["per_zone"][zone.zone_id]
    assert zone_data1["confirmed"] == 1
    assert zone_data1["false_alarms"] == 0
    assert zone_data1["risk_score"] == 4.0

    # 2. Update to False Alarm: critical (4.0) * false_alarm (0.1) = 0.4
    inc_confirmed.status = "false_alarm"
    await inc_confirmed.save()

    res2 = await client.get("/api/v1/analytics/heatmap?days=1", headers=auth_headers)
    assert res2.status_code == 200
    data2 = res2.json()
    zone_data2 = data2["per_zone"][zone.zone_id]
    assert zone_data2["confirmed"] == 0
    assert zone_data2["false_alarms"] == 1
    # False alarm risk score is 0.4 (90% reduction compared to 4.0)
    assert zone_data2["risk_score"] == 0.4
    assert zone_data2["risk_score"] < zone_data1["risk_score"]


@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient):
    # 1. Sunrise login
    sunrise_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@sunrise.demo", "password": "Owner@12345"},
    )
    assert sunrise_login.status_code == 200
    sunrise_token = sunrise_login.json()["access_token"]

    # 2. Green Valley login
    gv_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@greenvalley.demo", "password": "Owner@12345"},
    )
    assert gv_login.status_code == 200
    gv_token = gv_login.json()["access_token"]

    # Seed history for Sunrise
    await seed_history(close_when_done=False)

    # Sunrise should see its populated heatmap & patrol plan
    sunrise_heat = await client.get("/api/v1/analytics/heatmap?days=30", headers={"Authorization": f"Bearer {sunrise_token}"})
    assert sunrise_heat.status_code == 200
    sunrise_data = sunrise_heat.json()
    assert sunrise_data["total"]["incident_count"] > 0
    assert sunrise_data["total"]["risk_score"] > 0

    # Green Valley must see 0 incidents, 0 risk score, and no Sunrise zones
    gv_heat = await client.get("/api/v1/analytics/heatmap?days=30", headers={"Authorization": f"Bearer {gv_token}"})
    assert gv_heat.status_code == 200
    gv_data = gv_heat.json()
    assert gv_data["total"]["incident_count"] == 0
    assert gv_data["total"]["risk_score"] == 0.0
    for z in gv_data["zones"]:
        assert z["total"]["incident_count"] == 0

    # Summary isolation
    gv_summary = await client.get("/api/v1/analytics/summary?days=30", headers={"Authorization": f"Bearer {gv_token}"})
    assert gv_summary.status_code == 200
    assert gv_summary.json()["total_incidents"] == 0

    # Patrol plan isolation
    gv_plan = await client.get("/api/v1/analytics/patrol-plan?shift_start=22:00&shift_end=06:00", headers={"Authorization": f"Bearer {gv_token}"})
    assert gv_plan.status_code == 200
    for p in gv_plan.json()["plan"]:
        assert p["risk_score"] == 0.0


@pytest.mark.asyncio
async def test_patrol_plan_ordering(client: AsyncClient):
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "warden@sunrise.demo", "password": "Warden@12345"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Ensure history is seeded
    await seed_history(close_when_done=False)

    org = await Organization.find_one(Organization.slug == "sunrise")
    assert org is not None

    # Inject a camera tamper signal in terrace within last 24h
    now = datetime.now(timezone.utc)
    tamper_sig = Signal(
        org_id=str(org.id),
        zone_id="terrace",
        modality="video",
        kind="camera_tamper",
        score=0.9,
        ts=now - timedelta(hours=12),
        source="test",
    )
    await tamper_sig.insert()

    # Query patrol plan for overnight shift 22:00 to 06:00
    res = await client.get(
        "/api/v1/analytics/patrol-plan?shift_start=22:00&shift_end=06:00&days=30",
        headers=auth_headers,
    )
    assert res.status_code == 200
    plan_data = res.json()
    plan_list = plan_data["plan"]
    assert len(plan_list) >= 2

    # Check descending order of risk_score
    scores = [item["risk_score"] for item in plan_list]
    assert scores == sorted(scores, reverse=True)

    # Top zone should be Terrace because of historical late night concentration + tamper boost
    top_item = plan_list[0]
    assert top_item["zone_id"] == "terrace"
    assert top_item["recent_tamper"] is True
    assert "camera tampered" in top_item["reason"].lower() or "confirmed" in top_item["reason"].lower()
    assert top_item["suggested_check_time"] is not None
    assert ":" in top_item["suggested_check_time"]


@pytest.mark.asyncio
async def test_scenarios_reset_history_flag(client: AsyncClient):
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@sunrise.demo", "password": "Owner@12345"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Seed history
    await seed_history(close_when_done=False)
    org = await Organization.find_one(Organization.slug == "sunrise")
    assert org is not None

    initial_hist_count = await Incident.find({"org_id": str(org.id), "source": "seed_history"}).count()
    assert initial_hist_count >= 50

    # 1. Normal reset (include_history=False) -> Historical incidents PRESERVED
    reset1 = await client.post("/api/v1/scenarios/reset?include_history=false", headers=auth_headers)
    assert reset1.status_code == 200
    hist_count_after_soft_reset = await Incident.find({"org_id": str(org.id), "source": "seed_history"}).count()
    assert hist_count_after_soft_reset == initial_hist_count

    # 2. Reset with include_history=true -> Historical incidents REMOVED
    reset2 = await client.post("/api/v1/scenarios/reset?include_history=true", headers=auth_headers)
    assert reset2.status_code == 200
    hist_count_after_hard_reset = await Incident.find({"org_id": str(org.id), "source": "seed_history"}).count()
    assert hist_count_after_hard_reset == 0


@pytest.mark.asyncio
async def test_analytics_summary_metrics(client: AsyncClient):
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@sunrise.demo", "password": "Owner@12345"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Seed history
    await seed_history(close_when_done=False)

    res = await client.get("/api/v1/analytics/summary?days=30", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["total_incidents"] > 0
    assert "critical" in data["totals_by_severity"]
    assert "high" in data["totals_by_severity"]
    assert data["false_alarm_rate"] > 0.0
    assert data["avg_time_to_acknowledge_s"] > 0.0
    assert data["avg_time_to_review_s"] > 0.0
    assert len(data["top_incident_kinds"]) > 0
    assert data["status_breakdown"]["confirmed"] > 0
