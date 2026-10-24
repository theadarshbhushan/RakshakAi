"""
Cryptographic Evidence Management & In-Memory Watermarking for RakshakAI:
- AES-256-GCM encryption and decryption using EVIDENCE_KEY (64 hex characters).
- Never writes decrypted video or snapshots to disk.
- In-memory watermarking with viewer email, timestamp, and security classification label.
- Targeted face unblurring for authorized emergency reveals, blurring all non-flagged tracks.
"""
import base64
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import imageio_ffmpeg
import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

logger = logging.getLogger("rakshakai.privacy.encryption")


def get_evidence_key() -> bytes:
    """Retrieve and decode 32-byte AES-256-GCM master key from settings."""
    raw_key = settings.EVIDENCE_KEY
    if not raw_key or not raw_key.strip():
        # Fallback check from environment if settings wasn't refreshed
        raw_key = os.getenv("EVIDENCE_KEY", "")
    raw_key = raw_key.strip()
    if not raw_key:
        raise ValueError("EVIDENCE_KEY is missing from environment or backend/.env configuration.")
    try:
        key_bytes = bytes.fromhex(raw_key)
        if len(key_bytes) != 32:
            raise ValueError(f"EVIDENCE_KEY must be exactly 32 bytes (64 hex chars), got {len(key_bytes)} bytes.")
        return key_bytes
    except Exception as exc:
        raise ValueError(f"Invalid EVIDENCE_KEY format: {exc}")


def encrypt_bytes(data: bytes, key: Optional[bytes] = None) -> bytes:
    """
    Encrypt arbitrary bytes with AES-GCM.
    Returns: 12-byte random nonce + ciphertext (with 16-byte GCM authentication tag).
    """
    k = key or get_evidence_key()
    aesgcm = AESGCM(k)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext


def decrypt_bytes(encrypted_data: bytes, key: Optional[bytes] = None) -> bytes:
    """
    Decrypt AES-GCM encrypted bytes (nonce + ciphertext).
    Guarantees authenticity and confidentiality in memory.
    """
    if len(encrypted_data) < 28:
        raise ValueError("Encrypted data payload is too short to contain a valid AES-GCM nonce and tag.")
    k = key or get_evidence_key()
    aesgcm = AESGCM(k)
    nonce = encrypted_data[:12]
    ciphertext = encrypted_data[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)


def get_raw_clips_dir() -> Path:
    raw_dir = settings.DATA_DIR / "evidence" / "restricted" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def save_encrypted_raw_clip(
    incident_id: str,
    raw_media_bytes: Optional[bytes] = None,
    frame_tracks: Optional[List[Dict[str, Any]]] = None,
    source_file: Optional[Path] = None,
) -> Path:
    """
    Encrypt and save raw media clip for an incident under data/evidence/restricted/raw/<incident_id>.enc.
    Optionally bundles frame-by-frame tracked person bounding boxes/keypoints so TARGETED reveals
    can accurately blur non-flagged tracks without re-running model inference.
    """
    raw_dir = get_raw_clips_dir()
    target_path = raw_dir / f"{incident_id}.enc"

    media_bytes = raw_media_bytes or b""
    if source_file and Path(source_file).exists():
        sf = Path(source_file)
        if sf.suffix.lower() in [".mp4", ".avi", ".mkv", ".mov"]:
            ffmpeg_bin = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
            p = subprocess.run([
                ffmpeg_bin, "-y",
                "-i", str(sf),
                "-c:v", "copy",
                "-movflags", "frag_keyframe+empty_moov+default_base_moof",
                "-f", "mp4",
                "pipe:1"
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if p.returncode == 0 and len(p.stdout) > 0:
                media_bytes = p.stdout
            else:
                media_bytes = sf.read_bytes()
        else:
            media_bytes = sf.read_bytes()

    payload: Dict[str, Any] = {
        "media_base64": base64.b64encode(media_bytes).decode("ascii"),
        "frame_tracks": frame_tracks or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    encrypted_payload = encrypt_bytes(payload_bytes)

    target_path.write_bytes(encrypted_payload)
    logger.info(f"Encrypted raw clip for incident {incident_id} saved to {target_path} ({len(encrypted_payload)} bytes).")
    return target_path


def load_and_decrypt_raw_clip(incident_id: str) -> Tuple[bytes, List[Dict[str, Any]]]:
    """
    Loads and decrypts raw media for an incident entirely in memory.
    Never writes decrypted plaintext video to disk.
    Returns: (raw_media_bytes, frame_tracks)
    """
    raw_dir = get_raw_clips_dir()
    enc_path = raw_dir / f"{incident_id}.enc"
    if not enc_path.exists() or not enc_path.is_file():
        raise FileNotFoundError(f"Encrypted raw clip for incident '{incident_id}' not found.")

    encrypted_data = enc_path.read_bytes()
    decrypted_bytes = decrypt_bytes(encrypted_data)

    try:
        payload = json.loads(decrypted_bytes.decode("utf-8"))
        media_bytes = base64.b64decode(payload["media_base64"])
        frame_tracks = payload.get("frame_tracks", [])
        return media_bytes, frame_tracks
    except Exception:
        # Fallback if raw bytes were written directly
        return decrypted_bytes, []


def blur_person_face(
    frame: np.ndarray,
    person: Dict[str, Any],
) -> np.ndarray:
    """Blur a single person's face area using keypoints or fallback top 20% bounding box."""
    h, w = frame.shape[:2]
    kpts = person.get("keypoints", [])
    box = person.get("box", [0, 0, 0, 0])

    face_pts = []
    # 0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear
    for idx in [0, 1, 2, 3, 4]:
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
        # Fallback: top 20% of person's bounding box
        bx1, by1, bx2, by2 = map(int, box)
        fx1 = max(0, bx1)
        fy1 = max(0, by1)
        fx2 = min(w, bx2)
        fy2 = min(h, by1 + int((by2 - by1) * 0.20))

    if fx2 > fx1 + 4 and fy2 > fy1 + 4:
        roi = frame[fy1:fy2, fx1:fx2]
        ksize = max(15, (roi.shape[1] // 2) * 2 + 1)
        frame[fy1:fy2, fx1:fx2] = cv2.GaussianBlur(roi, (ksize, ksize), 30)

    return frame


def apply_watermark_to_frame(
    frame: np.ndarray,
    viewer_email: str,
    timestamp_str: str,
    label: str,
) -> np.ndarray:
    """Overlays tamper-evident forensic watermark and audit banner over a frame."""
    h, w = frame.shape[:2]

    # 1. Top HUD Banner
    banner_h = 28
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (10, 10, 15), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    text = f"{label} | VIEWER: {viewer_email} | {timestamp_str}"
    cv2.putText(frame, text, (12, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1, cv2.LINE_AA)

    # 2. Subtle translucent watermark across bottom-right
    watermark_sub = f"{viewer_email} · {label}"
    (tw, th), _ = cv2.getTextSize(watermark_sub, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    wx = max(10, w - tw - 16)
    wy = max(30, h - 16)
    cv2.putText(frame, watermark_sub, (wx, wy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    return frame


def watermark_and_filter_media(
    raw_media_bytes: bytes,
    frame_tracks: List[Dict[str, Any]],
    viewer_email: str,
    label: str,
    variant: str = "full",
    flagged_track_ids: Optional[List[int]] = None,
) -> Tuple[bytes, str]:
    """
    Decodes decrypted raw media in memory, applies targeted face blurring if requested,
    applies the viewer watermark, and encodes in memory.
    Returns: (watermarked_bytes, content_type)
    """
    flagged_set = set(flagged_track_ids or [])
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Detect if image (starts with JPEG or PNG magic bytes)
    is_jpeg = raw_media_bytes.startswith(b"\xff\xd8\xff")
    is_png = raw_media_bytes.startswith(b"\x89PNG")

    if is_jpeg or is_png:
        img_arr = np.frombuffer(raw_media_bytes, np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if frame is not None:
            if variant == "targeted":
                # Blur all persons not in flagged_set
                persons = frame_tracks[0] if (frame_tracks and isinstance(frame_tracks[0], list)) else frame_tracks
                for p in persons:
                    tid = p.get("track_id")
                    if tid not in flagged_set:
                        frame = blur_person_face(frame, p)

            frame = apply_watermark_to_frame(frame, viewer_email, now_str, label)
            _, out_jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return out_jpg.tobytes(), "image/jpeg"

    # Otherwise process as MP4 video in memory via ffmpeg
    ffmpeg_bin = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()

    # Decode video from pipe
    proc_dec = subprocess.Popen([
        ffmpeg_bin, "-y",
        "-i", "pipe:0",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "pipe:1"
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    # Decode all frames from memory
    try:
        dec_out, _ = proc_dec.communicate(input=raw_media_bytes, timeout=30)
    except Exception as e:
        logger.warning(f"Error decoding raw video: {e}")
        dec_out = b""

    # Attempt to inspect video dimensions using ffprobe/ffmpeg probe or fallback
    probe_w, probe_h, fps = 640, 360, 8.0
    try:
        probe_res = subprocess.run([
            ffmpeg_bin, "-i", "pipe:0"
        ], input=raw_media_bytes, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, timeout=10)
        lines = probe_res.stderr.splitlines()
        for line in lines:
            if "Video:" in line:
                import re
                m = re.search(r"(\d{3,4})x(\d{3,4})", line)
                if m:
                    probe_w, probe_h = int(m.group(1)), int(m.group(2))
                m_fps = re.search(r"(\d+(?:\.\d+)?) fps", line)
                if m_fps:
                    fps = float(m_fps.group(1))
                break
    except Exception:
        pass

    frame_size = probe_w * probe_h * 3
    if not dec_out or len(dec_out) < frame_size:
        # Fallback: if piping raw MP4 failed (e.g. unfragmented input), create a synthetic watermarked response
        canvas = np.zeros((probe_h, probe_w, 3), dtype=np.uint8)
        canvas = apply_watermark_to_frame(canvas, viewer_email, now_str, label)
        cv2.putText(canvas, f"NO VIDEO STREAM AVAILABLE ({label})", (50, probe_h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        _, err_jpg = cv2.imencode(".jpg", canvas)
        return err_jpg.tobytes(), "image/jpeg"

    num_frames = len(dec_out) // frame_size

    proc_enc = subprocess.Popen([
        ffmpeg_bin, "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{probe_w}x{probe_h}",
        "-pix_fmt", "bgr24",
        "-r", str(int(fps)),
        "-i", "pipe:0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4",
        "pipe:1"
    ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    processed_frames = []
    for f_idx in range(num_frames):
        start_idx = f_idx * frame_size
        raw_f = dec_out[start_idx:start_idx + frame_size]
        frame = np.frombuffer(raw_f, dtype=np.uint8).reshape((probe_h, probe_w, 3)).copy()

        if variant == "targeted":
            persons = frame_tracks[f_idx] if f_idx < len(frame_tracks) else []
            if isinstance(persons, list):
                for p in persons:
                    tid = p.get("track_id")
                    if tid not in flagged_set:
                        frame = blur_person_face(frame, p)

        frame = apply_watermark_to_frame(frame, viewer_email, now_str, label)
        processed_frames.append(frame.tobytes())

    try:
        enc_out, _ = proc_enc.communicate(input=b"".join(processed_frames), timeout=30)
    except Exception as exc:
        logger.error(f"Error encoding watermarked video: {exc}")
        enc_out = b""

    return enc_out, "video/mp4"
