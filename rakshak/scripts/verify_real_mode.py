"""
Verification script for RakshakAI in DETECTOR_MODE=real:
1. Plays scenario_1 and confirms a critical incident with video + audio + access modalities.
2. Plays scenario_3 and confirms the audio signal is suppressed with a reason.
3. Checks that skeleton (public) and face-blurred (restricted) evidence files exist.
"""
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import mongomock_motor
from beanie import init_beanie

from app.core.config import settings
from app.models.incident import Incident
from app.models.organization import Organization
from app.models.rules import RuleDocument
from app.models.signal import AccessEvent, Signal
from app.models.user import User
from app.models.zone import Camera, Zone
from app.scenario_runner import ScenarioRunner


async def main():
    print("=== Testing RakshakAI with DETECTOR_MODE=real ===")
    settings.DETECTOR_MODE = "real"

    # Setup offline mongomock DB
    client = mongomock_motor.AsyncMongoMockClient()
    db = client.rakshak_test
    await init_beanie(
        database=db,
        document_models=[User, Organization, Zone, Camera, RuleDocument, Incident, Signal, AccessEvent],
    )

    test_org_id = "org_verify_real"

    # Seed rules, zones, and cameras
    await RuleDocument(
        org_id=test_org_id,
        is_active=True,
        curfew={"start": "23:00", "end": "05:30"},
        weights={"video": 0.85, "audio": 0.70, "access": 0.75},
        fusion={"window_seconds": 60},
        rules={"audio": {"context_ratio": 0.80}, "loitering": {"seconds": 45}},
    ).insert()

    await Zone(
        org_id=test_org_id,
        site_id="site_main",
        zone_id="terrace",
        name="Terrace Rooftop",
        type="restricted",
        adjacent_zone_ids=["block_b_entry"],
        polygons={"cam_terrace": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]},
        allowed_roles=["warden", "maintenance"],
    ).insert()

    await Zone(
        org_id=test_org_id,
        site_id="site_main",
        zone_id="block_b_entry",
        name="Block B Entry",
        type="entry",
        adjacent_zone_ids=["terrace"],
        allowed_roles=["resident", "warden", "admin"],
    ).insert()

    await Camera(
        org_id=test_org_id,
        site_id="site_main",
        camera_id="cam_terrace",
        name="Terrace Camera",
        zone_id="terrace",
        source_path="videos/intrusion/intrusion_01.mp4",
    ).insert()

    await Zone(
        org_id=test_org_id,
        site_id="site_main",
        zone_id="common_room",
        name="Student Common Room",
        type="common",
        allowed_roles=["resident", "warden", "admin"],
    ).insert()

    # 1. PLAY SCENARIO 1
    print("\n--- Running Scenario 1 (Intrusion + Distress Audio + Curfew Access) ---")
    s1_data = ScenarioRunner.load_scenario("scenario_1")
    res1 = await ScenarioRunner.run_scenario(test_org_id, s1_data, speed=2.5)
    print(f"Scenario 1 completed: {res1['status']}")

    # Check incidents
    incidents = await Incident.find(Incident.org_id == test_org_id).to_list()
    print(f"Total incidents created in S1: {len(incidents)}")
    assert len(incidents) >= 1, "Scenario 1 must create at least 1 incident"

    s1_inc = incidents[0]
    print(f"Incident ID: {s1_inc.id}")
    print(f"Incident Severity: {s1_inc.severity}")
    print(f"Incident Modalities: {s1_inc.modalities}")
    print(f"Incident Explanation: {s1_inc.explanation}")

    assert s1_inc.severity == "critical", f"Expected 'critical' severity, got '{s1_inc.severity}'"
    for m in ["video", "audio", "access"]:
        assert m in s1_inc.modalities, f"Expected modality '{m}' in incident modalities {s1_inc.modalities}"

    # 2. PLAY SCENARIO 3
    print("\n--- Running Scenario 3 (Common Room Cheering - Context Filter Suppression) ---")
    s3_data = ScenarioRunner.load_scenario("scenario_3")
    res3 = await ScenarioRunner.run_scenario(test_org_id, s3_data, speed=5.0)
    print(f"Scenario 3 completed: {res3['status']}")

    s3_signals = await Signal.find(Signal.org_id == test_org_id, Signal.zone_id == "common_room").to_list()
    print(f"Total signals in common_room: {len(s3_signals)}")
    assert len(s3_signals) >= 1, "Scenario 3 must emit audio signals"

    suppressed_sigs = [s for s in s3_signals if s.suppressed]
    print(f"Suppressed signals count: {len(suppressed_sigs)}")
    assert len(suppressed_sigs) >= 1, "Scenario 3 audio signal must be suppressed"
    sup = suppressed_sigs[0]
    print(f"Suppressed Signal Reason: {sup.suppress_reason}")
    assert sup.suppress_reason is not None and len(sup.suppress_reason) > 0

    # 3. VERIFY EVIDENCE FILES EXIST
    print("\n--- Verifying Evidence Files on Disk ---")
    pub_evidence = list((settings.DATA_DIR / "evidence" / "public").glob("*_skeleton.jpg"))
    res_evidence = list((settings.DATA_DIR / "evidence" / "restricted").glob("*_blurred.jpg"))
    audio_evidence = list((settings.DATA_DIR / "evidence" / "restricted").glob("*.wav"))

    print(f"Public skeleton evidence files ({len(pub_evidence)} found): {[f.name for f in pub_evidence[:3]]}")
    print(f"Restricted face-blurred evidence files ({len(res_evidence)} found): {[f.name for f in res_evidence[:3]]}")
    print(f"Restricted audio clip evidence files ({len(audio_evidence)} found): {[f.name for f in audio_evidence[:3]]}")

    assert len(pub_evidence) >= 1, "At least one skeleton evidence file must exist in data/evidence/public/"
    assert len(res_evidence) >= 1, "At least one face-blurred evidence file must exist in data/evidence/restricted/"
    assert len(audio_evidence) >= 1, "At least one audio clip evidence file must exist in data/evidence/restricted/"

    print("\n[SUCCESS] All DETECTOR_MODE=real verifications PASSED!")


if __name__ == "__main__":
    asyncio.run(main())
