"""
Essential Integration Test Suite for RakshakAI Backend (Stabilization Mode).
Tests core multi-tenant security, RBAC, access rules, fusion, review, calibration,
audit verification, scenarios, and health endpoints against 'rakshakai_test' database.
"""
import pytest
from httpx import AsyncClient
from beanie import PydanticObjectId

from app.models.audit import AuditLog
from app.models.zone import Camera
from app.models.user import User


# =============================================================================
# 1. Login + /auth/me returns role and permissions
# =============================================================================
@pytest.mark.asyncio
async def test_login_and_auth_me_returns_role_and_permissions(client: AsyncClient):
    # Valid login
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@sunrise.demo", "password": "Owner@12345"},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    assert login_data["user"]["role"] == "owner"
    token = login_data["access_token"]

    # Verify /auth/me returns profile, role, and resolved permissions list
    me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == "owner@sunrise.demo"
    assert me_data["role"] == "owner"
    assert "incidents:review" in me_data["permissions"]
    assert "rules:write" in me_data["permissions"]

    # Wrong password attempt -> 401 generic
    bad_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@sunrise.demo", "password": "WrongPassword123!"},
    )
    assert bad_res.status_code == 401
    assert "Invalid email or password" in bad_res.json()["error"]["message"]


# =============================================================================
# 2. Refresh token rotation works; reused old refresh token is rejected
# =============================================================================
@pytest.mark.asyncio
async def test_refresh_token_rotation_and_reuse_rejection(client: AsyncClient):
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "warden@sunrise.demo", "password": "Warden@12345"},
    )
    assert login_res.status_code == 200
    data = login_res.json()
    refresh_token = data.get("refresh_token")
    assert refresh_token is not None

    # Rotate refresh token
    rotate_res = await client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert rotate_res.status_code == 200
    new_data = rotate_res.json()
    new_refresh = new_data["refresh_token"]
    assert new_refresh != refresh_token

    # Replay old refresh token -> Replay attack detection & revocation
    replay_res = await client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert replay_res.status_code == 401
    err_msg = replay_res.json()["error"]["message"].lower()
    assert "revoked" in err_msg or "compromised" in err_msg


# =============================================================================
# 3. Guard gets 403 on PUT /rules
# =============================================================================
@pytest.mark.asyncio
async def test_guard_gets_403_on_put_rules(client: AsyncClient):
    guard_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "guard@sunrise.demo", "password": "Guard@12345"},
    )
    guard_token = guard_login.json()["access_token"]

    # Guard attempts to modify security rules -> 403 Forbidden
    rules_res = await client.put(
        "/api/v1/rules",
        json={"version": 2, "curfew": {"start": "00:00", "end": "05:00"}},
        headers={"Authorization": f"Bearer {guard_token}"},
    )
    assert rules_res.status_code == 403

    # Guard cannot break-glass evidence override -> 403
    bg_res = await client.post(
        "/api/v1/privacy/breakglass",
        json={"incident_id": "6adcb552cbf9d04991e9984c", "reason": "emergency override justification"},
        headers={"Authorization": f"Bearer {guard_token}"},
    )
    assert bg_res.status_code == 403


# =============================================================================
# 4. User from Green Valley org gets 404 on a Sunrise incident
# =============================================================================
@pytest.mark.asyncio
async def test_tenant_isolation_green_valley_gets_404(client: AsyncClient):
    # Sunrise Owner
    res_a = await client.post("/api/v1/auth/login", json={"email": "owner@sunrise.demo", "password": "Owner@12345"})
    token_a = res_a.json()["access_token"]

    # Green Valley Owner
    res_b = await client.post("/api/v1/auth/login", json={"email": "owner@greenvalley.demo", "password": "Owner@12345"})
    token_b = res_b.json()["access_token"]

    # Sunrise generates an incident via Scenario 1
    await client.post("/api/v1/scenarios/reset", headers={"Authorization": f"Bearer {token_a}"})
    await client.post("/api/v1/scenarios/scenario_1/play?speed=100.0", headers={"Authorization": f"Bearer {token_a}"})

    incidents_a = (await client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token_a}"})).json()["items"]
    assert len(incidents_a) >= 1
    sunrise_inc_id = incidents_a[0]["id"]

    # Green Valley lists incidents -> Sunrise incident is NOT visible
    gv_incidents = (await client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token_b}"})).json()["items"]
    assert sunrise_inc_id not in [i["id"] for i in gv_incidents]

    # Green Valley requests Sunrise incident directly -> 404 Not Found (NEVER 403 to prevent existence leakage)
    cross_res = await client.get(f"/api/v1/incidents/{sunrise_inc_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert cross_res.status_code == 404


# =============================================================================
# 5. Scenario S1 -> critical incident with video, audio, and access modalities
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_s1_critical_corroboration(client: AsyncClient):
    res = await client.post("/api/v1/auth/login", json={"email": "admin@sunrise.demo", "password": "Admin@12345"})
    token = res.json()["access_token"]

    await client.post("/api/v1/scenarios/reset", headers={"Authorization": f"Bearer {token}"})
    s1_res = await client.post("/api/v1/scenarios/scenario_1/play?speed=100.0", headers={"Authorization": f"Bearer {token}"})
    assert s1_res.status_code == 200

    incidents_res = await client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token}"})
    assert incidents_res.status_code == 200
    inc_items = incidents_res.json()["items"]
    assert len(inc_items) >= 1
    crit_inc = inc_items[0]

    assert crit_inc["severity"] == "critical"
    assert len(set(crit_inc["modalities"])) == 3  # Video, Audio, Access
    assert crit_inc["composite_score"] >= 0.85
    assert "Terrace" in crit_inc["explanation"] or "Person entered" in crit_inc["explanation"]


# =============================================================================
# 6. Scenario S3 -> no incident, at least one suppressed signal
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_s3_suppressed_cheering_no_incident(client: AsyncClient):
    res = await client.post("/api/v1/auth/login", json={"email": "admin@sunrise.demo", "password": "Admin@12345"})
    token = res.json()["access_token"]

    # Play Scenario 3 (Common room birthday party cheering)
    await client.post("/api/v1/scenarios/reset", headers={"Authorization": f"Bearer {token}"})
    s3_res = await client.post("/api/v1/scenarios/scenario_3/play?speed=100.0", headers={"Authorization": f"Bearer {token}"})
    assert s3_res.status_code == 200

    # Must result in ZERO incidents
    incidents_res = await client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token}"})
    assert len(incidents_res.json()["items"]) == 0

    # At least one suppressed audio signal must be recorded
    signals_res = await client.get("/api/v1/signals?suppressed=true", headers={"Authorization": f"Bearer {token}"})
    assert signals_res.status_code == 200
    suppressed_signals = signals_res.json()["items"]
    assert len(suppressed_signals) >= 1
    assert "Context filter" in suppressed_signals[0]["suppress_reason"]


# =============================================================================
# 7. Reviewing an incident as false_alarm creates a calibration entry + revert
# =============================================================================
@pytest.mark.asyncio
async def test_false_alarm_review_creates_calibration_entry_and_revert(client: AsyncClient):
    res = await client.post("/api/v1/auth/login", json={"email": "warden@sunrise.demo", "password": "Warden@12345"})
    token = res.json()["access_token"]

    # Generate incident via S1
    await client.post("/api/v1/scenarios/reset", headers={"Authorization": f"Bearer {token}"})
    await client.post("/api/v1/scenarios/scenario_1/play?speed=100.0", headers={"Authorization": f"Bearer {token}"})

    incidents = (await client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token}"})).json()["items"]
    inc_id = incidents[0]["id"]

    # Human review marking incident as false_alarm
    review_res = await client.post(
        f"/api/v1/incidents/{inc_id}/review",
        json={"label": "false_alarm", "note": "False trigger due to scheduled terrace maintenance."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert review_res.status_code == 200
    assert review_res.json()["status"] == "false_alarm"

    # Verify calibration entry created with increased threshold (+0.05)
    cal_res = await client.get("/api/v1/calibration", headers={"Authorization": f"Bearer {token}"})
    assert cal_res.status_code == 200
    cal_data = cal_res.json()
    assert len(cal_data["history"]) >= 1
    entry = cal_data["history"][0]
    assert entry["new_value"] > entry["old_value"]

    # Revert calibration
    revert_res = await client.post(
        f"/api/v1/calibration/{entry['id']}/revert",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revert_res.status_code == 200
    assert revert_res.json()["reverted"] is True


# =============================================================================
# 8. /audit/verify returns valid on authentic chain, detects tampering
# =============================================================================
@pytest.mark.asyncio
async def test_audit_log_cryptographic_verification(client: AsyncClient):
    res = await client.post("/api/v1/auth/login", json={"email": "auditor@sunrise.demo", "password": "Auditor@12345"})
    token = res.json()["access_token"]

    # Authentic unbroken chain verification
    verify_res = await client.get("/api/v1/audit/verify", headers={"Authorization": f"Bearer {token}"})
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["valid"] is True
    assert verify_data["total_records"] > 0

    # Tamper with one record
    latest_record = await AuditLog.find().sort("-seq").first_or_none()
    assert latest_record is not None
    orig_action = latest_record.action
    latest_record.action = "UNAUTHORIZED_MODIFICATION"
    await latest_record.save()

    # Tampering detected
    tamper_res = await client.get("/api/v1/audit/verify", headers={"Authorization": f"Bearer {token}"})
    assert tamper_res.status_code == 200
    tamper_data = tamper_res.json()
    assert tamper_data["valid"] is False
    assert tamper_data["broken_at_seq"] == latest_record.seq

    # Restore record
    latest_record.action = orig_action
    await latest_record.save()


# =============================================================================
# 9. Health endpoints (/api/v1/health/live and /api/v1/health/ready)
# =============================================================================
@pytest.mark.asyncio
async def test_health_endpoints(client: AsyncClient):
    live_res = await client.get("/api/v1/health/live")
    assert live_res.status_code == 200
    assert live_res.json()["status"] == "live"

    ready_res = await client.get("/api/v1/health/ready")
    assert ready_res.status_code == 200
    assert ready_res.json()["status"] == "ready"
    assert ready_res.json()["database"]["connected"] is True


# =============================================================================
# 10. Swagger UI /docs vs Strict API CSP and Security Headers
# =============================================================================
@pytest.mark.asyncio
async def test_docs_security_headers_and_csp(client: AsyncClient):
    # GET /docs returns 200 and its CSP header includes cdn.jsdelivr.net
    docs_res = await client.get("/docs")
    assert docs_res.status_code == 200
    docs_csp = docs_res.headers.get("Content-Security-Policy", "")
    assert "https://cdn.jsdelivr.net" in docs_csp
    assert "https://fastapi.tiangolo.com" in docs_csp
    assert "X-Frame-Options" not in docs_res.headers

    # /redoc also allows CDN assets
    redoc_res = await client.get("/redoc")
    assert redoc_res.status_code == 200
    redoc_csp = redoc_res.headers.get("Content-Security-Policy", "")
    assert "https://cdn.jsdelivr.net" in redoc_csp

    # /api/v1/health/live keeps the strict API CSP and X-Frame-Options: DENY
    live_res = await client.get("/api/v1/health/live")
    assert live_res.status_code == 200
    live_csp = live_res.headers.get("Content-Security-Policy", "")
    assert live_csp == "default-src 'self'"
    assert live_res.headers.get("X-Frame-Options") == "DENY"


# =============================================================================
# 11. OAuth2 Form /auth/token and Malformed Input Error Handling (Never 500)
# =============================================================================
@pytest.mark.asyncio
async def test_auth_token_endpoint_and_malformed_input_returns_4xx(client: AsyncClient):
    # 1. Valid form login to /api/v1/auth/token (Swagger OAuth2PasswordRequestForm flow)
    token_res = await client.post(
        "/api/v1/auth/token",
        data={"username": "owner@sunrise.demo", "password": "Owner@12345"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert token_res.status_code == 200
    token_data = token_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    access_token = token_data["access_token"]

    # 2. Verify token works via HTTPBearer directly on protected route
    me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "owner@sunrise.demo"

    # 3. Invalid credentials to /api/v1/auth/token returns 401
    bad_token = await client.post(
        "/api/v1/auth/token",
        data={"username": "owner@sunrise.demo", "password": "WrongPassword99!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert bad_token.status_code == 401
    assert "error" in bad_token.json()

    # 4. Form data posted to JSON-expecting /api/v1/auth/login returns 422 (never 500)
    wrong_type_res = await client.post(
        "/api/v1/auth/login",
        content=b"username=owner%40sunrise.demo&password=Owner%4012345",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert 400 <= wrong_type_res.status_code < 500
    assert wrong_type_res.status_code == 422
    assert wrong_type_res.json()["error"]["code"] == "VALIDATION_ERROR"

    # 5. Malformed binary data to /login returns 422 (never 500)
    malformed_res = await client.post(
        "/api/v1/auth/login",
        content=b"\x00\xff\xfe{malformed}",
        headers={"Content-Type": "application/json"},
    )
    assert 400 <= malformed_res.status_code < 500
    assert malformed_res.status_code == 422
    assert malformed_res.json()["error"]["code"] == "VALIDATION_ERROR"


