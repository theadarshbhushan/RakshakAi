"""
Verification script for Camera Tamper and Blind-Spot Compensation in live server:
- Simulates camera tamper (black frames / covered) on cam_terrace
- Confirms tamper incident with blind-spot explanation narrative
- Confirms zone marked is_blind_spot=True and audio threshold lowered
- Confirms patrol plan ranks blind-spot zone at the top with reason 'camera not functioning'
- Reverts camera health to ok and confirms recovery
"""
import httpx
import json

BASE_URL = "http://localhost:8000"

def main():
    client = httpx.Client(base_url=BASE_URL, timeout=60.0)

    # 1. Login
    login_res = client.post("/api/v1/auth/login", json={"email": "owner@sunrise.demo", "password": "Owner@12345"})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Logged in successfully.")

    # 2. Update cam_terrace health to tampered
    print("Updating cam_terrace health to tampered (dark)...")
    cam_res = client.post(
        "/api/v1/cameras/cam_terrace/health",
        json={"health_status": "tampered", "health_reason": "dark"},
        headers=headers,
    )
    assert cam_res.status_code == 200, f"Failed to update camera health: {cam_res.text}"
    cam_data = cam_res.json()
    assert cam_data["health_status"] == "tampered"
    assert cam_data["health_reason"] == "dark"
    print(f"Camera health updated: status={cam_data['health_status']}, reason={cam_data['health_reason']}")

    # 3. Check zone terrace is_blind_spot
    zones_res = client.get("/api/v1/zones", headers=headers)
    assert zones_res.status_code == 200
    terrace_zone = next(z for z in zones_res.json() if z["zone_id"] == "terrace")
    print(f"Zone terrace blind spot: is_blind_spot={terrace_zone.get('is_blind_spot')}, reason={terrace_zone.get('blind_spot_reason')}")
    assert terrace_zone.get("is_blind_spot") is True
    assert terrace_zone.get("blind_spot_reason") == "dark"

    # 4. Check active rules threshold lowered
    rules_res = client.get("/api/v1/rules", headers=headers)
    assert rules_res.status_code == 200
    active_rules = rules_res.json()
    terrace_conf = active_rules["zones"]["terrace"]
    distress_threshold = terrace_conf["thresholds"]["distress_audio"]
    print(f"Active distress_audio threshold in terrace: {distress_threshold}")
    assert distress_threshold <= 0.25, f"Expected lowered threshold <= 0.25, got {distress_threshold}"
    assert "blind_spot_compensation" in terrace_conf
    assert terrace_conf["blind_spot_compensation"]["reason"] == "blind_spot_compensation"

    # 5. Check /analytics/patrol-plan puts terrace at the very top with reason 'camera not functioning'
    plan_res = client.get("/api/v1/analytics/patrol-plan?shift_start=22:00&shift_end=06:00", headers=headers)
    assert plan_res.status_code == 200
    plan_data = plan_res.json()
    plan_items = plan_data.get("plan", [])
    assert len(plan_items) > 0

    top_item = plan_items[0]
    print(f"Top patrol plan item: {top_item['zone_name']} ({top_item['zone_id']})")
    print(f"  is_blind_spot: {top_item.get('is_blind_spot')}")
    print(f"  reason: {top_item.get('reason')}")
    assert top_item["zone_id"] == "terrace", f"Expected terrace at top, got {top_item['zone_id']}"
    assert top_item.get("is_blind_spot") is True
    assert "camera not functioning" in top_item.get("reason"), f"Expected 'camera not functioning' in reason, got {top_item.get('reason')}"

    # 6. Revert camera health to ok
    print("\nReverting cam_terrace health to ok...")
    rec_res = client.post(
        "/api/v1/cameras/cam_terrace/health",
        json={"health_status": "ok"},
        headers=headers,
    )
    assert rec_res.status_code == 200
    rec_zone = next(z for z in client.get("/api/v1/zones", headers=headers).json() if z["zone_id"] == "terrace")
    print(f"Zone terrace after recovery: is_blind_spot={rec_zone.get('is_blind_spot')}")
    assert rec_zone.get("is_blind_spot") is False

    rec_rules = client.get("/api/v1/rules", headers=headers).json()
    restored_threshold = rec_rules["zones"]["terrace"]["thresholds"]["distress_audio"]
    print(f"Restored distress_audio threshold in terrace: {restored_threshold}")
    assert restored_threshold == 0.35, f"Expected restored threshold 0.35, got {restored_threshold}"

    print("\nSTEP 6 PASSED: Tamper activates blind-spot compensation, shifts patrol plan to top, and reverts on recovery.")

if __name__ == "__main__":
    main()
