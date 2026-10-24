"""
Analysis Service for RakshakAI.
Handles on-demand media uploads (video, audio), multi-modal parallel analysis,
annotated skeleton MP4 generation, live webcam/RTSP feeds, and privacy compliance.
"""
import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
import zoneinfo

from beanie import PydanticObjectId
from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import BadRequestError, NotFoundError, PayloadTooLargeError
from app.detectors.base import SimulationClock
from app.fusion.corroboration import FusionEngine
from app.models.analysis import AnalysisJob
from app.models.organization import Organization
from app.models.rules import RuleDocument
from app.models.signal import Signal
from app.models.zone import Camera, Zone
from app.realtime.ws import ws_hub

logger = logging.getLogger("rakshakai.services.analysis")

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac"}

_running_job_tasks: Dict[str, asyncio.Task] = {}
_active_job_clocks: Dict[str, SimulationClock] = {}
_active_live_sessions: Dict[Tuple[str, str], Dict[str, Any]] = {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_ffmpeg_binary() -> str:
    """Resolve ffmpeg executable from PATH or bundled imageio-ffmpeg."""
    import imageio_ffmpeg
    return shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def validate_media_upload(filename: Optional[str], content_type: Optional[str]) -> Tuple[str, str]:
    """
    Validates uploaded file extension and content type.
    Rejects unauthorized executable or script formats.
    Returns (media_type, extension) where media_type is 'video' or 'audio'.
    """
    if not filename:
        raise BadRequestError("Uploaded file must have a filename", code="INVALID_FILENAME")

    ext = Path(filename).suffix.lower()
    ct = (content_type or "").lower().strip()

    # Explicitly reject dangerous executable extensions
    if ext in {".exe", ".bat", ".sh", ".cmd", ".msi", ".dll", ".so", ".bin", ".py", ".js"}:
        raise BadRequestError(f"Unsupported and unsafe file extension: '{ext}'", code="UNSUPPORTED_MEDIA")

    if ext in ALLOWED_VIDEO_EXTENSIONS:
        if ct and not (
            ct.startswith("video/") or
            ct in ("application/octet-stream", "application/x-matroska")
        ):
            raise BadRequestError(f"Invalid content type '{ct}' for video extension '{ext}'", code="INVALID_CONTENT_TYPE")
        return "video", ext

    if ext in ALLOWED_AUDIO_EXTENSIONS:
        if ct and not (
            ct.startswith("audio/") or
            ct in ("application/octet-stream", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/flac")
        ):
            raise BadRequestError(f"Invalid content type '{ct}' for audio extension '{ext}'", code="INVALID_CONTENT_TYPE")
        return "audio", ext

    raise BadRequestError(
        f"Unsupported file format '{ext}'. Allowed video: {sorted(ALLOWED_VIDEO_EXTENSIONS)}, audio: {sorted(ALLOWED_AUDIO_EXTENSIONS)}",
        code="UNSUPPORTED_MEDIA"
    )


async def save_uploaded_media(
    file: UploadFile,
    org_id: str,
    job_id: str,
    ext: str,
) -> Path:
    """
    Saves an uploaded file to data/uploads/<org_id>/<job_id>/<uuid>.<ext>.
    Never uses the client's original filename on disk.
    Enforces configurable MAX_UPLOAD_SIZE_MB during streaming.
    """
    target_dir = settings.UPLOADS_DIR / org_id / job_id
    target_dir.mkdir(parents=True, exist_ok=True)

    random_filename = f"{uuid4().hex}{ext}"
    target_path = target_dir / random_filename

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_bytes = 0
    chunk_size = 1024 * 1024  # 1 MB

    try:
        with open(target_path, "wb") as out_file:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise PayloadTooLargeError(
                        f"Uploaded file exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB",
                        code="PAYLOAD_TOO_LARGE"
                    )
                out_file.write(chunk)
    except Exception:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        raise

    return target_path


def extract_audio_from_video(video_path: Path, output_wav_path: Path) -> bool:
    """
    Extracts 16 kHz mono PCM WAV audio track from video using ffmpeg.
    Returns True if an audio stream was extracted successfully, False otherwise.
    """
    ffmpeg_bin = get_ffmpeg_binary()
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_wav_path),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
        return proc.returncode == 0 and output_wav_path.exists() and output_wav_path.stat().st_size > 44
    except Exception as exc:
        logger.warning(f"Audio extraction from video failed or no audio track present: {exc}")
        return False


async def run_media_analysis_job(
    job_id: str,
    org_id: str,
    sim_start_str: Optional[str] = None,
) -> None:
    """
    Background job execution for on-demand media analysis:
    - Pre-warms AI models (YOLO pose & YAMNet)
    - Aligns simulation clock to user specified sim_start or org timezone
    - If video has sound, runs video pose + audio distress in parallel
    - Emits signals with source="upload" into FusionEngine
    - Generates annotated skeleton-only MP4 at data/evidence/public/<job_id>_annotated.mp4
    - Auto-deletes raw uploaded file if delete_raw_uploads_after_analysis is true (default)
    - Broadcasts WebSocket events analysis.progress and analysis.done to org room
    """
    job = await AnalysisJob.find_one(AnalysisJob.job_id == job_id, AnalysisJob.org_id == org_id)
    if not job:
        logger.error(f"Analysis job '{job_id}' not found for org '{org_id}'")
        return

    # Pre-warm AI models in real mode
    if settings.DETECTOR_MODE == "real":
        try:
            from app.detectors.audio_distress import get_yamnet_model
            from app.detectors.synthetic_media import ensure_media_fixtures
            from app.detectors.video_pose import get_yolo_model
            ensure_media_fixtures(settings.DATA_DIR)
            get_yolo_model()
            get_yamnet_model()
        except Exception as e:
            logger.warning(f"Model pre-warm warning: {e}")

    job.status = "running"
    job.started_at = utc_now()
    job.progress = 5
    await job.save()

    await ws_hub.broadcast_to_org(
        org_id=org_id,
        event_type="analysis.progress",
        data={"job_id": job_id, "status": "running", "progress": 5},
    )

    try:
        # Load Organization
        try:
            org = await Organization.get(PydanticObjectId(org_id))
        except Exception:
            org = await Organization.find_one({"_id": org_id})
        if not org:
            org = await Organization.find_one({"slug": org_id})

        # Calculate simulation start time
        if sim_start_str:
            parts = sim_start_str.strip().split(":")
            sh = int(parts[0])
            sm = int(parts[1]) if len(parts) > 1 else 0
            ss = int(parts[2]) if len(parts) > 2 else 0
            start_sim_time = utc_now().replace(hour=sh, minute=sm, second=ss, microsecond=0)
        else:
            org_tz_str = org.settings.get("timezone", "Asia/Kolkata") if org and org.settings else "Asia/Kolkata"
            try:
                org_tz = zoneinfo.ZoneInfo(org_tz_str)
                now_in_tz = datetime.now(org_tz)
                start_sim_time = utc_now().replace(
                    hour=now_in_tz.hour,
                    minute=now_in_tz.minute,
                    second=now_in_tz.second,
                    microsecond=0,
                )
            except Exception:
                start_sim_time = utc_now()

        # Offline video runs accelerated through sim_clock (speed=50.0x)
        sim_clock = SimulationClock(start_sim_time=start_sim_time, speed=50.0)
        _active_job_clocks[job_id] = sim_clock

        # Fetch active rules for org
        active_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
        rules_dict = active_rules.model_dump() if active_rules else {}
        fusion_engine = FusionEngine(org_id, rules_dict)

        emitted_signal_ids: List[str] = []
        emitted_incident_ids: List[str] = []

        async def emit_signal(signal: Signal) -> None:
            signal.org_id = org_id
            signal.source = "upload"
            inc = await fusion_engine.ingest_signal(signal)
            emitted_signal_ids.append(str(signal.id))
            if inc and str(inc.id) not in emitted_incident_ids:
                emitted_incident_ids.append(str(inc.id))

        async def on_progress(pct: int) -> None:
            job.progress = pct
            await job.save()
            await ws_hub.broadcast_to_org(
                org_id=org_id,
                event_type="analysis.progress",
                data={"job_id": job_id, "status": "running", "progress": pct},
            )

        # Execute analysis by type
        if job.type == "video":
            from app.detectors.audio_distress import AudioDistressDetector
            from app.detectors.video_pose import VideoPoseDetector

            video_path = Path(job.stored_path) if job.stored_path else None
            if not video_path or not video_path.exists():
                raise NotFoundError(f"Uploaded video file not found at {job.stored_path}")

            annotated_mp4_path = settings.DATA_DIR / "evidence" / "public" / f"{job_id}_annotated.mp4"
            annotated_mp4_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if video has audio stream
            extracted_wav_path = video_path.parent / f"{job_id}_extracted.wav"
            has_audio = extract_audio_from_video(video_path, extracted_wav_path)

            v_detector = VideoPoseDetector(camera_id=job.camera_id, zone_id=job.zone_id)
            tasks = [
                v_detector.start(
                    source=str(video_path),
                    zone_id=job.zone_id or "terrace",
                    sim_clock=sim_clock,
                    emit_callback=emit_signal,
                    loop=False,
                    annotated_output_path=annotated_mp4_path,
                    progress_callback=on_progress,
                )
            ]

            if has_audio:
                logger.info(f"Dual-modality detected for job {job_id}: extracted audio track for distress analysis.")
                a_detector = AudioDistressDetector(zone_id=job.zone_id or "terrace")
                tasks.append(
                    a_detector.start(
                        source=str(extracted_wav_path),
                        zone_id=job.zone_id or "terrace",
                        sim_clock=sim_clock,
                        emit_callback=emit_signal,
                    )
                )

            await asyncio.gather(*tasks)

            # Clean up temporary extracted audio file
            if extracted_wav_path.exists():
                extracted_wav_path.unlink(missing_ok=True)

            if annotated_mp4_path.exists():
                job.annotated_video_path = f"evidence/public/{annotated_mp4_path.name}"

        elif job.type == "audio":
            from app.detectors.audio_distress import AudioDistressDetector

            audio_path = Path(job.stored_path) if job.stored_path else None
            if not audio_path or not audio_path.exists():
                raise NotFoundError(f"Uploaded audio file not found at {job.stored_path}")

            a_detector = AudioDistressDetector(zone_id=job.zone_id or "terrace")
            await a_detector.start(
                source=str(audio_path),
                zone_id=job.zone_id or "terrace",
                sim_clock=sim_clock,
                emit_callback=emit_signal,
                progress_callback=on_progress,
            )

        # Privacy Enforcement: Auto-delete raw uploaded file
        delete_raw = True
        if org and org.settings:
            delete_raw = bool(org.settings.get("delete_raw_uploads_after_analysis", True))

        if delete_raw and job.stored_path:
            raw_path = Path(job.stored_path)
            if raw_path.exists():
                raw_path.unlink(missing_ok=True)
            parent_dir = raw_path.parent
            if parent_dir.exists():
                for f in parent_dir.iterdir():
                    if f.is_file():
                        f.unlink(missing_ok=True)
                try:
                    parent_dir.rmdir()
                except Exception:
                    pass
            job.stored_path = None

        job.status = "done"
        job.progress = 100
        job.completed_at = utc_now()
        job.signals_count = len(emitted_signal_ids)
        job.incident_ids = emitted_incident_ids
        await job.save()

        await ws_hub.broadcast_to_org(
            org_id=org_id,
            event_type="analysis.done",
            data={
                "job_id": job_id,
                "status": "done",
                "progress": 100,
                "signals_count": job.signals_count,
                "incident_ids": job.incident_ids,
            },
        )
        logger.info(f"Analysis job {job_id} successfully completed. Signals: {len(emitted_signal_ids)}, Incidents: {len(emitted_incident_ids)}")

    except asyncio.CancelledError:
        logger.info(f"Analysis job {job_id} was cancelled.")
        job.status = "cancelled"
        job.completed_at = utc_now()
        await job.save()
        await ws_hub.broadcast_to_org(
            org_id=org_id,
            event_type="analysis.done",
            data={"job_id": job_id, "status": "cancelled", "progress": job.progress},
        )
    except Exception as exc:
        logger.error(f"Analysis job {job_id} failed with error: {exc}", exc_info=True)
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = utc_now()
        await job.save()
        await ws_hub.broadcast_to_org(
            org_id=org_id,
            event_type="analysis.done",
            data={"job_id": job_id, "status": "failed", "progress": job.progress, "error": str(exc)},
        )
    finally:
        _running_job_tasks.pop(job_id, None)
        _active_job_clocks.pop(job_id, None)


def cancel_analysis_job(job_id: str) -> bool:
    """Cancels an in-flight analysis job task if active."""
    clock = _active_job_clocks.pop(job_id, None)
    if clock:
        clock.stop()

    task = _running_job_tasks.pop(job_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def start_live_analysis(
    org_id: str,
    camera_id: str,
    source: str,
    mic_enabled: bool = False,
) -> Dict[str, Any]:
    """
    Starts continuous live video analysis for a camera using webcam or RTSP stream.
    Updates the skeleton MJPEG frame buffer in real-time.
    """
    key = (org_id, camera_id)
    if key in _active_live_sessions:
        await stop_live_analysis(org_id, camera_id)

    # Resolve camera & zone
    cam = await Camera.find_one({"camera_id": camera_id, "org_id": org_id})
    zone_id = cam.zone_id if cam else "terrace"

    active_rules = await RuleDocument.find_one({"org_id": org_id, "is_active": True})
    rules_dict = active_rules.model_dump() if active_rules else {}
    fusion_engine = FusionEngine(org_id, rules_dict)

    sim_clock = SimulationClock(start_sim_time=utc_now(), speed=1.0)

    async def emit_live_signal(signal: Signal) -> None:
        signal.org_id = org_id
        signal.source = "live"
        await fusion_engine.ingest_signal(signal)

    from app.detectors.video_pose import VideoPoseDetector
    v_detector = VideoPoseDetector(camera_id=camera_id, zone_id=zone_id)

    task = asyncio.create_task(
        v_detector.start(
            source=source,
            zone_id=zone_id,
            sim_clock=sim_clock,
            emit_callback=emit_live_signal,
            loop=True,
        )
    )

    _active_live_sessions[key] = {
        "detector": v_detector,
        "task": task,
        "sim_clock": sim_clock,
        "source": source,
        "camera_id": camera_id,
        "started_at": utc_now(),
    }

    return {"status": "started", "camera_id": camera_id, "source": source}


async def stop_live_analysis(org_id: str, camera_id: str) -> bool:
    """Stops an active live camera analysis session."""
    key = (org_id, camera_id)
    session = _active_live_sessions.pop(key, None)
    if not session:
        return False

    session["sim_clock"].stop()
    await session["detector"].stop()
    if session["task"] and not session["task"].done():
        session["task"].cancel()
    return True
