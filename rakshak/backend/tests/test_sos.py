"""
Integration tests for QR-Code Anonymous Student SOS emergency reporting:
- Zone QR code generation (PNG) and printable sheet (HTML)
- Token rotation by owner/admin
- Public zone info endpoint
- Anonymous SOS submission creating high-severity incident
- Corroboration: SOS + distress audio in same zone -> critical severity and explainable narrative
- Invalid token -> 404
- Rate limiting: 4th request in a minute -> 429
- Honeypot anti-abuse -> 400
- Anonymous audit logging with zero personal data
"""
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient

from app.api.v1.routers.sos import reset_sos_rate_limits
from app.fusion.corroboration import FusionEngine
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.rules import RuleDocument
from app.models.signal import Signal
from app.models.zone import Zone


@pytest.mark.asyncio
async def test_sos_creates_high_incident_and_anonymous_audit(client: AsyncClient):
    reset_sos_rate_limits()
    # Find a zone in the test org
    zone = await Zone.find_one({"zone_id": "corridor_2f"})
    if not zone:
        zone = await Zone.find_one()
    assert zone is not None
    assert zone.sos_token is not None

    # Submit valid SOS
    sos_payload = {
        "type": "fight",
        "note": "Two individuals fighting near stairway",
    }
    response = await client.post(
        f"/api/v1/sos/{zone.sos_token}",
        json=sos_payload,
        headers={"x-forwarded-for": "198.51.100.1"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "received"
    assert data["severity"] == "high"
    assert data["zone_name"] == zone.name
    assert data["incident_id"] is not None

    # Verify incident in DB
    incident = await Incident.get(data["incident_id"])
    assert incident is not None
    assert incident.severity == "high"
    assert "report" in incident.modalities
    assert zone.name in incident.explanation or zone.zone_id in incident.explanation

    # Verify signal in DB
    signal = await Signal.find_one({"incident_id": str(incident.id), "kind": "student_sos"})
    assert signal is not None
    assert signal.modality == "report"
    assert signal.score == 0.9
    assert signal.details.get("type") == "fight"
    assert signal.details.get("note") == "Two individuals fighting near stairway"

    # Verify anonymous audit log (no IP, no device ID, no personal info)
    audit = await AuditLog.find_one({"action": "sos.submit", "target": f"zone:{zone.zone_id}"})
    assert audit is not None
    assert audit.actor.get("type") == "anonymous"
    assert audit.actor.get("role") == "student"
    assert audit.ip is None
    assert audit.user_agent is None


@pytest.mark.asyncio
async def test_sos_corroborated_by_distress_audio_becomes_critical(client: AsyncClient):
    reset_sos_rate_limits()
    zone = await Zone.find_one({"zone_id": "corridor_2f"})
    if not zone:
        zone = await Zone.find_one()
    assert zone is not None

    # 1. First: Student SOS submitted
    now = datetime.now(timezone.utc)
    sos_payload = {
        "type": "fight",
        "note": "Immediate assistance needed",
    }
    sos_res = await client.post(
        f"/api/v1/sos/{zone.sos_token}",
        json=sos_payload,
        headers={"x-forwarded-for": "198.51.100.2"},
    )
    assert sos_res.status_code == 201
    inc_id = sos_res.json()["incident_id"]
    assert inc_id is not None

    # 2. Corroborating distress audio detected 8 seconds later in the same zone
    audio_signal = Signal(
        org_id=zone.org_id,
        site_id=zone.site_id,
        modality="audio",
        kind="distress_audio",
        zone_id=zone.zone_id,
        score=0.78,
        threshold=0.5,
        details={"label": "screaming"},
        ts=now + timedelta(seconds=8),
        source="audio_yfh_resnet",
    )
    active_rules = await RuleDocument.find_one({"org_id": zone.org_id, "is_active": True})
    rules_dict = active_rules.model_dump() if active_rules else {}
    fusion_engine = FusionEngine(zone.org_id, rules_dict)

    fused_incident = await fusion_engine.ingest_signal(audio_signal)
    assert fused_incident is not None
    assert str(fused_incident.id) == inc_id

    # The incident severity must elevate to critical
    assert fused_incident.severity == "critical"
    # Modalites should contain both report and audio
    assert "report" in fused_incident.modalities
    assert "audio" in fused_incident.modalities

    # Explanation narrative verification
    explanation = fused_incident.explanation
    assert "Student SOS report (fight)" in explanation
    assert "corroborated by distress audio" in explanation
    assert "Screaming 0.78" in explanation or "screaming" in explanation.lower()
    assert "8 s later" in explanation


@pytest.mark.asyncio
async def test_sos_invalid_token_returns_404(client: AsyncClient):
    reset_sos_rate_limits()
    # Public info endpoint
    info_res = await client.get("/api/v1/sos/nonexistent_invalid_sos_token/info")
    assert info_res.status_code == 404
    data_info = info_res.json()
    err_msg = data_info.get("error", {}).get("message") or data_info.get("detail", "")
    assert "Invalid or rotated SOS token" in err_msg

    # Submit endpoint
    submit_res = await client.post(
        "/api/v1/sos/nonexistent_invalid_sos_token",
        json={"type": "unsafe"},
        headers={"x-forwarded-for": "198.51.100.3"},
    )
    assert submit_res.status_code == 404
    data_submit = submit_res.json()
    err_msg = data_submit.get("error", {}).get("message") or data_submit.get("detail", "")
    assert "Invalid or rotated SOS token" in err_msg


@pytest.mark.asyncio
async def test_sos_rate_limiting_4th_request_returns_429(client: AsyncClient):
    reset_sos_rate_limits()
    zone = await Zone.find_one()
    assert zone is not None

    test_ip = "198.51.100.50"
    headers = {"x-forwarded-for": test_ip}

    # 1st request -> 201
    r1 = await client.post(f"/api/v1/sos/{zone.sos_token}", json={"type": "medical"}, headers=headers)
    assert r1.status_code == 201

    # 2nd request -> 201
    r2 = await client.post(f"/api/v1/sos/{zone.sos_token}", json={"type": "unsafe"}, headers=headers)
    assert r2.status_code == 201

    # 3rd request -> 201
    r3 = await client.post(f"/api/v1/sos/{zone.sos_token}", json={"type": "other", "note": "noise"}, headers=headers)
    assert r3.status_code == 201

    # 4th request in a minute -> 429
    r4 = await client.post(f"/api/v1/sos/{zone.sos_token}", json={"type": "harassment"}, headers=headers)
    assert r4.status_code == 429
    r4_data = r4.json()
    err_msg = r4_data.get("error", {}).get("message") or r4_data.get("detail", "")
    assert "Rate limit exceeded" in err_msg


@pytest.mark.asyncio
async def test_sos_honeypot_rejection_returns_400(client: AsyncClient):
    reset_sos_rate_limits()
    zone = await Zone.find_one()
    assert zone is not None

    # Honeypot filled by bot
    bot_payload = {
        "type": "medical",
        "website": "http://spambot-link.example.com",
    }
    res = await client.post(
        f"/api/v1/sos/{zone.sos_token}",
        json=bot_payload,
        headers={"x-forwarded-for": "198.51.100.99"},
    )
    assert res.status_code == 400
    assert "Spam submission detected" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_sos_public_info_returns_zone_name(client: AsyncClient):
    zone = await Zone.find_one()
    assert zone is not None

    res = await client.get(f"/api/v1/sos/{zone.sos_token}/info")
    assert res.status_code == 200
    data = res.json()
    assert data["zone_name"] == zone.name
    # Must NOT leak internal database IDs or tokens
    assert "id" not in data
    assert "_id" not in data
    assert "sos_token" not in data
    assert "org_id" not in data


@pytest.mark.asyncio
async def test_sos_qr_code_and_qr_sheet_endpoints(client: AsyncClient):
    # Authenticate as owner
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@sunrise.demo", "password": "Owner@12345"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    zone = await Zone.find_one()
    assert zone is not None

    # 1. GET /api/v1/sos/qr/{zone_id} returns PNG image
    qr_res = await client.get(f"/api/v1/sos/qr/{zone.zone_id}", headers=auth_headers)
    assert qr_res.status_code == 200
    assert qr_res.headers["content-type"] == "image/png"
    # PNG signature: 89 50 4E 47 0D 0A 1A 0A
    assert qr_res.content.startswith(b"\x89PNG\r\n\x1a\n")

    # 2. GET /api/v1/sos/qr-sheet returns printable HTML sheet
    sheet_res = await client.get("/api/v1/sos/qr-sheet", headers=auth_headers)
    assert sheet_res.status_code == 200
    assert "text/html" in sheet_res.headers["content-type"]
    html_text = sheet_res.text
    assert "<!DOCTYPE html>" in html_text
    assert zone.name in html_text
    assert "Campus Student SOS" in html_text

    # 3. POST /api/v1/sos/rotate/{zone_id} rotates token
    old_token = zone.sos_token
    rot_res = await client.post(f"/api/v1/sos/rotate/{zone.zone_id}", headers=auth_headers)
    assert rot_res.status_code == 200
    new_token = rot_res.json()["sos_token"]
    assert new_token != old_token

    # Old token is now invalid (404)
    old_info = await client.get(f"/api/v1/sos/{old_token}/info")
    assert old_info.status_code == 404

    # New token is active (200)
    new_info = await client.get(f"/api/v1/sos/{new_token}/info")
    assert new_info.status_code == 200
    assert new_info.json()["zone_name"] == zone.name
