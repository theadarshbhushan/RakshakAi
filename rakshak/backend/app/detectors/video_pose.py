"""
Real Video Pose & Threat Detector for RakshakAI.
Integrates YOLOv8n-pose with ByteTrack tracking on CPU:
- Zone intrusion via ankle midpoint keypoint polygon test (>= 5 consecutive frames, 20s cooldown)
- Line crossing via door line vector crossing
- Loitering detection in corridors/restricted zones during curfew
- Experimental fight heuristic via box proximity + normalized wrist movement speed
- Camera tamper detection (blackout, heavy blur, sudden view change)
- Privacy-preserving evidence generation (skeleton render on black, Gaussian face blur)
- Real-time in-memory frame buffer for live MJPEG streaming
"""
import asyncio
import logging
import math
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import cv2
import imageio_ffmpeg
import numpy as np
from ultralytics import YOLO

from app.core.config import settings
from app.detectors.base import BaseDetector, SimulationClock
from app.models.signal import Signal

logger = logging.getLogger("rakshakai.detectors.video_pose")

# COCO Keypoint Constants
NOSE = 0
LEFT_EYE = 1
RIGHT_EYE = 2
LEFT_EAR = 3
RIGHT_EAR = 4
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_ELBOW = 7
RIGHT_ELBOW = 8
LEFT_WRIST = 9
RIGHT_WRIST = 10
LEFT_HIP = 11
RIGHT_HIP = 12
LEFT_KNEE = 13
RIGHT_KNEE = 14
LEFT_ANKLE = 15
RIGHT_ANKLE = 16

SKELETON_BONES = [
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_ELBOW),
    (LEFT_ELBOW, LEFT_WRIST),
    (RIGHT_SHOULDER, RIGHT_ELBOW),
    (RIGHT_ELBOW, RIGHT_WRIST),
    (LEFT_SHOULDER, LEFT_HIP),
    (RIGHT_SHOULDER, RIGHT_HIP),
    (LEFT_HIP, RIGHT_HIP),
    (LEFT_HIP, LEFT_KNEE),
    (LEFT_KNEE, LEFT_ANKLE),
    (RIGHT_HIP, RIGHT_KNEE),
    (RIGHT_KNEE, RIGHT_ANKLE),
    (NOSE, LEFT_EYE),
    (NOSE, RIGHT_EYE),
    (LEFT_EYE, LEFT_EAR),
    (RIGHT_EYE, RIGHT_EAR),
]

# Global buffer holding the latest annotated frame per camera for live MJPEG streaming
# Format: camera_id -> {"skeleton": bytes, "blurred": bytes, "updated_at": float}
latest_camera_frames: Dict[str, Dict[str, Any]] = {}

# Shared YOLO model cache to avoid reloading weights repeatedly across detector instances
_cached_yolo_model: Optional[YOLO] = None


def get_yolo_model() -> YOLO:
    global _cached_yolo_model
    if _cached_yolo_model is None:
        model_path = Path("yolov8n-pose.pt")
        if not model_path.exists():
            model_path = settings.BACKEND_DIR / "yolov8n-pose.pt"
        if not model_path.exists():
            model_path = Path("yolov8n-pose.pt")
        _cached_yolo_model = YOLO(str(model_path))
    return _cached_yolo_model


def is_time_in_curfew(sim_time: datetime, start_str: str = "23:00", end_str: str = "05:30") -> bool:
    """Check if sim_time is within curfew window (handles crossing midnight)."""
    t = sim_time.time()
    sh, sm = map(int, start_str.split(":"))
    eh, em = map(int, end_str.split(":"))
    from datetime import time as dtime
    start_t = dtime(sh, sm)
    end_t = dtime(eh, em)

    if start_t > end_t:  # e.g. 23:00 to 05:30
        return t >= start_t or t <= end_t
    return start_t <= t <= end_t


def point_line_side(p: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Signed cross product determining which side of line P1->P2 point P lies on."""
    return (p2[0] - p1[0]) * (p[1] - p1[1]) - (p2[1] - p1[1]) * (p[0] - p1[0])


def draw_detection_overlays(
    canvas: np.ndarray,
    persons_data: List[Dict[str, Any]],
    polygon_pts: Optional[np.ndarray] = None,
    is_occupied: Optional[bool] = None,
    door_line: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
    door_info: Optional[Dict[str, Any]] = None,
    camera_name: Optional[str] = None,
    sim_time: Optional[datetime] = None,
    privacy_mode_text: str = "PRIVACY MODE: SKELETON VIEW",
    show_boxes: Optional[bool] = None,
) -> np.ndarray:
    """
    Unified overlay renderer for all RakshakAI video visualisations
    (skeleton stream, face-blurred stream, evidence stills, and annotated MP4):
    1. Restricted-zone polygon (semi-transparent red fill when occupied, amber/yellow fill when unoccupied)
    2. Door line for entry cameras with in/out counter badge ("IN: 2 | SWIPES: 1")
    3. Tracked person bounding boxes with state-based colours:
       - Green = normal
       - Amber = inside monitored/restricted zone or loitering timer running
       - Red = active threat signal (intrusion, fight, tailgating, loitering)
    4. Label tags above each box: "ID 7 · person 0.91" or "ID 7 · INTRUSION 0.85" / "ID 3 · LOITERING 52s"
       (Strict privacy: never names or identities, only track IDs)
    5. Top-left HUD card: Camera name, sim/real timestamp, and privacy mode indicator
    """
    if show_boxes is None:
        show_boxes = getattr(settings, "SHOW_BOXES", True)

    h, w = canvas.shape[:2]

    # -------------------------------------------------------------
    # 1. Restricted-Zone Polygon Overlay
    # -------------------------------------------------------------
    if polygon_pts is not None and len(polygon_pts) >= 3:
        if isinstance(polygon_pts, list):
            polygon_pts = np.array(polygon_pts, dtype=np.int32)

        # Determine occupancy if not explicitly given
        if is_occupied is None:
            is_occupied = any(
                p.get("in_zone", False) or p.get("state") in ("amber", "red")
                for p in persons_data
            )

        if is_occupied:
            fill_color = (0, 0, 180)      # Deep red fill (BGR)
            border_color = (0, 0, 255)    # Bright red border
            fill_alpha = 0.35
            zone_tag = "RESTRICTED ZONE [OCCUPIED]"
        else:
            fill_color = (0, 90, 90)      # Amber/Yellow dark fill (BGR)
            border_color = (0, 255, 255)  # Bright yellow border
            fill_alpha = 0.20
            zone_tag = "RESTRICTED ZONE"

        overlay = canvas.copy()
        cv2.fillPoly(overlay, [polygon_pts], fill_color)
        cv2.addWeighted(overlay, fill_alpha, canvas, 1.0 - fill_alpha, 0, canvas)
        cv2.polylines(canvas, [polygon_pts], isClosed=True, color=border_color, thickness=2, lineType=cv2.LINE_AA)

        # Polygon header tag near first point
        pt0 = polygon_pts[0]
        if hasattr(pt0, "shape") and len(pt0.shape) > 1:
            pt0 = pt0[0]
        px, py = int(pt0[0]), int(pt0[1])
        px = max(10, min(w - 220, px))
        py = max(20, min(h - 10, py - 6))
        cv2.putText(
            canvas,
            zone_tag,
            (px, py),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            border_color,
            1,
            cv2.LINE_AA,
        )

    # -------------------------------------------------------------
    # 2. Door Line & Crossing Counter (Entry Cameras)
    # -------------------------------------------------------------
    if door_line is not None and len(door_line) == 2:
        p1, p2 = door_line
        p1_i = (int(p1[0]), int(p1[1]))
        p2_i = (int(p2[0]), int(p2[1]))

        # Line and terminal endpoints
        cv2.line(canvas, p1_i, p2_i, (255, 230, 0), 2, cv2.LINE_AA)
        cv2.circle(canvas, p1_i, 5, (255, 230, 0), -1, cv2.LINE_AA)
        cv2.circle(canvas, p2_i, 5, (255, 230, 0), -1, cv2.LINE_AA)

        # Counter badge
        in_c = door_info.get("in", door_info.get("in_count", 0)) if door_info else 0
        swipes_c = door_info.get("swipes", door_info.get("swipes_count", 0)) if door_info else 0
        badge_text = f"IN: {in_c} | SWIPES: {swipes_c}"

        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.45
        (tw, th), bl = cv2.getTextSize(badge_text, font, scale, 1)

        mid_x = int((p1_i[0] + p2_i[0]) / 2)
        mid_y = int((p1_i[1] + p2_i[1]) / 2)

        bx1 = max(4, mid_x - tw // 2 - 8)
        by1 = max(4, mid_y - th - 10)
        bx2 = min(w - 4, bx1 + tw + 16)
        by2 = min(h - 4, by1 + th + 14)

        is_tailgating_risk = (in_c > swipes_c and in_c > 0)
        border_col = (0, 0, 255) if is_tailgating_risk else (255, 230, 0)
        text_col = (0, 100, 255) if is_tailgating_risk else (240, 240, 240)

        # Badge background
        badge_overlay = canvas.copy()
        cv2.rectangle(badge_overlay, (bx1, by1), (bx2, by2), (20, 20, 25), -1)
        cv2.addWeighted(badge_overlay, 0.85, canvas, 0.15, 0, canvas)
        cv2.rectangle(canvas, (bx1, by1), (bx2, by2), border_col, 1, cv2.LINE_AA)
        cv2.putText(canvas, badge_text, (bx1 + 8, by2 - bl - 4), font, scale, text_col, 1, cv2.LINE_AA)

    # -------------------------------------------------------------
    # 3. Tracked Persons Bounding Boxes & State Labels
    # -------------------------------------------------------------
    if show_boxes:
        for p in persons_data:
            box = p.get("box", [0, 0, 0, 0])
            tid = p.get("track_id", 0)
            conf = float(p.get("mean_conf", 0.85))
            state = p.get("state", "normal")
            event_name = p.get("event_name")
            loitering_s = p.get("loitering_s", 0)

            # Determine colour and label text
            if state == "red":
                box_color = (0, 0, 255)      # Red
                text_color = (255, 255, 255)  # White text
                if event_name:
                    label = f"ID {tid} · {event_name.upper()}"
                else:
                    label = f"ID {tid} · ALERT {conf:.2f}"
            elif state == "amber":
                box_color = (0, 165, 255)    # Amber / Orange
                text_color = (0, 0, 0)        # Black text on amber badge
                if event_name:
                    label = f"ID {tid} · {event_name.upper()}"
                elif loitering_s >= 5.0:
                    label = f"ID {tid} · LOITERING {int(loitering_s)}s"
                else:
                    label = f"ID {tid} · person {conf:.2f}"
            else:  # normal
                box_color = (0, 220, 0)      # Green
                text_color = (255, 255, 255)  # White text
                label = f"ID {tid} · person {conf:.2f}"

            x1, y1, x2, y2 = map(int, box)
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))

            if x2 > x1 and y2 > y1:
                # Draw bounding box
                cv2.rectangle(canvas, (x1, y1), (x2, y2), box_color, 2, cv2.LINE_AA)

                # Label badge above the box
                font = cv2.FONT_HERSHEY_SIMPLEX
                scale = 0.44
                (lw, lh), lbl = cv2.getTextSize(label, font, scale, 1)

                badge_y2 = y1 - 3
                badge_y1 = badge_y2 - lh - 6
                badge_x1 = x1
                badge_x2 = min(w - 1, badge_x1 + lw + 8)

                # If badge would clip outside top edge, place inside top of box
                if badge_y1 < 0:
                    badge_y1 = y1 + 2
                    badge_y2 = badge_y1 + lh + 6

                cv2.rectangle(canvas, (badge_x1, badge_y1), (badge_x2, badge_y2), box_color, -1)
                cv2.putText(
                    canvas,
                    label,
                    (badge_x1 + 4, badge_y2 - lbl - 2),
                    font,
                    scale,
                    text_color,
                    1,
                    cv2.LINE_AA,
                )

    # -------------------------------------------------------------
    # 4. Top-Left HUD Card
    # -------------------------------------------------------------
    cam_str = f"CAM: {camera_name}" if camera_name else "CAM: CAM_01"
    if sim_time:
        if isinstance(sim_time, datetime):
            time_str = sim_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = str(sim_time)
    else:
        time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    hud_font = cv2.FONT_HERSHEY_SIMPLEX
    (tw_cam, _), _ = cv2.getTextSize(cam_str, hud_font, 0.46, 1)
    (tw_time, _), _ = cv2.getTextSize(time_str, hud_font, 0.42, 1)
    (tw_mode, _), _ = cv2.getTextSize(privacy_mode_text, hud_font, 0.44, 1)
    hud_w = max(240, max(tw_cam, tw_time, tw_mode) + 26)
    hud_h = 72

    # Draw semi-transparent dark HUD card
    hud_overlay = canvas.copy()
    cv2.rectangle(hud_overlay, (12, 12), (12 + hud_w, 12 + hud_h), (18, 18, 22), -1)
    cv2.addWeighted(hud_overlay, 0.78, canvas, 0.22, 0, canvas)
    cv2.rectangle(canvas, (12, 12), (12 + hud_w, 12 + hud_h), (60, 60, 70), 1, cv2.LINE_AA)

    # HUD Texts
    cv2.putText(canvas, cam_str, (20, 31), hud_font, 0.46, (240, 240, 240), 1, cv2.LINE_AA)
    cv2.putText(canvas, time_str, (20, 51), hud_font, 0.42, (180, 205, 205), 1, cv2.LINE_AA)

    mode_color = (0, 255, 128) if "SKELETON" in privacy_mode_text.upper() else (0, 165, 255)
    cv2.putText(canvas, privacy_mode_text, (20, 71), hud_font, 0.44, mode_color, 1, cv2.LINE_AA)

    return canvas


def render_skeleton_frame(
    canvas_shape: Tuple[int, int, int],
    persons_data: List[Dict[str, Any]],
    polygon_pts: Optional[np.ndarray] = None,
    is_occupied: Optional[bool] = None,
    door_line: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
    door_info: Optional[Dict[str, Any]] = None,
    camera_name: Optional[str] = None,
    sim_time: Optional[datetime] = None,
    show_boxes: Optional[bool] = None,
) -> np.ndarray:
    """
    Renders privacy-preserving skeleton render:
    - Pure black background
    - Zone polygon overlay in semi-transparent red (occupied) or yellow (clear)
    - Track keypoints and bones in cyan and neon green
    - Tracked person bounding boxes colour-coded by state:
      green = normal, amber = inside zone/loitering timer, red = active alert
    - Label tags above each box: "ID 7 · person 0.91" or threat event
    - Top-left HUD card: camera name, sim time, "PRIVACY MODE: SKELETON VIEW"
    """
    canvas = np.zeros(canvas_shape, dtype=np.uint8)

    # 1. Render each person's skeleton bones and joints
    for p in persons_data:
        kpts = p.get("keypoints", [])

        # Draw bones
        for idx1, idx2 in SKELETON_BONES:
            if idx1 < len(kpts) and idx2 < len(kpts):
                pt1, c1 = kpts[idx1][:2], kpts[idx1][2] if len(kpts[idx1]) > 2 else 1.0
                pt2, c2 = kpts[idx2][:2], kpts[idx2][2] if len(kpts[idx2]) > 2 else 1.0
                if c1 > 0.25 and c2 > 0.25:
                    p1_i = (int(pt1[0]), int(pt1[1]))
                    p2_i = (int(pt2[0]), int(pt2[1]))
                    cv2.line(canvas, p1_i, p2_i, (0, 255, 128), 2, cv2.LINE_AA)

        # Draw keypoint dots
        for k in kpts:
            pt, c = k[:2], k[2] if len(k) > 2 else 1.0
            if c > 0.25:
                cv2.circle(canvas, (int(pt[0]), int(pt[1])), 3, (255, 200, 0), -1, cv2.LINE_AA)

    # 2. Render all detection overlays (polygon, door line, bounding boxes, labels, HUD)
    canvas = draw_detection_overlays(
        canvas=canvas,
        persons_data=persons_data,
        polygon_pts=polygon_pts,
        is_occupied=is_occupied,
        door_line=door_line,
        door_info=door_info,
        camera_name=camera_name,
        sim_time=sim_time,
        privacy_mode_text="PRIVACY MODE: SKELETON VIEW",
        show_boxes=show_boxes,
    )

    return canvas


def render_face_blurred_frame(
    orig_frame: np.ndarray,
    persons_data: List[Dict[str, Any]],
    polygon_pts: Optional[np.ndarray] = None,
    is_occupied: Optional[bool] = None,
    door_line: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
    door_info: Optional[Dict[str, Any]] = None,
    camera_name: Optional[str] = None,
    sim_time: Optional[datetime] = None,
    show_boxes: Optional[bool] = None,
) -> np.ndarray:
    """
    Renders restricted-access frame with strict face blurring:
    Gaussian blur over the padded bounding box spanned by nose, eye, and ear keypoints.
    Overlays identical bounding boxes, labels, polygon, door line, and HUD over the face-blurred frame.
    """
    blurred_frame = orig_frame.copy()
    h, w = orig_frame.shape[:2]

    for p in persons_data:
        kpts = p.get("keypoints", [])
        box = p.get("box", [0, 0, 0, 0])

        face_pts = []
        for idx in [NOSE, LEFT_EYE, RIGHT_EYE, LEFT_EAR, RIGHT_EAR]:
            if idx < len(kpts):
                k = kpts[idx]
                c = k[2] if len(k) > 2 else 1.0
                if c > 0.15:
                    face_pts.append((k[0], k[1]))

        if face_pts:
            xs = [pt[0] for pt in face_pts]
            ys = [pt[1] for pt in face_pts]
            pad_x = max(12, int((max(xs) - min(xs)) * 0.4))
            pad_y = max(12, int((max(ys) - min(ys)) * 0.4))

            fx1 = max(0, int(min(xs) - pad_x))
            fy1 = max(0, int(min(ys) - pad_y))
            fx2 = min(w, int(max(xs) + pad_x))
            fy2 = min(h, int(max(ys) + pad_y))
        else:
            # Fallback: Blur top 28% of the person's bounding box
            bx1, by1, bx2, by2 = map(int, box)
            fx1 = max(0, bx1)
            fy1 = max(0, by1)
            fx2 = min(w, bx2)
            fy2 = min(h, by1 + int((by2 - by1) * 0.28))

        if fx2 > fx1 + 4 and fy2 > fy1 + 4:
            roi = blurred_frame[fy1:fy2, fx1:fx2]
            # Heavy Gaussian blur
            ksize = max(15, (roi.shape[1] // 2) * 2 + 1)
            roi_blurred = cv2.GaussianBlur(roi, (ksize, ksize), 30)
            blurred_frame[fy1:fy2, fx1:fx2] = roi_blurred

    # Overlays identical bounding boxes, labels, polygon, door line, and HUD
    blurred_frame = draw_detection_overlays(
        canvas=blurred_frame,
        persons_data=persons_data,
        polygon_pts=polygon_pts,
        is_occupied=is_occupied,
        door_line=door_line,
        door_info=door_info,
        camera_name=camera_name,
        sim_time=sim_time,
        privacy_mode_text="PRIVACY MODE: BREAK-GLASS BLURRED VIEW",
        show_boxes=show_boxes,
    )

    return blurred_frame


class VideoPoseDetector(BaseDetector):
    """
    Real AI Video Pose Detector processing video feeds at ~8 FPS using YOLOv8n-pose.
    """
    def __init__(self, camera_id: Optional[str] = None, zone_id: Optional[str] = None) -> None:
        super().__init__()
        self.camera_id = camera_id
        self.zone_id = zone_id
        self._task: Optional[asyncio.Task] = None
        self.running = False

    async def _load_camera_zone_config(self, camera_id: str, zone_id: str) -> Dict[str, Any]:
        """Load camera and zone configuration from Mongo if available, with resilient defaults."""
        config: Dict[str, Any] = {
            "zone_type": "restricted",
            "polygon": [[0.25, 0.25], [0.85, 0.25], [0.85, 0.85], [0.25, 0.85]],
            "door_line": {"p1": [0.2, 0.5], "p2": [0.8, 0.5]},
            "threshold_intrusion": 0.50,
            "threshold_fight": 0.60,
            "loiter_seconds": 45,
            "curfew_start": "23:00",
            "curfew_end": "05:30",
        }
        try:
            from app.models.zone import Camera, Zone
            from app.models.rules import RuleDocument

            cam_doc = await Camera.find_one({"camera_id": camera_id})
            if cam_doc and cam_doc.door_line:
                config["door_line"] = cam_doc.door_line

            zone_doc = await Zone.find_one({"zone_id": zone_id})
            if zone_doc:
                config["zone_type"] = zone_doc.type
                if zone_doc.polygons and camera_id in zone_doc.polygons:
                    config["polygon"] = zone_doc.polygons[camera_id]
                elif zone_doc.polygons and "default" in zone_doc.polygons:
                    config["polygon"] = zone_doc.polygons["default"]

            rules_doc = await RuleDocument.find_one({"is_active": True})
            if rules_doc:
                curfew = rules_doc.curfew
                if curfew:
                    config["curfew_start"] = curfew.get("start", "23:00")
                    config["curfew_end"] = curfew.get("end", "05:30")
                if rules_doc.zones and zone_id in rules_doc.zones:
                    z_thresh = rules_doc.zones[zone_id].get("thresholds", {})
                    config["threshold_intrusion"] = z_thresh.get("zone_intrusion", 0.50)
                    config["threshold_fight"] = z_thresh.get("fight", 0.60)
                config["loiter_seconds"] = rules_doc.rules.get("loitering", {}).get("seconds", 45)
        except Exception as e:
            logger.debug(f"Config load using default fallbacks: {e}")

        return config

    async def start(
        self,
        source: Any,
        zone_id: str,
        sim_clock: SimulationClock,
        emit_callback: Callable[[Signal], Awaitable[None]],
        loop: bool = True,
        annotated_output_path: Optional[Path] = None,
        progress_callback: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> None:
        self.running = True
        camera_id = self.camera_id or str(source)
        self.zone_id = zone_id

        # Resolve media source path or stream
        cap_arg: Any = source
        if isinstance(source, int):
            cap_arg = source
        elif isinstance(source, str):
            if source.isdigit():
                cap_arg = int(source)
            elif source.startswith("webcam:"):
                parts = source.split(":")
                cap_arg = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            elif source.startswith("rtsp://") or source.startswith("http://") or source.startswith("https://"):
                cap_arg = source
            else:
                src_path = Path(source)
                if not src_path.is_absolute():
                    src_path = settings.DATA_DIR / source
                if not src_path.exists():
                    from app.detectors.synthetic_media import ensure_media_fixtures
                    ensure_media_fixtures()
                    if not src_path.exists():
                        # Fallback to standard fixtures by zone
                        if "tailgate" in source or "block_b" in zone_id:
                            src_path = settings.DATA_DIR / "videos" / "tailgating" / "tailgate_01.mp4"
                        elif "normal" in source or "common" in zone_id:
                            src_path = settings.DATA_DIR / "videos" / "normal" / "normal_01.mp4"
                        else:
                            src_path = settings.DATA_DIR / "videos" / "intrusion" / "intrusion_01.mp4"
                cap_arg = str(src_path)

        logger.info(f"Starting VideoPoseDetector on camera '{camera_id}' zone '{zone_id}' using source '{cap_arg}'")

        # Load config
        cam_config = await self._load_camera_zone_config(camera_id, zone_id)
        door_line_cfg = cam_config.get("door_line")
        poly_norm = cam_config.get("polygon", [])
        threshold_intrusion = float(cam_config.get("threshold_intrusion", 0.50))
        loiter_seconds = float(cam_config.get("loiter_seconds", 45))
        curfew_start = cam_config.get("curfew_start", "23:00")
        curfew_end = cam_config.get("curfew_end", "05:30")

        # Open video capture
        cap = cv2.VideoCapture(cap_arg)
        if not cap.isOpened():
            logger.warning(f"Failed to open video source: {cap_arg}, trying fallback fixture...")
            fallback_path = settings.DATA_DIR / "videos" / "normal" / "normal_01.mp4"
            if fallback_path.exists():
                cap = cv2.VideoCapture(str(fallback_path))
            if not cap.isOpened():
                logger.error(f"Failed to open video source: {cap_arg}")
                return

        model = get_yolo_model()

        # State trackers across frames
        consecutive_inside: Dict[int, int] = {}
        last_intrusion_emit: Dict[int, datetime] = {}
        track_first_seen: Dict[int, datetime] = {}
        last_loitering_emit: Dict[int, datetime] = {}
        prev_centroids: Dict[int, Tuple[float, float]] = {}
        wrist_speeds: Dict[int, List[float]] = {}
        prev_wrist_pos: Dict[int, Tuple[float, float]] = {}
        active_signals: Dict[int, Tuple[str, datetime]] = {}
        door_in_count = 0
        door_swipes_count = 1

        # Tamper detection state
        rolling_laplacian_var: Optional[float] = None
        baseline_hist: Optional[np.ndarray] = None
        view_change_start_ts: Optional[datetime] = None
        last_tamper_emit: Optional[datetime] = None

        # Video recording & progress state
        ffmpeg_proc: Optional[subprocess.Popen] = None
        last_progress_pct = 0
        latest_event_banner: Optional[str] = None
        event_banner_expiry: Optional[datetime] = None

        frame_interval_s = 0.125  # ~8 FPS
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_skip = max(1, int(round(fps / 8.0)))

        frame_count = 0

        while self.running and not sim_clock.is_stopped:
            ret, frame = cap.read()
            if not ret:
                if loop:
                    # Rewind to loop video seamlessly for live simulation
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
                    if not ret:
                        break
                else:
                    break

            frame_count += 1
            if frame_count % frame_skip != 0:
                continue

            current_sim_time = sim_clock.now()

            # Resize to max 640px width
            orig_h, orig_w = frame.shape[:2]
            if orig_w > 640:
                scale = 640.0 / orig_w
                frame_w = 640
                frame_h = int(orig_h * scale)
                frame = cv2.resize(frame, (frame_w, frame_h))
            else:
                frame_w, frame_h = orig_w, orig_h

            # Scale polygon to frame pixels
            poly_px = None
            if poly_norm and len(poly_norm) >= 3:
                poly_px = np.array([
                    [int(pt[0] * frame_w), int(pt[1] * frame_h)]
                    for pt in poly_norm
                ], dtype=np.int32)

            # Convert door line to frame pixels
            p1_px, p2_px = None, None
            door_line_pts = None
            if door_line_cfg and "p1" in door_line_cfg and "p2" in door_line_cfg:
                p1_px = (door_line_cfg["p1"][0] * frame_w, door_line_cfg["p1"][1] * frame_h)
                p2_px = (door_line_cfg["p2"][0] * frame_w, door_line_cfg["p2"][1] * frame_h)
                door_line_pts = (p1_px, p2_px)

            # -------------------------------------------------------------
            # 1. Camera Tamper Detection
            # -------------------------------------------------------------
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_brightness = float(np.mean(gray))
            laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

            # Histogram
            hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
            cv2.normalize(hist, hist)

            tamper_type = None
            tamper_metric = 0.0

            if mean_brightness < 15.0:
                tamper_type = "blackout (near-black frame)"
                tamper_metric = mean_brightness
            elif rolling_laplacian_var is not None and rolling_laplacian_var > 35.0:
                if laplacian_var < 0.15 * rolling_laplacian_var:
                    tamper_type = "heavy blur (lens obstructed/defocused)"
                    tamper_metric = laplacian_var
            elif baseline_hist is not None:
                hist_corr = float(cv2.compareHist(hist, baseline_hist, cv2.HISTCMP_CORREL))
                if hist_corr < 0.35:
                    if view_change_start_ts is None:
                        view_change_start_ts = current_sim_time
                    elif (current_sim_time - view_change_start_ts).total_seconds() > 3.0:
                        tamper_type = "sudden view redirection"
                        tamper_metric = hist_corr
                else:
                    view_change_start_ts = None

            # Update rolling baselines
            if rolling_laplacian_var is None:
                rolling_laplacian_var = laplacian_var
                baseline_hist = hist.copy()
            else:
                rolling_laplacian_var = 0.95 * rolling_laplacian_var + 0.05 * laplacian_var
                if tamper_type is None:
                    baseline_hist = 0.98 * baseline_hist + 0.02 * hist

            # Emit camera_tamper signal if condition met
            if tamper_type:
                cooldown_elapsed = (
                    last_tamper_emit is None or
                    (current_sim_time - last_tamper_emit).total_seconds() > 25.0
                )
                if cooldown_elapsed:
                    last_tamper_emit = current_sim_time
                    tamper_sig = Signal(
                        org_id="",
                        ts=current_sim_time,
                        modality="video",
                        kind="camera_tamper",
                        zone_id=zone_id,
                        camera_id=camera_id,
                        score=0.95,
                        threshold=0.50,
                        details={
                            "tamper_type": tamper_type,
                            "metric": tamper_metric,
                        },
                        source="video_pose",
                    )
                    await emit_callback(tamper_sig)

            # -------------------------------------------------------------
            # 2. YOLOv8 Pose Inference & Tracking
            # -------------------------------------------------------------
            # Run tracker with ByteTrack
            results = model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                verbose=False,
            )

            persons_data: List[Dict[str, Any]] = []
            active_track_ids = set()

            if results and len(results) > 0 and results[0].boxes is not None:
                res = results[0]
                boxes_xyxy = res.boxes.xyxy.cpu().numpy() if res.boxes.xyxy is not None else []
                track_ids_arr = (
                    res.boxes.id.cpu().numpy().astype(int)
                    if res.boxes.id is not None
                    else list(range(len(boxes_xyxy)))
                )
                kpts_arr = (
                    res.keypoints.data.cpu().numpy()
                    if res.keypoints is not None and res.keypoints.data is not None
                    else []
                )

                for b_idx in range(len(boxes_xyxy)):
                    tid = int(track_ids_arr[b_idx])
                    active_track_ids.add(tid)
                    box = boxes_xyxy[b_idx]
                    kpts = kpts_arr[b_idx] if b_idx < len(kpts_arr) else []

                    # Calculate person mean keypoint confidence
                    if len(kpts) > 0:
                        confs = [k[2] for k in kpts if len(k) > 2]
                        mean_conf = float(np.mean(confs)) if confs else 0.8
                    else:
                        mean_conf = 0.8

                    # Track first seen for loitering
                    if tid not in track_first_seen:
                        track_first_seen[tid] = current_sim_time

                    elapsed_s = (current_sim_time - track_first_seen[tid]).total_seconds()

                    # Test point for polygon containment
                    has_ankles = False
                    test_pt = ((box[0] + box[2]) / 2.0, float(box[3]))
                    if len(kpts) > 16:
                        la, ra = kpts[LEFT_ANKLE], kpts[RIGHT_ANKLE]
                        if la[2] > 0.2 and ra[2] > 0.2:
                            test_pt = ((la[0] + ra[0]) / 2.0, (la[1] + ra[1]) / 2.0)
                            has_ankles = True

                    inside = False
                    if poly_px is not None:
                        inside = cv2.pointPolygonTest(poly_px, (float(test_pt[0]), float(test_pt[1])), False) >= 0

                    loiter_running = (
                        cam_config.get("zone_type") in ("corridor", "restricted")
                        and is_time_in_curfew(current_sim_time, curfew_start, curfew_end)
                        and elapsed_s >= 5.0
                    )

                    # Initial person state
                    is_active_threat = (tid in active_signals and current_sim_time <= active_signals[tid][1])
                    if is_active_threat:
                        p_state = "red"
                        p_event = active_signals[tid][0]
                    elif inside or loiter_running:
                        p_state = "amber"
                        p_event = f"LOITERING {int(elapsed_s)}s" if (loiter_running and elapsed_s >= 10.0) else None
                    else:
                        p_state = "normal"
                        p_event = None

                    person_entry = {
                        "track_id": tid,
                        "box": box,
                        "keypoints": kpts,
                        "mean_conf": mean_conf,
                        "state": p_state,
                        "event_name": p_event,
                        "in_zone": inside,
                        "loitering_s": elapsed_s,
                    }
                    persons_data.append(person_entry)

                    # (A) Zone Intrusion Check
                    if poly_px is not None:
                        if inside:
                            consecutive_inside[tid] = consecutive_inside.get(tid, 0) + 1
                        else:
                            consecutive_inside[tid] = 0

                        if consecutive_inside.get(tid, 0) >= 5:
                            last_emit = last_intrusion_emit.get(tid)
                            if last_emit is None or (current_sim_time - last_emit).total_seconds() > 20.0:
                                last_intrusion_emit[tid] = current_sim_time
                                score = max(0.50, min(1.0, mean_conf))
                                event_tag = f"INTRUSION {score:.2f}"
                                active_signals[tid] = (event_tag, current_sim_time + timedelta(seconds=5.0))
                                person_entry["state"] = "red"
                                person_entry["event_name"] = event_tag

                                evidence_id = f"intrusion_{camera_id}_{tid}_{int(current_sim_time.timestamp())}"
                                ev_rel_path = self._save_evidence(
                                    frame=frame,
                                    persons_data=persons_data,
                                    poly_px=poly_px,
                                    prefix=evidence_id,
                                    is_occupied=True,
                                    door_line=door_line_pts,
                                    door_info={"in": door_in_count, "swipes": door_swipes_count},
                                    camera_name=camera_id,
                                    sim_time=current_sim_time,
                                )

                                intrusion_sig = Signal(
                                    org_id="",
                                    ts=current_sim_time,
                                    modality="video",
                                    kind="zone_intrusion",
                                    zone_id=zone_id,
                                    camera_id=camera_id,
                                    score=score,
                                    threshold=threshold_intrusion,
                                    details={
                                        "track_id": tid,
                                        "ankle_point": [round(float(test_pt[0]) / frame_w, 3), round(float(test_pt[1]) / frame_h, 3)],
                                        "bounding_box": [round(float(x) / (frame_w if i % 2 == 0 else frame_h), 3) for i, x in enumerate(box)],
                                        "consecutive_frames": consecutive_inside[tid],
                                    },
                                    evidence_path=ev_rel_path,
                                    source="video_pose",
                                )
                                await emit_callback(intrusion_sig)
                                latest_event_banner = f"ZONE INTRUSION (ID {tid})"
                                event_banner_expiry = current_sim_time + timedelta(seconds=4.0)

                    # (B) Line Crossing Check
                    curr_centroid = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
                    prev_c = prev_centroids.get(tid)
                    if prev_c is None:
                        # Match nearest previous centroid within 120px to handle tracker ID shifts
                        for p_coord in prev_centroids.values():
                            if math.hypot(curr_centroid[0] - p_coord[0], curr_centroid[1] - p_coord[1]) < 120.0:
                                prev_c = p_coord
                                break

                    if p1_px and p2_px and prev_c is not None:
                        side_prev = point_line_side(prev_c, p1_px, p2_px)
                        side_curr = point_line_side(curr_centroid, p1_px, p2_px)

                        # Transition from negative side to positive side -> "in" direction crossing
                        if side_prev < 0 and side_curr >= 0:
                            door_in_count += 1
                            is_tailgating = (door_in_count > door_swipes_count)
                            event_tag = "TAILGATING" if is_tailgating else "CROSSING 0.96"
                            active_signals[tid] = (event_tag, current_sim_time + timedelta(seconds=5.0))
                            person_entry["state"] = "red"
                            person_entry["event_name"] = event_tag

                            evidence_id = f"line_{camera_id}_{tid}_{int(current_sim_time.timestamp())}"
                            ev_rel_path = self._save_evidence(
                                frame=frame,
                                persons_data=persons_data,
                                poly_px=poly_px,
                                prefix=evidence_id,
                                is_occupied=any(p.get("in_zone", False) for p in persons_data),
                                door_line=door_line_pts,
                                door_info={"in": door_in_count, "swipes": door_swipes_count},
                                camera_name=camera_id,
                                sim_time=current_sim_time,
                            )

                            crossing_sig = Signal(
                                org_id="",
                                ts=current_sim_time,
                                modality="video",
                                kind="line_crossing",
                                zone_id=zone_id,
                                camera_id=camera_id,
                                score=0.96,
                                threshold=0.50,
                                details={
                                    "track_id": tid,
                                    "direction": "in",
                                    "door_id": door_line_cfg.get("door_id", f"door_{zone_id}"),
                                    "tailgating": is_tailgating,
                                },
                                evidence_path=ev_rel_path,
                                source="video_pose",
                            )
                            await emit_callback(crossing_sig)

                    prev_centroids[tid] = curr_centroid

                    # (C) Loitering Check
                    if cam_config.get("zone_type") in ("corridor", "restricted") and is_time_in_curfew(current_sim_time, curfew_start, curfew_end):
                        if elapsed_s >= loiter_seconds:
                            last_loiter = last_loitering_emit.get(tid)
                            if last_loiter is None or (current_sim_time - last_loiter).total_seconds() > 30.0:
                                last_loitering_emit[tid] = current_sim_time
                                event_tag = f"LOITERING {int(elapsed_s)}s"
                                active_signals[tid] = (event_tag, current_sim_time + timedelta(seconds=6.0))
                                person_entry["state"] = "red"
                                person_entry["event_name"] = event_tag

                                evidence_id = f"loiter_{camera_id}_{tid}_{int(current_sim_time.timestamp())}"
                                ev_rel_path = self._save_evidence(
                                    frame=frame,
                                    persons_data=persons_data,
                                    poly_px=poly_px,
                                    prefix=evidence_id,
                                    is_occupied=any(p.get("in_zone", False) for p in persons_data),
                                    door_line=door_line_pts,
                                    door_info={"in": door_in_count, "swipes": door_swipes_count},
                                    camera_name=camera_id,
                                    sim_time=current_sim_time,
                                )

                                loiter_sig = Signal(
                                    org_id="",
                                    ts=current_sim_time,
                                    modality="video",
                                    kind="loitering",
                                    zone_id=zone_id,
                                    camera_id=camera_id,
                                    score=0.88,
                                    threshold=0.50,
                                    details={
                                        "track_id": tid,
                                        "duration_s": round(elapsed_s, 1),
                                        "zone_type": cam_config.get("zone_type"),
                                    },
                                    evidence_path=ev_rel_path,
                                    source="video_pose",
                                )
                                await emit_callback(loiter_sig)

                    # (D) Fight Heuristic (if FIGHT_DETECTION is enabled)
                    if settings.FIGHT_DETECTION and len(kpts) > 10:
                        lw, rw = kpts[LEFT_WRIST], kpts[RIGHT_WRIST]
                        if lw[2] > 0.2 or rw[2] > 0.2:
                            w_pt = lw[:2] if lw[2] > rw[2] else rw[:2]
                            box_h = max(1.0, float(box[3] - box[1]))
                            if tid in prev_wrist_pos:
                                pw = prev_wrist_pos[tid]
                                disp = math.hypot(w_pt[0] - pw[0], w_pt[1] - pw[1])
                                norm_speed = (disp / frame_interval_s) / box_h
                                speeds = wrist_speeds.setdefault(tid, [])
                                speeds.append(norm_speed)
                                if len(speeds) > 8:
                                    speeds.pop(0)
                            prev_wrist_pos[tid] = (float(w_pt[0]), float(w_pt[1]))

            # Multi-person proximity fight check
            if settings.FIGHT_DETECTION and len(persons_data) >= 2:
                for idx_a in range(len(persons_data)):
                    for idx_b in range(idx_a + 1, len(persons_data)):
                        pa = persons_data[idx_a]
                        pb = persons_data[idx_b]
                        ba, bb = pa["box"], pb["box"]
                        ca = ((ba[0] + ba[2]) / 2.0, (ba[1] + ba[3]) / 2.0)
                        cb = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
                        wa = ba[2] - ba[0]
                        wb = bb[2] - bb[0]
                        mean_w = (wa + wb) / 2.0
                        dist = math.hypot(ca[0] - cb[0], ca[1] - cb[1])

                        if dist < 1.2 * mean_w:
                            # Check wrist speeds
                            sp_a = wrist_speeds.get(pa["track_id"], [])
                            sp_b = wrist_speeds.get(pb["track_id"], [])
                            if len(sp_a) >= 6 and len(sp_b) >= 6:
                                mean_sp = (np.mean(sp_a) + np.mean(sp_b)) / 2.0
                                if mean_sp > 1.8:  # threshold speed
                                    f_score = round(min(1.0, mean_sp / 3.0), 3)
                                    event_tag = f"FIGHT {f_score:.2f}"
                                    for p_obj in (pa, pb):
                                        p_tid = p_obj["track_id"]
                                        active_signals[p_tid] = (event_tag, current_sim_time + timedelta(seconds=5.0))
                                        p_obj["state"] = "red"
                                        p_obj["event_name"] = event_tag

                                    evidence_id = f"fight_{camera_id}_{pa['track_id']}_{pb['track_id']}_{int(current_sim_time.timestamp())}"
                                    ev_rel_path = self._save_evidence(
                                        frame=frame,
                                        persons_data=persons_data,
                                        poly_px=poly_px,
                                        prefix=evidence_id,
                                        is_occupied=any(p.get("in_zone", False) for p in persons_data),
                                        door_line=door_line_pts,
                                        door_info={"in": door_in_count, "swipes": door_swipes_count},
                                        camera_name=camera_id,
                                        sim_time=current_sim_time,
                                    )

                                    fight_sig = Signal(
                                        org_id="",
                                        ts=current_sim_time,
                                        modality="video",
                                        kind="fight",
                                        zone_id=zone_id,
                                        camera_id=camera_id,
                                        score=f_score,
                                        threshold=cam_config.get("threshold_fight", 0.60),
                                        details={
                                            "track_ids": [pa["track_id"], pb["track_id"]],
                                            "wrist_speed_norm": round(mean_sp, 2),
                                            "experimental": True,
                                        },
                                        evidence_path=ev_rel_path,
                                        source="video_pose",
                                    )
                                    await emit_callback(fight_sig)

            # -------------------------------------------------------------
            # 3. Update Live MJPEG Stream Memory Buffer & Annotated MP4 Pipe
            # -------------------------------------------------------------
            is_occupied = any(p.get("in_zone", False) for p in persons_data)
            door_info = {"in": door_in_count, "swipes": door_swipes_count}

            skeleton_img = render_skeleton_frame(
                canvas_shape=frame.shape,
                persons_data=persons_data,
                polygon_pts=poly_px,
                is_occupied=is_occupied,
                door_line=door_line_pts,
                door_info=door_info,
                camera_name=camera_id,
                sim_time=current_sim_time,
            )
            blurred_img = render_face_blurred_frame(
                orig_frame=frame,
                persons_data=persons_data,
                polygon_pts=poly_px,
                is_occupied=is_occupied,
                door_line=door_line_pts,
                door_info=door_info,
                camera_name=camera_id,
                sim_time=current_sim_time,
            )

            # Annotated video recording if requested
            if annotated_output_path:
                if ffmpeg_proc is None:
                    ffmpeg_bin = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
                    annotated_output_path.parent.mkdir(parents=True, exist_ok=True)
                    ffmpeg_proc = subprocess.Popen([
                        ffmpeg_bin, "-y",
                        "-f", "rawvideo",
                        "-vcodec", "rawvideo",
                        "-s", f"{frame_w}x{frame_h}",
                        "-pix_fmt", "bgr24",
                        "-r", "8",
                        "-i", "-",
                        "-c:v", "libx264",
                        "-preset", "veryfast",
                        "-pix_fmt", "yuv420p",
                        str(annotated_output_path),
                    ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                ann_frame = skeleton_img.copy()
                if latest_event_banner and event_banner_expiry and current_sim_time <= event_banner_expiry:
                    cv2.rectangle(ann_frame, (10, frame_h - 40), (450, frame_h - 10), (0, 0, 180), -1)
                    cv2.putText(
                        ann_frame,
                        f"ALERT: {latest_event_banner}",
                        (16, frame_h - 18),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )

                if ffmpeg_proc and ffmpeg_proc.stdin:
                    try:
                        ffmpeg_proc.stdin.write(ann_frame.tobytes())
                    except Exception as err:
                        logger.warning(f"Error piping frame to ffmpeg: {err}")

            # Report progress if callback supplied
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 0 and progress_callback:
                current_pct = min(95, int((frame_count / total_frames) * 90) + 5)
                if current_pct - last_progress_pct >= 5:
                    last_progress_pct = current_pct
                    await progress_callback(current_pct)

            _, sk_jpg = cv2.imencode(".jpg", skeleton_img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            _, bl_jpg = cv2.imencode(".jpg", blurred_img, [cv2.IMWRITE_JPEG_QUALITY, 80])

            latest_camera_frames[camera_id] = {
                "skeleton": sk_jpg.tobytes(),
                "blurred": bl_jpg.tobytes(),
                "updated_at": time.time(),
            }

            # Pace execution according to simulation clock
            await sim_clock.sleep(frame_interval_s)

        cap.release()
        if ffmpeg_proc and ffmpeg_proc.stdin:
            try:
                ffmpeg_proc.stdin.close()
                ffmpeg_proc.wait(timeout=10)
            except Exception as e:
                logger.warning(f"Error finalizing ffmpeg process: {e}")

        if progress_callback:
            await progress_callback(95)

        logger.info(f"VideoPoseDetector finished for camera '{camera_id}'")

    def _save_evidence(
        self,
        frame: np.ndarray,
        persons_data: List[Dict[str, Any]],
        poly_px: Optional[np.ndarray],
        prefix: str,
        is_occupied: Optional[bool] = None,
        door_line: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
        door_info: Optional[Dict[str, Any]] = None,
        camera_name: Optional[str] = None,
        sim_time: Optional[datetime] = None,
    ) -> str:
        """
        Generates and writes evidence files:
        - data/evidence/public/{prefix}_skeleton.jpg (keypoints on black + polygon overlay + boxes + HUD)
        - data/evidence/restricted/{prefix}_blurred.jpg (strictly face-blurred + boxes + HUD)
        Returns relative path to public evidence.
        """
        pub_dir = settings.DATA_DIR / "evidence" / "public"
        res_dir = settings.DATA_DIR / "evidence" / "restricted"
        pub_dir.mkdir(parents=True, exist_ok=True)
        res_dir.mkdir(parents=True, exist_ok=True)

        skeleton_img = render_skeleton_frame(
            canvas_shape=frame.shape,
            persons_data=persons_data,
            polygon_pts=poly_px,
            is_occupied=is_occupied,
            door_line=door_line,
            door_info=door_info,
            camera_name=camera_name,
            sim_time=sim_time,
        )
        blurred_img = render_face_blurred_frame(
            orig_frame=frame,
            persons_data=persons_data,
            polygon_pts=poly_px,
            is_occupied=is_occupied,
            door_line=door_line,
            door_info=door_info,
            camera_name=camera_name,
            sim_time=sim_time,
        )

        pub_path = pub_dir / f"{prefix}_skeleton.jpg"
        res_path = res_dir / f"{prefix}_blurred.jpg"

        cv2.imwrite(str(pub_path), skeleton_img)
        cv2.imwrite(str(res_path), blurred_img)

        # Return relative path to DATA_DIR
        return f"evidence/public/{pub_path.name}"

    async def stop(self) -> None:
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("VideoPoseDetector stopped.")
