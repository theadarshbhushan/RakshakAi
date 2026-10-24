"""
Synthetic video and audio placeholder generator for RakshakAI.
Generates realistic video feeds with OpenCV stick-figure humanoids (detectable by YOLO pose)
and synthetic/ESC-50 audio files so scenarios run out-of-the-box on any fresh clone.
"""
import math
import os
import shutil
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import soundfile as sf

from app.core.config import settings


def draw_humanoid(
    frame: np.ndarray,
    center_x: int,
    center_y: int,
    height: int = 140,
    color: Tuple[int, int, int] = (220, 220, 220),
    arm_angle: float = 0.0,
    leg_offset: float = 0.0,
) -> None:
    """
    Draw an OpenCV humanoid with head, torso, arms, legs, and ankles
    with contrast that YOLO pose models detect as person keypoints.
    """
    # Scale parts
    head_r = int(height * 0.12)
    head_y = center_y - int(height * 0.42)
    torso_top_y = head_y + head_r
    torso_bot_y = center_y + int(height * 0.1)
    
    # 1. Head (filled circle with inner contrast)
    cv2.circle(frame, (center_x, head_y), head_r, color, -1)
    cv2.circle(frame, (center_x, head_y), head_r, (40, 40, 40), 2)
    # Eyes
    cv2.circle(frame, (center_x - int(head_r * 0.35), head_y - int(head_r * 0.1)), 2, (30, 30, 30), -1)
    cv2.circle(frame, (center_x + int(head_r * 0.35), head_y - int(head_r * 0.1)), 2, (30, 30, 30), -1)

    # 2. Torso (thick line / rectangle)
    cv2.line(frame, (center_x, torso_top_y), (center_x, torso_bot_y), color, 14)
    cv2.line(frame, (center_x, torso_top_y), (center_x, torso_bot_y), (30, 30, 30), 2)

    # 3. Shoulders & Arms
    shoulder_y = torso_top_y + int(height * 0.05)
    shoulder_w = int(height * 0.18)
    # Left arm
    elbow_l_x = center_x - shoulder_w - int(math.sin(arm_angle) * 10)
    elbow_l_y = shoulder_y + int(height * 0.15)
    wrist_l_x = elbow_l_x - int(math.cos(arm_angle) * 15)
    wrist_l_y = elbow_l_y + int(height * 0.15)
    cv2.line(frame, (center_x, shoulder_y), (elbow_l_x, elbow_l_y), color, 8)
    cv2.line(frame, (elbow_l_x, elbow_l_y), (wrist_l_x, wrist_l_y), color, 7)

    # Right arm
    elbow_r_x = center_x + shoulder_w + int(math.sin(arm_angle) * 10)
    elbow_r_y = shoulder_y + int(height * 0.15)
    wrist_r_x = elbow_r_x + int(math.cos(arm_angle) * 15)
    wrist_r_y = elbow_r_y + int(height * 0.15)
    cv2.line(frame, (center_x, shoulder_y), (elbow_r_x, elbow_r_y), color, 8)
    cv2.line(frame, (elbow_r_x, elbow_r_y), (wrist_r_x, wrist_r_y), color, 7)

    # 4. Hips & Legs (Left and right with stride)
    hip_w = int(height * 0.10)
    knee_l_x = center_x - hip_w + int(leg_offset * 12)
    knee_l_y = torso_bot_y + int(height * 0.2)
    ankle_l_x = knee_l_x + int(leg_offset * 15)
    ankle_l_y = center_y + int(height * 0.45)

    knee_r_x = center_x + hip_w - int(leg_offset * 12)
    knee_r_y = torso_bot_y + int(height * 0.2)
    ankle_r_x = knee_r_x - int(leg_offset * 15)
    ankle_r_y = center_y + int(height * 0.45)

    cv2.line(frame, (center_x - int(hip_w * 0.5), torso_bot_y), (knee_l_x, knee_l_y), color, 9)
    cv2.line(frame, (knee_l_x, knee_l_y), (ankle_l_x, ankle_l_y), color, 8)
    cv2.circle(frame, (ankle_l_x, ankle_l_y), 4, (60, 60, 60), -1)

    cv2.line(frame, (center_x + int(hip_w * 0.5), torso_bot_y), (knee_r_x, knee_r_y), color, 9)
    cv2.line(frame, (knee_r_x, knee_r_y), (ankle_r_x, ankle_r_y), color, 8)
    cv2.circle(frame, (ankle_r_x, ankle_r_y), 4, (60, 60, 60), -1)


def generate_intrusion_video(output_path: Path, width: int = 640, height: int = 480, fps: int = 15, duration_s: int = 6) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    total_frames = int(fps * duration_s)
    # Zone polygon roughly center-right (normalized 0.35 to 0.75 in x, 0.3 to 0.8 in y)
    poly = np.array([
        [int(width * 0.35), int(height * 0.30)],
        [int(width * 0.75), int(height * 0.30)],
        [int(width * 0.75), int(height * 0.80)],
        [int(width * 0.35), int(height * 0.80)],
    ], dtype=np.int32)

    # Person walks from x=80, y=260 into x=360, y=260 (inside polygon)
    start_x, end_x = 80, int(width * 0.55)
    y_pos = int(height * 0.55)

    for i in range(total_frames):
        # Background: dark hostel terrace / floor
        frame = np.full((height, width, 3), (45, 50, 55), dtype=np.uint8)
        # Floor lines
        cv2.line(frame, (0, int(height * 0.65)), (width, int(height * 0.65)), (65, 70, 75), 2)
        # Draw zone boundary marker
        cv2.polylines(frame, [poly], isClosed=True, color=(70, 140, 200), thickness=2)

        # Progress
        t = min(1.0, i / (total_frames * 0.75))
        curr_x = int(start_x + (end_x - start_x) * t)
        stride = math.sin(i * 0.6)
        arm = math.cos(i * 0.6)

        draw_humanoid(frame, curr_x, y_pos, height=180, color=(210, 215, 220), arm_angle=arm, leg_offset=stride)
        out.write(frame)

    out.release()
    return output_path


def generate_tailgating_video(output_path: Path, width: int = 640, height: int = 480, fps: int = 15, duration_s: int = 6) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    total_frames = int(fps * duration_s)
    # Door line at y = 0.5 (height * 0.5)
    door_y = int(height * 0.5)

    # Person 1 starts at y=100, moves to y=380
    # Person 2 follows closely: starts at y=40, moves to y=320
    for i in range(total_frames):
        frame = np.full((height, width, 3), (40, 42, 48), dtype=np.uint8)
        # Turnstile lane lines
        cv2.line(frame, (int(width * 0.35), 0), (int(width * 0.35), height), (80, 80, 90), 2)
        cv2.line(frame, (int(width * 0.65), 0), (int(width * 0.65), height), (80, 80, 90), 2)
        # Door line
        cv2.line(frame, (int(width * 0.35), door_y), (int(width * 0.65), door_y), (0, 165, 255), 3)

        t1 = min(1.0, i / (total_frames * 0.6))
        p1_y = int(100 + (360 - 100) * t1)
        stride1 = math.sin(i * 0.5)

        # Person 2 follows closely (lagged)
        t2 = max(0.0, min(1.0, (i - 12) / (total_frames * 0.6)))
        p2_y = int(60 + (320 - 60) * t2)
        stride2 = math.sin(i * 0.5 + 1.2)

        draw_humanoid(frame, int(width * 0.5), p1_y, height=160, color=(200, 220, 240), leg_offset=stride1)
        if i >= 6:
            draw_humanoid(frame, int(width * 0.5), p2_y, height=155, color=(230, 210, 190), leg_offset=stride2)

        out.write(frame)

    out.release()
    return output_path


def generate_normal_video(output_path: Path, width: int = 640, height: int = 480, fps: int = 15, duration_s: int = 6) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    total_frames = int(fps * duration_s)
    for i in range(total_frames):
        frame = np.full((height, width, 3), (35, 38, 42), dtype=np.uint8)
        # Normal room view with ambient lighting
        cv2.rectangle(frame, (int(width * 0.1), int(height * 0.2)), (int(width * 0.9), int(height * 0.8)), (50, 55, 60), 1)
        # Person walking peacefully across bottom
        t = i / total_frames
        curr_x = int(50 + (width - 100) * t)
        stride = math.sin(i * 0.4)
        draw_humanoid(frame, curr_x, int(height * 0.65), height=150, color=(190, 210, 190), leg_offset=stride)
        out.write(frame)

    out.release()
    return output_path


def generate_audio_file(output_path: Path, sound_type: str = "distress", duration_s: float = 3.0, sr: int = 16000) -> Path:
    """
    Generate synthetic WAV audio file for distress (screaming/crying), cheering/laughter, or ambient noise.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = int(duration_s * sr)
    t = np.linspace(0, duration_s, n_samples, endpoint=False)

    if sound_type == "distress":
        # Frequency modulation between 900 Hz and 2400 Hz simulating a distress scream
        base_f = 1100.0 + 800.0 * np.sin(2 * np.pi * 3.5 * t)
        carrier = np.sin(2 * np.pi * base_f * t)
        harmonic1 = 0.5 * np.sin(2 * np.pi * (base_f * 2.0) * t)
        harmonic2 = 0.25 * np.sin(2 * np.pi * (base_f * 3.0) * t)
        noise = 0.12 * np.random.normal(0, 1, n_samples)
        # Envelope: sharp rise, sustained vibrato
        env = np.clip(t / 0.15, 0, 1) * np.clip((duration_s - t) / 0.3, 0, 1)
        audio = (carrier + harmonic1 + harmonic2 + noise) * env * 0.8
    elif sound_type in ("cheering", "laughter", "hard_negative"):
        # Pulsed bursts simulating laughter / cheering (4 Hz pulses of harmonic audio)
        pulse = np.maximum(0.0, np.sin(2 * np.pi * 4.2 * t)) ** 2
        carrier = np.sin(2 * np.pi * 480.0 * t) + 0.4 * np.sin(2 * np.pi * 960.0 * t)
        noise = 0.2 * np.random.normal(0, 1, n_samples)
        audio = (carrier * pulse + noise * 0.3) * 0.7
    else:
        # Quiet ambient / room tone
        noise = 0.02 * np.random.normal(0, 1, n_samples)
        audio = noise

    audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
    sf.write(str(output_path), audio, sr)
    return output_path


def ensure_media_fixtures(data_dir: Optional[Path] = None) -> None:
    """
    Ensure all required video and audio scenario files exist.
    If real datasets are in raw_datasets, copies relevant files; otherwise generates synthetic placeholders.
    """
    root = data_dir or settings.DATA_DIR
    raw = root / "raw_datasets"

    # Targets
    v_intrusion = root / "videos" / "intrusion" / "intrusion_01.mp4"
    v_tailgate = root / "videos" / "tailgating" / "tailgate_01.mp4"
    v_normal = root / "videos" / "normal" / "normal_01.mp4"
    v_fight = root / "videos" / "fight" / "fight_01.mp4"

    a_distress = root / "audio" / "distress" / "distress_01.wav"
    a_hard_neg = root / "audio" / "hard_negative" / "cheering_01.wav"
    a_normal = root / "audio" / "normal" / "normal_01.wav"

    # Check ESC-50 for real audio if available
    esc_dir = raw / "ESC-50-master" / "audio"
    esc_meta = raw / "ESC-50-master" / "meta" / "esc50.csv"
    if esc_dir.exists() and esc_meta.exists():
        import pandas as pd
        df = pd.read_csv(esc_meta)
        
        # Distress sample (glass_breaking or crying_baby)
        if not a_distress.exists():
            distress_rows = df[df["category"].isin(["glass_breaking", "crying_baby"])]
            if not distress_rows.empty:
                src = esc_dir / distress_rows.iloc[0]["filename"]
                if src.exists():
                    a_distress.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(src, a_distress)

        # Hard negative sample (laughing or clapping)
        if not a_hard_neg.exists():
            hn_rows = df[df["category"].isin(["laughing", "clapping"])]
            if not hn_rows.empty:
                src = esc_dir / hn_rows.iloc[0]["filename"]
                if src.exists():
                    a_hard_neg.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(src, a_hard_neg)

    # Check Real Life Violence for real video if available
    rlv_dir = raw / "Real Life Violence Dataset"
    if rlv_dir.exists():
        v_rows = list((rlv_dir / "Violence").glob("*.mp4")) if (rlv_dir / "Violence").exists() else []
        nv_rows = list((rlv_dir / "NonViolence").glob("*.mp4")) if (rlv_dir / "NonViolence").exists() else []
        if v_rows and not v_fight.exists():
            v_fight.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(v_rows[0], v_fight)
        if nv_rows and not v_normal.exists():
            v_normal.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(nv_rows[0], v_normal)

    # Generate synthetic fallbacks for any still missing
    if not v_intrusion.exists():
        generate_intrusion_video(v_intrusion)
    if not v_tailgate.exists():
        generate_tailgating_video(v_tailgate)
    if not v_normal.exists():
        generate_normal_video(v_normal)
    if not v_fight.exists():
        generate_intrusion_video(v_fight)

    if not a_distress.exists():
        generate_audio_file(a_distress, sound_type="distress")
    if not a_hard_neg.exists():
        generate_audio_file(a_hard_neg, sound_type="cheering")
    if not a_normal.exists():
        generate_audio_file(a_normal, sound_type="normal")
