"""
Real Audio Distress Detector for RakshakAI using YAMNet.
Features:
- YAMNet inference on CPU via tensorflow_hub (0.96s windows, 0.48s hop)
- Dynamic class name loading from model's class_map CSV at runtime (no hardcoded indices)
- Stage 1: Distress score threshold check
- Stage 2: Context filter suppression (confusable_max >= distress_max * context_ratio)
- Stage 3: Temporal persistence suppression (>= 2 of last 3 windows required)
- Strict privacy: saves 3-second audio clip to data/evidence/restricted/; never stores transcripts
- Optional audio head support (AUDIO_CLASSIFIER=yamnet_head)
- Optional keyword detection hook (HELP_KEYWORDS=true)
"""
import asyncio
import csv
import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import librosa
import numpy as np
import soundfile as sf
import tensorflow as tf
import tensorflow_hub as hub

from app.core.config import settings
from app.detectors.base import BaseDetector, SimulationClock
from app.models.signal import Signal

logger = logging.getLogger("rakshakai.detectors.audio_distress")

# Target class keywords
DISTRESS_KEYWORDS = [
    "screaming",
    "shout",
    "yell",
    "children shouting",
    "crying, sobbing",
    "wail, moan",
    "glass",
    "shatter",
]

CONFUSABLE_KEYWORDS = [
    "laughter",
    "giggle",
    "chuckle, chortle",
    "cheering",
    "applause",
    "crowd",
    "music",
    "singing",
    "children playing",
]

# Model and class map cache
_cached_yamnet_model = None
_cached_yamnet_classes: Optional[List[str]] = None
_cached_distress_indices: Optional[List[int]] = None
_cached_confusable_indices: Optional[List[int]] = None
_cached_audio_head = None


def get_yamnet_model():
    global _cached_yamnet_model
    if _cached_yamnet_model is None:
        logger.info("Loading YAMNet model from TensorFlow Hub...")
        _cached_yamnet_model = hub.load("https://tfhub.dev/google/yamnet/1")
    return _cached_yamnet_model


def get_yamnet_class_mapping(model) -> Tuple[List[str], List[int], List[int]]:
    global _cached_yamnet_classes, _cached_distress_indices, _cached_confusable_indices
    if _cached_yamnet_classes is None:
        csv_path = model.class_map_path().numpy().decode("utf-8")
        classes = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                if len(row) >= 3:
                    classes.append(row[2])

        _cached_yamnet_classes = classes

        # Dynamically map indices
        distress_idx = []
        for i, c in enumerate(classes):
            c_low = c.lower()
            if any(k.lower() in c_low for k in DISTRESS_KEYWORDS):
                distress_idx.append(i)

        confusable_idx = []
        for i, c in enumerate(classes):
            c_low = c.lower()
            if any(k.lower() in c_low for k in CONFUSABLE_KEYWORDS):
                # Avoid overlap with distress
                if i not in distress_idx:
                    confusable_idx.append(i)

        _cached_distress_indices = distress_idx
        _cached_confusable_indices = confusable_idx
        logger.info(f"Loaded {len(classes)} YAMNet classes: {len(distress_idx)} distress, {len(confusable_idx)} confusable.")

    return _cached_yamnet_classes, _cached_distress_indices, _cached_confusable_indices


def load_audio_head_if_enabled():
    global _cached_audio_head
    if _cached_audio_head is None:
        model_path = settings.MODELS_DIR / "audio_head.joblib"
        if not model_path.exists():
            model_path = settings.DATA_DIR.parent / "models" / "audio_head.joblib"
        if not model_path.exists():
            model_path = Path("ml/models/audio_head.joblib")
        if settings.AUDIO_CLASSIFIER == "yamnet_head" and model_path.exists():
            import joblib
            try:
                _cached_audio_head = joblib.load(str(model_path))
                logger.info(f"Loaded custom audio head from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load audio head: {e}")
    return _cached_audio_head


def check_keywords_if_enabled(audio_chunk: np.ndarray, sr: int = 16000) -> Tuple[bool, Optional[str]]:
    """
    Spot 'help' or 'bachao' using faster-whisper if enabled and installed.
    Never stores transcripts; returns only (matched: bool, keyword: str).
    """
    if not settings.HELP_KEYWORDS:
        return False, None

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_chunk, language=None)
        for s in segments:
            text = s.text.lower()
            if "help" in text:
                return True, "help"
            if "bachao" in text:
                return True, "bachao"
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Keyword spotter check skipped: {e}")

    return False, None


class AudioDistressDetector(BaseDetector):
    """
    Real Audio Distress Detector with 3-stage contextual pipeline.
    """
    def __init__(self, zone_id: Optional[str] = None) -> None:
        super().__init__()
        self.zone_id = zone_id
        self._task: Optional[asyncio.Task] = None
        self.running = False

    async def start(
        self,
        source: str,
        zone_id: str,
        sim_clock: SimulationClock,
        emit_callback: Callable[[Signal], Awaitable[None]],
        progress_callback: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> None:
        self.running = True
        self.zone_id = zone_id

        # Resolve media source path
        src_path = Path(source)
        if not src_path.is_absolute():
            source_str = str(source).replace("\\", "/")
            if (settings.DATA_DIR / source).exists():
                src_path = settings.DATA_DIR / source
            elif (settings.PROJECT_ROOT / source).exists():
                src_path = settings.PROJECT_ROOT / source
            elif source_str.startswith("data/") and (settings.PROJECT_ROOT / source).exists():
                src_path = settings.PROJECT_ROOT / source
            elif source_str.startswith("data/") and (settings.DATA_DIR / source_str[len("data/"):]).exists():
                src_path = settings.DATA_DIR / source_str[len("data/"):]
            elif Path(source).exists():
                src_path = Path(source).resolve()
            else:
                src_path = settings.DATA_DIR / source

        if not src_path.exists():
            from app.detectors.synthetic_media import ensure_media_fixtures
            ensure_media_fixtures()
            if not src_path.exists():
                # Fallback to standard fixtures by zone or kind
                if "hard_negative" in str(source) or "common" in zone_id:
                    src_path = settings.DATA_DIR / "audio" / "hard_negative" / "cheering_01.wav"
                elif "normal" in str(source):
                    src_path = settings.DATA_DIR / "audio" / "normal" / "normal_01.wav"
                else:
                    src_path = settings.DATA_DIR / "audio" / "distress" / "distress_01.wav"

        logger.info(f"Starting AudioDistressDetector on zone '{zone_id}' using audio source '{src_path}'")

        # Load audio at 16 kHz mono
        try:
            waveform, sr = librosa.load(str(src_path), sr=16000, mono=True)
        except Exception as e:
            logger.error(f"Error loading audio file {src_path}: {e}")
            return

        # Ensure minimum length (at least 0.96s)
        if len(waveform) < 15360:
            pad = np.zeros(15360 - len(waveform), dtype=np.float32)
            waveform = np.concatenate([waveform, pad])

        model = get_yamnet_model()
        classes, distress_indices, confusable_indices = get_yamnet_class_mapping(model)
        head_model = load_audio_head_if_enabled()

        # Run YAMNet inference
        wav_tensor = tf.convert_to_tensor(waveform, dtype=tf.float32)
        scores_tf, embeddings_tf, _ = model(wav_tensor)
        scores = scores_tf.numpy()  # shape (num_windows, 521)
        embeddings = embeddings_tf.numpy()  # shape (num_windows, 1024)

        num_windows = scores.shape[0]
        window_hop_s = 0.48
        window_len_s = 0.96

        # Fetch zone threshold & context ratio from rules
        zone_threshold = 0.35
        context_ratio = 0.80
        try:
            from app.models.rules import RuleDocument
            rules_doc = await RuleDocument.find_one({"is_active": True})
            if rules_doc:
                if rules_doc.zones and zone_id in rules_doc.zones:
                    zone_threshold = float(
                        rules_doc.zones[zone_id].get("thresholds", {}).get("distress_audio", 0.35)
                    )
                context_ratio = float(rules_doc.rules.get("audio", {}).get("context_ratio", 0.80))
        except Exception:
            pass

        # Pipeline state: history of stage 1+2 passes for persistence
        stage1_2_history: List[bool] = []
        last_unsuppressed_sim_time: Optional[datetime] = None
        last_suppressed_sim_time: Optional[datetime] = None
        last_progress_pct = 0

        for w in range(num_windows):
            if not self.running or sim_clock.is_stopped:
                break

            if progress_callback and num_windows > 0:
                current_pct = min(95, int((w / num_windows) * 90) + 5)
                if current_pct - last_progress_pct >= 5:
                    last_progress_pct = current_pct
                    await progress_callback(current_pct)

            offset_s = w * window_hop_s
            target_sim_time = sim_clock.start_sim_time + timedelta(seconds=offset_s)
            await sim_clock.sleep_until(target_sim_time)

            if not self.running or sim_clock.is_stopped:
                break

            current_sim_time = sim_clock.now()
            win_scores = scores[w]

            # -------------------------------------------------------------
            # Stage 1: Distress Score
            # -------------------------------------------------------------
            if head_model is not None:
                emb = embeddings[w].reshape(1, -1)
                distress_score = float(head_model.predict_proba(emb)[0][1])
                distress_label = "Screaming (head)"
            else:
                distress_scores = [win_scores[idx] for idx in distress_indices]
                max_d_idx = int(np.argmax(distress_scores))
                distress_score = float(distress_scores[max_d_idx])
                distress_label = classes[distress_indices[max_d_idx]]

            stage1_pass = bool(distress_score >= zone_threshold)

            # -------------------------------------------------------------
            # Stage 2: Context Filter
            # -------------------------------------------------------------
            confusable_scores = [win_scores[idx] for idx in confusable_indices]
            max_c_idx = int(np.argmax(confusable_scores))
            confusable_score = float(confusable_scores[max_c_idx])
            confusable_label = classes[confusable_indices[max_c_idx]]

            stage2_suppressed = False
            suppress_reason = None

            if confusable_score >= (distress_score * context_ratio):
                stage2_suppressed = True
                suppress_reason = (
                    f"{confusable_label} {confusable_score:.2f} >= "
                    f"{context_ratio:.1f} x {distress_label} {distress_score:.2f}"
                )

            stage1_2_pass = stage1_pass and not stage2_suppressed
            stage1_2_history.append(stage1_2_pass)

            # -------------------------------------------------------------
            # Stage 3: Temporal Persistence (>= 2 of last 3 windows)
            # -------------------------------------------------------------
            recent_windows = stage1_2_history[-3:]
            stage3_pass = sum(1 for p in recent_windows if p) >= 2

            suppressed = False
            if not stage1_pass:
                # If stage 1 failed, don't emit unless score is near threshold or part of scenario
                continue
            elif stage2_suppressed:
                suppressed = True
            elif not stage3_pass:
                suppressed = True
                suppress_reason = "not persistent"

            # Optional Keyword Spotter Check
            kw_hit, kw_word = False, None
            if stage1_pass and settings.HELP_KEYWORDS:
                w_start = int(offset_s * 16000)
                w_end = min(len(waveform), int((offset_s + 3.0) * 16000))
                audio_slice = waveform[w_start:w_end]
                kw_hit, kw_word = check_keywords_if_enabled(audio_slice)
                if kw_hit:
                    distress_score = min(1.0, distress_score + 0.15)

            # Throttle emissions so we don't spam duplicate signals per second
            if suppressed:
                if last_suppressed_sim_time is not None:
                    if (current_sim_time - last_suppressed_sim_time).total_seconds() < 2.0:
                        continue
                last_suppressed_sim_time = current_sim_time
            else:
                if last_unsuppressed_sim_time is not None:
                    if (current_sim_time - last_unsuppressed_sim_time).total_seconds() < 2.0:
                        continue
                last_unsuppressed_sim_time = current_sim_time

            # Top 5 classes for explainability
            top5_indices = np.argsort(win_scores)[-5:][::-1]
            top5_details = [
                {"class": classes[idx], "score": round(float(win_scores[idx]), 3)}
                for idx in top5_indices
            ]

            # Save 3-second restricted evidence clip (never transcripts)
            w_start = max(0, int((offset_s - 0.5) * 16000))
            w_end = min(len(waveform), int((offset_s + 2.5) * 16000))
            clip = waveform[w_start:w_end]

            ev_id = f"distress_{zone_id}_{w}_{int(current_sim_time.timestamp())}"
            evidence_rel_path = self._save_audio_evidence(clip, ev_id)

            signal = Signal(
                org_id="",
                ts=current_sim_time,
                modality="audio",
                kind="distress_audio",
                zone_id=zone_id,
                camera_id=None,
                score=round(distress_score, 3),
                threshold=zone_threshold,
                details={
                    "label": distress_label,
                    "top5": top5_details,
                    "stages": {
                        "stage1_pass": stage1_pass,
                        "stage2_pass": not stage2_suppressed,
                        "stage3_pass": stage3_pass,
                        "distress_score": round(distress_score, 3),
                        "confusable_score": round(confusable_score, 3),
                        "context_ratio": context_ratio,
                    },
                    "help_keyword": kw_hit,
                    "keyword": kw_word,
                },
                suppressed=suppressed,
                suppress_reason=suppress_reason,
                evidence_path=evidence_rel_path,
                source="audio_distress",
            )

            logger.info(
                f"AudioDistressDetector emitting distress_audio (suppressed={suppressed}) "
                f"score={signal.score} reason={suppress_reason} at {current_sim_time.strftime('%H:%M:%S')}"
            )
            await emit_callback(signal)

        if progress_callback:
            await progress_callback(95)

    def _save_audio_evidence(self, audio_chunk: np.ndarray, ev_id: str) -> str:
        """Saves a 3-second audio snippet to data/evidence/restricted/."""
        res_dir = settings.DATA_DIR / "evidence" / "restricted"
        res_dir.mkdir(parents=True, exist_ok=True)
        file_path = res_dir / f"{ev_id}.wav"
        sf.write(str(file_path), audio_chunk, 16000)
        return f"evidence/restricted/{file_path.name}"

    async def stop(self) -> None:
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("AudioDistressDetector stopped.")
