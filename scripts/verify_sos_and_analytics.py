"""
Verification script for SOS submission and Risk Analytics (heatmap & patrol-plan).
"""
import httpx
import json
import sys

BASE_URL = "http://localhost:8000"

def main():
    client = httpx.Client(base_url=BASE_URL, timeout=60.0)

    # 1. Login
    login_res = client.post("/api/v1/auth/login", json={"email": "owner@sunrise.demo", "password": "Owner@12345"})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Logged in successfully.")

    # 2. Get zones and extract sos_token
    zones_res = client.get("/api/v1/zones", headers=headers)
    assert zones_res.status_code == 200, f"Failed to get zones: {zones_res.text}"
    zones = zones_res.json()
    assert len(zones) > 0, "No zones found"

    target_zone = next((z for z in zones if z.get("sos_token")), zones[0])
    sos_token = target_zone.get("sos_token")
    zone_name = target_zone.get("name")
    zone_id = target_zone.get("zone_id")
    assert sos_token, f"No sos_token found on zone {zone_id}"
    print(f"Selected zone: {zone_name} ({zone_id}), sos_token={sos_token}")

    # 3. Submit anonymous SOS report
    print(f"Submitting public SOS to /api/v1/sos/{sos_token}...")
    sos_payload = {
        "type": "unsafe",
        "note": "Suspicious person loitering near stairs",
    }
    # Anonymous request without auth header
    sos_res = client.post(f"/api/v1/sos/{sos_token}", json=sos_payload)
    print("SOS submission response status:", sos_res.status_code)
    assert sos_res.status_code in (200, 201), f"SOS submission failed: {sos_res.text}"
    sos_data = sos_res.json()
    print("SOS Response:", json.dumps(sos_data, indent=2))
    incident_id = sos_data.get("incident_id")
    assert incident_id, "Expected incident_id in SOS response"

    # Confirm incident severity is at least high
    inc_res = client.get(f"/api/v1/incidents/{incident_id}", headers=headers)
    assert inc_res.status_code == 200, f"Failed to fetch incident: {inc_res.text}"
    inc_info = inc_res.json()
    print("Created SOS Incident:")
    print(f"  ID: {inc_info['id']}")
    print(f"  Severity: {inc_info['severity']}")
    print(f"  Zone: {inc_info['zone_id']}")
    print(f"  Explanation: {inc_info['explanation']}")
    assert inc_info["severity"] in ("high", "critical"), f"Expected severity high or critical, got {inc_info['severity']}"

    # 4. Check /analytics/heatmap
    print("\nQuerying /api/v1/analytics/heatmap?days=30...")
    heatmap_res = client.get("/api/v1/analytics/heatmap?days=30", headers=headers)
    print("Heatmap status:", heatmap_res.status_code)
    assert heatmap_res.status_code == 200, f"Heatmap failed: {heatmap_res.text}"
    hm_data = heatmap_res.json()
    assert "zones" in hm_data and "per_zone" in hm_data and "per_hour" in hm_data and "total" in hm_data, "Missing heatmap fields"
    print(f"Heatmap returned {len(hm_data['zones'])} zones, {len(hm_data['per_hour'])} hours.")
    print(f"Total historical incidents: {hm_data['total'].get('incident_count')}, Total risk score: {hm_data['total'].get('risk_score')}")

    # 5. Check /analytics/patrol-plan
    print("\nQuerying /api/v1/analytics/patrol-plan?shift_start=22:00&shift_end=06:00...")
    plan_res = client.get("/api/v1/analytics/patrol-plan?shift_start=22:00&shift_end=06:00", headers=headers)
    print("Patrol plan status:", plan_res.status_code)
    assert plan_res.status_code == 200, f"Patrol plan failed: {plan_res.text}"
    plan_data = plan_res.json()
    plan_items = plan_data.get("plan", [])
    print(f"Patrol plan returned {len(plan_items)} ranked zones:")
    for idx, item in enumerate(plan_items, 1):
        print(f"  #{idx} Zone: {item['zone_name']} ({item['zone_id']}) | Risk: {item['risk_score']} | Time: {item['suggested_check_time']}")
        print(f"      Reason: {item['reason']}")

    assert len(plan_items) > 0, "Patrol plan returned empty list"

    print("\nSTEP 5 PASSED: SOS created high incident, heatmap and patrol-plan verified.")

if __name__ == "__main__":
    main()
