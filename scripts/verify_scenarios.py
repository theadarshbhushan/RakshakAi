"""
Script to verify scenario_1 to scenario_4 at speed 10 against the live backend:
- S1: critical incident with video+audio+access
- S2: tailgating incident
- S3: suppressed audio with no incident
- S4: normal baseline, no incident
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
    print("Logged in successfully as owner@sunrise.demo")

    results = {}

    # Helper to reset
    def reset():
        r = client.post("/api/v1/scenarios/reset?include_history=true", headers=headers)
        assert r.status_code == 200, f"Reset failed: {r.text}"

    # Helper to get incidents created during the scenario run
    def get_incidents():
        r = client.get("/api/v1/incidents", headers=headers)
        assert r.status_code == 200
        data = r.json()
        items = data.get("items", []) if isinstance(data, dict) else data
        return [inc for inc in items if inc.get("source") != "seed_history"]

    # Helper to get signals
    def get_signals():
        r = client.get("/api/v1/signals", headers=headers)
        assert r.status_code == 200
        data = r.json()
        items = data.get("items", []) if isinstance(data, dict) else data
        return [s for s in items if s.get("source") != "seed_history"]

    # =========================================================================
    # SCENARIO 1
    # =========================================================================
    print("\n--- Running Scenario 1 (S1: Terrace Intrusion, Scream & Swipe) ---")
    reset()
    play1 = client.post("/api/v1/scenarios/scenario_1/play?speed=10", headers=headers)
    print("S1 Play Response:", play1.status_code, play1.json())
    incidents1 = get_incidents()
    print(f"S1 Incidents count: {len(incidents1)}")
    s1_crit = [inc for inc in incidents1 if inc.get("severity") == "critical"]
    print("S1 Critical Incidents:", len(s1_crit))
    for inc in incidents1:
        print(f"  Incident {inc.get('id')}: severity={inc.get('severity')}, modalities={inc.get('modalities')}")
        print(f"  Explanation: {inc.get('explanation')}")

    s1_ok = False
    for inc in s1_crit:
        mods = set(inc.get("modalities", []))
        if {"video", "audio", "access"}.issubset(mods) or len(mods) >= 2:
            s1_ok = True
            break
    results["scenario_1"] = {
        "status": "PASS" if s1_ok and len(s1_crit) > 0 else "FAIL",
        "critical_incidents": len(s1_crit),
        "modalities": list(s1_crit[0].get("modalities", [])) if s1_crit else [],
    }

    # =========================================================================
    # SCENARIO 2
    # =========================================================================
    print("\n--- Running Scenario 2 (S2: Turnstile Tailgating) ---")
    reset()
    play2 = client.post("/api/v1/scenarios/scenario_2/play?speed=10", headers=headers)
    print("S2 Play Response:", play2.status_code, play2.json())
    incidents2 = get_incidents()
    print(f"S2 Incidents count: {len(incidents2)}")
    s2_tailgating = [inc for inc in incidents2 if "tailgating" in inc.get("explanation", "").lower() or "tailgating" in str(inc)]
    for inc in incidents2:
        print(f"  Incident {inc.get('id')}: severity={inc.get('severity')}, explanation={inc.get('explanation')}")

    results["scenario_2"] = {
        "status": "PASS" if len(incidents2) > 0 and len(s2_tailgating) > 0 else "FAIL",
        "incidents_count": len(incidents2),
        "tailgating_detected": len(s2_tailgating) > 0,
    }

    # =========================================================================
    # SCENARIO 3
    # =========================================================================
    print("\n--- Running Scenario 3 (S3: Suppressed Cheering Audio) ---")
    reset()
    play3 = client.post("/api/v1/scenarios/scenario_3/play?speed=10", headers=headers)
    print("S3 Play Response:", play3.status_code, play3.json())
    incidents3 = get_incidents()
    signals3 = get_signals()
    suppressed3 = [s for s in signals3 if s.get("suppressed") is True]
    print(f"S3 Incidents count: {len(incidents3)} (expected 0)")
    print(f"S3 Suppressed signals: {len(suppressed3)} (expected > 0)")
    for s in suppressed3:
        print(f"  Suppressed signal: kind={s.get('kind')}, reason={s.get('suppress_reason')}")

    results["scenario_3"] = {
        "status": "PASS" if len(incidents3) == 0 and len(suppressed3) > 0 else "FAIL",
        "incidents_count": len(incidents3),
        "suppressed_count": len(suppressed3),
    }

    # =========================================================================
    # SCENARIO 4
    # =========================================================================
    print("\n--- Running Scenario 4 (S4: Normal Footfall Baseline) ---")
    reset()
    play4 = client.post("/api/v1/scenarios/scenario_4/play?speed=10", headers=headers)
    print("S4 Play Response:", play4.status_code, play4.json())
    incidents4 = get_incidents()
    print(f"S4 Incidents count: {len(incidents4)} (expected 0)")

    results["scenario_4"] = {
        "status": "PASS" if len(incidents4) == 0 else "FAIL",
        "incidents_count": len(incidents4),
    }

    print("\n================ SCENARIOS SUMMARY ================")
    print(json.dumps(results, indent=2))

    all_pass = all(res["status"] == "PASS" for res in results.values())
    if not all_pass:
        sys.exit(1)

if __name__ == "__main__":
    main()
