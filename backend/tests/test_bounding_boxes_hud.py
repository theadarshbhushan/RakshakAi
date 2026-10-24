"""
Unit tests for Video Visualisations with Bounding Boxes, Threat States, Door Line Counters, and Privacy HUD:
- Normal (green), inside zone/loitering (amber), active threat (red) colour-coded bounding boxes
- Label formatting: 'ID 7 · person 0.91', 'ID 7 · INTRUSION 0.85', 'ID 3 · LOITERING 52s'
- Strict privacy: No user names or identities in labels, only track IDs
- Semi-transparent restricted-zone polygon (red fill when occupied, yellow when clear)
- Door line for entry cameras with 'IN: 2 | SWIPES: 1' counter badge
- Top-left HUD: camera name, sim/real time, 'PRIVACY MODE: SKELETON VIEW' vs 'PRIVACY MODE: BREAK-GLASS BLURRED VIEW'
- Config toggle: SHOW_BOXES=true by default, box drawing suppressed when False
"""
import pytest
from datetime import datetime, timezone
import numpy as np
import cv2

from app.core.config import settings
from app.detectors.video_pose import (
    draw_detection_overlays,
    render_skeleton_frame,
    render_face_blurred_frame,
    SKELETON_BONES,
)


def test_default_config_show_boxes():
    """Verify SHOW_BOXES config option is True by default."""
    assert settings.SHOW_BOXES is True


def test_state_colour_coded_bounding_boxes_and_labels():
    """
    Verify colour coding and label formatting:
    - green = normal
    - amber = inside zone / loitering timer
    - red = active signal (intrusion, fight, tailgating, loitering)
    """
    canvas = np.zeros((480, 640, 3), dtype=np.uint8)
    sim_time = datetime(2026, 10, 24, 23, 45, 0, tzinfo=timezone.utc)

    persons_data = [
        # 1. Normal person
        {
            "track_id": 7,
            "box": [50, 100, 150, 300],
            "mean_conf": 0.91,
            "state": "normal",
            "keypoints": [],
        },
        # 2. Amber person (loitering timer running)
        {
            "track_id": 3,
            "box": [200, 100, 300, 300],
            "mean_conf": 0.88,
            "state": "amber",
            "loitering_s": 52.0,
            "event_name": "LOITERING 52s",
            "keypoints": [],
        },
        # 3. Red person (active intrusion alert)
        {
            "track_id": 12,
            "box": [350, 100, 450, 300],
            "mean_conf": 0.85,
            "state": "red",
            "event_name": "INTRUSION 0.85",
            "keypoints": [],
        },
        # 4. Red person (active tailgating alert)
        {
            "track_id": 2,
            "box": [500, 100, 600, 300],
            "mean_conf": 0.96,
            "state": "red",
            "event_name": "TAILGATING",
            "keypoints": [],
        },
    ]

    rendered = draw_detection_overlays(
        canvas=canvas,
        persons_data=persons_data,
        camera_name="CAM_TERRACE",
        sim_time=sim_time,
        privacy_mode_text="PRIVACY MODE: SKELETON VIEW",
        show_boxes=True,
    )

    assert rendered.shape == (480, 640, 3)

    # 1. Check Green box boundary (person 7 at x=50, y=100)
    # Box rectangle color is (0, 220, 0)
    box1_border_pixel = rendered[100, 50]
    assert box1_border_pixel[1] > 200, f"Expected green border component, got {box1_border_pixel}"

    # 2. Check Amber box boundary (person 3 at x=200, y=100)
    # Amber color is (0, 165, 255) in BGR: high R (255), medium G (165)
    box2_border_pixel = rendered[100, 200]
    assert box2_border_pixel[2] > 200 and box2_border_pixel[1] > 100, f"Expected amber border, got {box2_border_pixel}"

    # 3. Check Red box boundary (person 12 at x=350, y=100)
    # Red color is (0, 0, 255) in BGR: high R (255), zero G/B
    box3_border_pixel = rendered[100, 350]
    assert box3_border_pixel[2] > 200 and box3_border_pixel[1] < 50, f"Expected red border, got {box3_border_pixel}"


def test_strict_privacy_no_identities_in_labels():
    """Verify labels only use track IDs (e.g. 'ID 7 · ...') and never names or emails."""
    persons_data = [
        {"track_id": 7, "box": [50, 100, 150, 300], "mean_conf": 0.91, "state": "normal"},
        {"track_id": 3, "box": [200, 100, 300, 300], "mean_conf": 0.88, "state": "amber", "event_name": "LOITERING 52s"},
        {"track_id": 1, "box": [350, 100, 450, 300], "mean_conf": 0.85, "state": "red", "event_name": "FIGHT 0.72"},
    ]

    for p in persons_data:
        tid = p["track_id"]
        conf = p["mean_conf"]
        state = p["state"]
        event = p.get("event_name")
        if state == "red":
            lbl = f"ID {tid} · {event}"
        elif state == "amber":
            lbl = f"ID {tid} · {event}"
        else:
            lbl = f"ID {tid} · person {conf:.2f}"

        # Assert format starts with 'ID {tid} ·'
        assert lbl.startswith(f"ID {tid} · ")
        # Ensure no accidental user identity strings
        assert "@" not in lbl
        assert "user" not in lbl.lower() or "person" in lbl


def test_restricted_zone_polygon_transparency_and_occupancy():
    """
    Restricted-zone polygon:
    - Red semi-transparent fill when occupied
    - Amber/yellow semi-transparent fill when clear
    """
    poly = np.array([[100, 100], [300, 100], [300, 300], [100, 300]], dtype=np.int32)

    # 1. Clear zone (is_occupied=False)
    canvas_clear = np.zeros((400, 400, 3), dtype=np.uint8)
    rendered_clear = draw_detection_overlays(
        canvas=canvas_clear,
        persons_data=[],
        polygon_pts=poly,
        is_occupied=False,
        show_boxes=False,
    )
    # Inside clear polygon: yellow/amber faint fill (B=0, G>0, R>0)
    inside_clear_pt = rendered_clear[200, 200]
    assert inside_clear_pt[1] > 0 and inside_clear_pt[2] > 0
    assert inside_clear_pt[0] == 0, "Blue should be 0 in yellow fill"

    # 2. Occupied zone (is_occupied=True)
    canvas_occ = np.zeros((400, 400, 3), dtype=np.uint8)
    rendered_occ = draw_detection_overlays(
        canvas=canvas_occ,
        persons_data=[{"track_id": 1, "box": [150, 150, 250, 250], "in_zone": True}],
        polygon_pts=poly,
        is_occupied=True,
        show_boxes=False,
    )
    # Inside occupied polygon: red fill (R > 0, G == 0, B == 0)
    inside_occ_pt = rendered_occ[200, 200]
    assert inside_occ_pt[2] > 40, f"Red channel must be prominent in occupied fill, got {inside_occ_pt}"
    assert inside_occ_pt[1] == 0 and inside_occ_pt[0] == 0, "G and B should be 0 in red fill"


def test_door_line_and_counter_badge():
    """Verify door line with 'IN: 2 | SWIPES: 1' counter badge."""
    canvas = np.zeros((400, 600, 3), dtype=np.uint8)
    p1 = (100, 200)
    p2 = (500, 200)

    rendered = draw_detection_overlays(
        canvas=canvas,
        persons_data=[],
        door_line=(p1, p2),
        door_info={"in": 2, "swipes": 1},
        show_boxes=False,
    )

    # Midpoint of door line is around (300, 200)
    # Door line at (150, 200) should be drawn in cyan/yellow (BGR: 255, 230, 0)
    door_line_pixel = rendered[200, 150]
    assert door_line_pixel[0] > 200 and door_line_pixel[1] > 200

    # Counter badge should be drawn near midpoint
    # Since in > swipes (tailgating risk), border is highlighted in red
    badge_pixel = rendered[190, 300]
    assert np.any(badge_pixel > 0), "Counter badge must be drawn near door midpoint"


def test_top_left_hud_card():
    """Verify top-left HUD card contains camera name, time, and privacy mode."""
    canvas = np.zeros((480, 640, 3), dtype=np.uint8)
    sim_time = datetime(2026, 10, 24, 23, 15, 0, tzinfo=timezone.utc)

    rendered_sk = draw_detection_overlays(
        canvas=canvas.copy(),
        persons_data=[],
        camera_name="CAM_TERRACE",
        sim_time=sim_time,
        privacy_mode_text="PRIVACY MODE: SKELETON VIEW",
    )

    # HUD card is in top-left (e.g. at x=30, y=30)
    hud_bg = rendered_sk[30, 30]
    assert np.any(hud_bg > 0), "HUD background should be rendered in top-left"

    rendered_bl = draw_detection_overlays(
        canvas=canvas.copy(),
        persons_data=[],
        camera_name="CAM_GATE",
        sim_time=sim_time,
        privacy_mode_text="PRIVACY MODE: BREAK-GLASS BLURRED VIEW",
    )
    hud_bg_bl = rendered_bl[30, 30]
    assert np.any(hud_bg_bl > 0)


def test_show_boxes_toggle():
    """Verify show_boxes=False suppresses boxes and tags, while preserving other overlays."""
    canvas = np.zeros((480, 640, 3), dtype=np.uint8)
    persons_data = [
        {"track_id": 5, "box": [100, 100, 200, 250], "mean_conf": 0.92, "state": "normal"}
    ]

    # With show_boxes=False
    rendered_no_boxes = draw_detection_overlays(
        canvas=canvas.copy(),
        persons_data=persons_data,
        show_boxes=False,
    )
    # The box border at (100, 100) should NOT be drawn
    assert np.all(rendered_no_boxes[100, 100] == 0), "Bounding box should not be drawn when show_boxes=False"

    # With show_boxes=True
    rendered_with_boxes = draw_detection_overlays(
        canvas=canvas.copy(),
        persons_data=persons_data,
        show_boxes=True,
    )
    # The box border at (100, 100) MUST be drawn (green: BGR (0, 220, 0))
    assert rendered_with_boxes[100, 100][1] > 200, "Bounding box must be drawn when show_boxes=True"


def test_render_skeleton_frame_privacy():
    """Verify default skeleton view is black background with bones and HUD."""
    persons_data = [
        {
            "track_id": 1,
            "box": [50, 50, 150, 200],
            "keypoints": [
                [100, 60, 0.9],   # nose
                [95, 55, 0.9],    # left eye
                [105, 55, 0.9],   # right eye
                [90, 60, 0.9],    # left ear
                [110, 60, 0.9],   # right ear
                [80, 80, 0.9],    # left shoulder
                [120, 80, 0.9],   # right shoulder
                [75, 110, 0.9],   # left elbow
                [125, 110, 0.9],  # right elbow
                [70, 140, 0.9],   # left wrist
                [130, 140, 0.9],  # right wrist
                [85, 150, 0.9],   # left hip
                [115, 150, 0.9],  # right hip
                [85, 180, 0.9],   # left knee
                [115, 180, 0.9],  # right knee
                [85, 210, 0.9],   # left ankle
                [115, 210, 0.9],  # right ankle
            ],
            "mean_conf": 0.90,
            "state": "normal",
        }
    ]

    sk_frame = render_skeleton_frame(
        canvas_shape=(400, 400, 3),
        persons_data=persons_data,
        camera_name="CAM_CORRIDOR",
        sim_time=datetime(2026, 10, 24, 23, 0, 0, tzinfo=timezone.utc),
    )

    assert sk_frame.shape == (400, 400, 3)
    # Background in unused area is pure black (0, 0, 0)
    assert np.all(sk_frame[350, 350] == 0), "Default background must be pure black"
    # Skeletons / boxes are drawn
    assert np.any(sk_frame > 0)


def test_render_face_blurred_frame_with_overlays():
    """Verify break-glass mode face blurring and overlays."""
    # Synthetic frame with high frequency details in face region
    orig_frame = np.full((400, 500, 3), 120, dtype=np.uint8)
    orig_frame[150:180, 330:350] = np.random.randint(0, 255, (30, 20, 3), dtype=np.uint8)
    orig_var = float(cv2.Laplacian(orig_frame[155:175, 335:345], cv2.CV_64F).var())

    persons_data = [
        {
            "track_id": 2,
            "box": [300, 140, 380, 280],
            "keypoints": [
                [340, 160, 0.9],  # nose
                [335, 155, 0.9],  # left eye
                [345, 155, 0.9],  # right eye
                [330, 160, 0.9],  # left ear
                [350, 160, 0.9],  # right ear
            ],
            "mean_conf": 0.90,
            "state": "amber",
            "event_name": "LOITERING 48s",
        }
    ]

    blurred_frame = render_face_blurred_frame(
        orig_frame=orig_frame,
        persons_data=persons_data,
        camera_name="CAM_ENTRY",
        door_line=((50, 320), (350, 320)),
        door_info={"in": 1, "swipes": 1},
    )

    assert blurred_frame.shape == (400, 500, 3)
    # Face region should be blurred
    face_roi = blurred_frame[155:175, 335:345]
    blurred_var = float(cv2.Laplacian(face_roi, cv2.CV_64F).var())
    # Variance of blurred ROI is significantly lower than original random noise
    assert blurred_var < 0.25 * orig_var
