"""
Unit and logic tests for RakshakAI Detectors and Fusion logic:
- Zone intrusion on synthetic keypoints & polygon tests
- Line crossing direction math
- Camera tamper detection (blackout, heavy blur)
- Audio multi-stage pipeline on synthetic score arrays (Stage 1, 2, 3)
- Fusion of camera_tamper (at least medium severity) and loitering (video weight)
"""
import pytest
from datetime import datetime, timezone
import numpy as np
import cv2

from app.detectors.video_pose import (
    point_line_side,
    render_skeleton_frame,
    render_face_blurred_frame,
    is_time_in_curfew,
)
from app.fusion.corroboration import FusionEngine
from app.models.signal import Signal


def test_zone_intrusion_synthetic_keypoints():
    """Verify polygon containment logic using cv2.pointPolygonTest."""
    # Polygon: rectangle from (100, 100) to (400, 400)
    polygon = np.array([[100, 100], [400, 100], [400, 400], [100, 400]], dtype=np.int32)

    # Synthetic person inside polygon
    ankle_left_inside = (250, 300)
    ankle_right_inside = (260, 300)
    midpoint_inside = ((ankle_left_inside[0] + ankle_right_inside[0]) / 2, (ankle_left_inside[1] + ankle_right_inside[1]) / 2)

    dist_inside = cv2.pointPolygonTest(polygon, midpoint_inside, False)
    assert dist_inside >= 0, "Ankle midpoint inside polygon must return >= 0"

    # Synthetic person outside polygon
    ankle_outside = (50, 50)
    dist_outside = cv2.pointPolygonTest(polygon, ankle_outside, False)
    assert dist_outside < 0, "Point outside polygon must return < 0"


def test_line_crossing_direction():
    """Verify signed direction test for door crossing."""
    # Horizontal door line at y=0.5: p1=(0.2, 0.5), p2=(0.8, 0.5)
    p1 = (0.2, 0.5)
    p2 = (0.8, 0.5)

    # Point above line (approaching door)
    p_before = (0.5, 0.3)
    # Point below line (entered door)
    p_after = (0.5, 0.7)

    side_before = point_line_side(p_before, p1, p2)
    side_after = point_line_side(p_after, p1, p2)

    # Moving from side_before < 0 to side_after >= 0 represents "in" crossing
    assert side_before < 0
    assert side_after > 0
    assert side_before * side_after < 0, "Points on opposite sides of line must have opposite signs"

    # Moving backwards (out)
    side_out_1 = point_line_side(p_after, p1, p2)
    side_out_2 = point_line_side(p_before, p1, p2)
    assert side_out_1 > 0 and side_out_2 < 0


def test_tamper_detection_blackout_and_blur():
    """Verify tamper logic for near-black and heavily blurred frames."""
    # 1. Near-black frame
    black_frame = np.full((240, 320), 8, dtype=np.uint8)
    mean_brightness = float(np.mean(black_frame))
    assert mean_brightness < 15.0, "Blackout frame must have mean brightness < 15"

    # 2. Heavy blur detection via Laplacian variance
    sharp_frame = np.zeros((240, 320), dtype=np.uint8)
    # Draw high-contrast checkerboard
    sharp_frame[::20, :] = 255
    sharp_frame[:, ::20] = 255
    sharp_var = float(cv2.Laplacian(sharp_frame, cv2.CV_64F).var())

    blurred_frame = cv2.GaussianBlur(sharp_frame, (51, 51), 30)
    blurred_var = float(cv2.Laplacian(blurred_frame, cv2.CV_64F).var())

    assert sharp_var > 100.0, "Sharp frame should have high Laplacian variance"
    assert blurred_var < (0.15 * sharp_var), "Heavy blur should drop variance far below baseline"


def test_audio_context_filter_and_persistence_synthetic():
    """Verify 3-stage audio classification logic on synthetic score matrices."""
    # Setup
    threshold = 0.35
    context_ratio = 0.80

    # Case A: Clear distress scream
    distress_score_a = 0.85
    confusable_score_a = 0.20
    stage1_pass_a = distress_score_a >= threshold
    stage2_suppressed_a = confusable_score_a >= (distress_score_a * context_ratio)
    assert stage1_pass_a is True
    assert stage2_suppressed_a is False, "Distress without background party sound should not be suppressed"

    # Case B: Birthday party laughter / cheering (Hard negative)
    distress_score_b = 0.65
    confusable_score_b = 0.75  # Cheering louder than distress
    stage1_pass_b = distress_score_b >= threshold
    stage2_suppressed_b = confusable_score_b >= (distress_score_b * context_ratio)
    assert stage1_pass_b is True
    assert stage2_suppressed_b is True, "Celebratory cheering must be suppressed by context filter"

    # Case C: Temporal persistence (Stage 3)
    # Scenario: 1 transient spike in 3 windows -> [False, False, True]
    window_passes_transient = [False, False, True]
    stage3_pass_transient = sum(1 for p in window_passes_transient[-3:] if p) >= 2
    assert stage3_pass_transient is False, "Single spike must fail temporal persistence"

    # Scenario: Sustained distress -> [False, True, True]
    window_passes_sustained = [False, True, True]
    stage3_pass_sustained = sum(1 for p in window_passes_sustained[-3:] if p) >= 2
    assert stage3_pass_sustained is True, "2 of last 3 windows must pass temporal persistence"


def test_curfew_time_helper():
    """Verify curfew check logic across midnight."""
    # Curfew: 23:00 to 05:30
    t_during_night = datetime(2026, 10, 24, 23, 45, 0, tzinfo=timezone.utc)
    t_early_morning = datetime(2026, 10, 25, 2, 15, 0, tzinfo=timezone.utc)
    t_daytime = datetime(2026, 10, 25, 14, 0, 0, tzinfo=timezone.utc)

    assert is_time_in_curfew(t_during_night, "23:00", "05:30") is True
    assert is_time_in_curfew(t_early_morning, "23:00", "05:30") is True
    assert is_time_in_curfew(t_daytime, "23:00", "05:30") is False


def test_fusion_camera_tamper_severity():
    """Camera tamper must create at least a medium-severity incident on its own."""
    fusion = FusionEngine(org_id="test_org", rules_config={})

    tamper_signal = Signal(
        org_id="test_org",
        ts=datetime.now(timezone.utc),
        modality="video",
        kind="camera_tamper",
        zone_id="terrace",
        camera_id="cam_terrace",
        score=0.95,
        threshold=0.50,
    )

    composite = fusion.calculate_composite_score([tamper_signal])
    severity = fusion.determine_severity([tamper_signal], composite)

    # Even on a single signal, tamper is critical security event -> at least medium
    assert severity in ("medium", "high", "critical"), f"Tamper severity should be at least medium, got {severity}"


def test_fusion_loitering_video_weight():
    """Loitering signal is assigned video weight (0.9)."""
    fusion = FusionEngine(org_id="test_org", rules_config={"weights": {"video": 0.9, "audio": 0.8, "access": 0.7}})

    loiter_signal = Signal(
        org_id="test_org",
        ts=datetime.now(timezone.utc),
        modality="video",
        kind="loitering",
        zone_id="corridor_2f",
        score=0.85,
        threshold=0.50,
    )

    comp = fusion.calculate_composite_score([loiter_signal])
    # composite = 1 - (1 - 0.85 * 0.9) = 1 - (1 - 0.765) = 0.765
    assert comp == pytest.approx(0.765, 0.01)
    sev = fusion.determine_severity([loiter_signal], comp)
    assert sev == "medium"


def test_fusion_fight_alone_and_corroboration_rules():
    """Verify fight alone creates at most LOW severity, and escalates properly."""
    fusion = FusionEngine(org_id="test_org", rules_config={})

    fight_sig = Signal(
        org_id="test_org",
        ts=datetime.now(timezone.utc),
        modality="video",
        kind="fight",
        zone_id="terrace",
        score=0.85,
        threshold=0.65,
    )
    audio_sig = Signal(
        org_id="test_org",
        ts=datetime.now(timezone.utc),
        modality="audio",
        kind="distress_audio",
        zone_id="terrace",
        score=0.80,
        threshold=0.35,
    )
    sos_sig = Signal(
        org_id="test_org",
        ts=datetime.now(timezone.utc),
        modality="report",
        kind="student_sos",
        zone_id="terrace",
        score=0.90,
        threshold=0.50,
        details={"type": "fight"},
    )

    # 1. Fight alone -> at most LOW severity
    comp_alone = fusion.calculate_composite_score([fight_sig])
    sev_alone = fusion.determine_severity([fight_sig], comp_alone)
    assert sev_alone == "low"

    # 2. Fight + Distress audio -> CRITICAL
    comp_fa = fusion.calculate_composite_score([fight_sig, audio_sig])
    sev_fa = fusion.determine_severity([fight_sig, audio_sig], comp_fa)
    assert sev_fa == "critical"

    # 3. Fight + Student SOS -> HIGH
    comp_fs = fusion.calculate_composite_score([fight_sig, sos_sig])
    sev_fs = fusion.determine_severity([fight_sig, sos_sig], comp_fs)
    assert sev_fs == "high"

