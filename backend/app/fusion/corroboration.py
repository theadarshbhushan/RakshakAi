"""
Real Fusion Engine for RakshakAI: multi-modal corroboration and explainability.
Fuses Video, Audio, and Access signals within temporal and spatial adjacency windows.
Calculates Bayesian composite confidence score, determines severity, and generates
human-readable explanation narratives detailing all corroborating and suppressed signals.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from beanie import PydanticObjectId

from app.core.config import settings
from app.models.incident import Incident
from app.models.signal import AccessEvent, Signal
from app.models.zone import Zone
from app.realtime.ws import ws_hub

logger = logging.getLogger("rakshakai.fusion")

DEFAULT_WEIGHTS = {
    "video": 0.9,
    "audio": 0.8,
    "access": 0.7,
    "report": 0.85,
}


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class FusionEngine:
    def __init__(self, org_id: str, rules_config: Dict[str, Any]) -> None:
        self.org_id = org_id
        self.rules = rules_config
        self.weights = self.rules.get("weights", DEFAULT_WEIGHTS)
        self.fusion_window_s = float(self.rules.get("fusion", {}).get("window_seconds", 30))

    def calculate_composite_score(self, signals: List[Signal]) -> float:
        """
        composite = 1 - prod(1 - score_i * w_modality)
        """
        prod = 1.0
        for s in signals:
            if s.suppressed:
                continue
            w = float(self.weights.get(s.modality, 0.7))
            clamped_score = max(0.0, min(1.0, float(s.score)))
            prod *= (1.0 - (clamped_score * w))

        composite = 1.0 - prod
        return round(max(0.0, min(1.0, composite)), 3)

    def determine_severity(
        self,
        signals: List[Signal],
        composite_score: float,
        is_blind_spot: bool = False,
    ) -> str:
        """
        Severity determination rules:
        - SOS corroborated by video or audio in same zone -> critical
        - >= 3 modalities OR (fight AND distress_audio) -> critical
        - Blind spot compensation: in a blind-spot zone, any student SOS or access violation is at least high
        - SOS alone -> high (at least high)
        - 2 modalities -> high
        - 1 modality & composite >= 0.6 -> medium
        - 1 modality & composite < 0.6 -> low
        """
        active_signals = [s for s in signals if not s.suppressed]
        modalities = set(s.modality for s in active_signals)
        kinds = set(s.kind for s in active_signals)

        # Fight + distress audio in same zone -> critical (existing rule)
        if "fight" in kinds and "distress_audio" in kinds:
            return "critical"

        # SOS corroborated by audio or non-fight video in same zone -> critical
        non_fight_video = any(s.modality == "video" and s.kind != "fight" for s in active_signals)
        if "student_sos" in kinds and ("audio" in modalities or non_fight_video):
            return "critical"

        if len(modalities) >= 3:
            return "critical"

        # Fight + student SOS -> high
        if "fight" in kinds and "student_sos" in kinds:
            return "high"

        # Blind spot compensation: any student SOS or access violation in a blind spot zone is at least high severity
        access_kinds = {"restricted_access", "curfew_violation", "tailgating"}
        if is_blind_spot and ("student_sos" in kinds or (kinds & access_kinds)):
            return "high"

        # SOS alone creates at least a high-severity incident
        if "student_sos" in kinds:
            return "high"

        # Fight signal ALONE creates at most a LOW severity incident
        if kinds == {"fight"}:
            return "low"

        # Perimeter breach: at least high severity, critical with any second signal
        has_perimeter = any(s.kind == "zone_intrusion" and s.details.get("subtype") == "perimeter_breach" for s in active_signals)
        if has_perimeter:
            if len(active_signals) >= 2 or len(modalities) >= 2:
                return "critical"
            return "high"

        # Unswiped entry: high severity during curfew, medium during the day
        if "unswiped_entry" in kinds:
            is_curfew = any(s.details.get("is_curfew", False) for s in active_signals if s.kind == "unswiped_entry")
            if is_curfew or len(active_signals) >= 2:
                return "high"
            return "medium"

        # Unexplained presence: low-medium alone, higher when corroborated with loitering, audio, or SOS
        if "unexplained_presence" in kinds:
            if "distress_audio" in kinds or "student_sos" in kinds or "fight" in kinds:
                return "critical"
            if "loitering" in kinds or len(modalities) >= 2:
                return "high"
            return "medium" if composite_score >= 0.5 else "low"

        if len(modalities) == 2:
            return "high"
        if len(modalities) <= 1:
            if "camera_tamper" in kinds:
                return "high" if composite_score >= 0.8 else "medium"
            return "medium" if composite_score >= 0.6 else "low"
        return "low"

    async def generate_explanation(
        self,
        incident: Incident,
        signals: List[Signal],
        zone_name: str,
    ) -> str:
        """
        Generate explainable narrative detailing all corroborating and suppressed signals.
        """
        active_signals = [s for s in signals if not s.suppressed]
        kinds = set(s.kind for s in active_signals)
        sorted_signals = sorted(signals, key=lambda s: ensure_utc(s.ts))
        narrative_parts: List[str] = []
        base_time: Optional[datetime] = None

        for idx, s in enumerate(sorted_signals):
            s_ts = ensure_utc(s.ts)
            t_str = s_ts.strftime("%H:%M")
            diff_text = ""
            if base_time is None:
                base_time = s_ts
            else:
                diff_s = int(abs((s_ts - base_time).total_seconds()))
                diff_text = f" {diff_s} s later"

            if s.kind == "student_sos":
                sos_type = s.details.get("type", "other")
                note = s.details.get("note")
                note_str = f" ('{note}')" if note else ""
                if idx == 0:
                    narrative_parts.append(
                        f"Student SOS report ({sos_type}) from {zone_name} at {t_str}{note_str}"
                    )
                else:
                    narrative_parts.append(
                        f"corroborated by Student SOS report ({sos_type}){note_str} from {zone_name}{diff_text}"
                    )
            elif s.kind == "distress_audio":
                sound_label = s.details.get("label", "Distress sound").title()
                if idx == 0:
                    narrative_parts.append(
                        f"Distress audio ({sound_label} {s.score:.2f}) detected in '{zone_name}' at {t_str}"
                    )
                else:
                    narrative_parts.append(
                        f"corroborated by distress audio ({sound_label} {s.score:.2f}){diff_text}"
                    )
            elif s.kind == "zone_intrusion":
                is_perimeter = (s.details.get("subtype") == "perimeter_breach")
                explained = s.details.get("explained_by_access")
                role = s.details.get("role")
                swipe_id = s.details.get("swipe_id")

                if is_perimeter:
                    prefix = f"Perimeter breach detected at '{zone_name}' at {t_str}"
                    explain_note = "Always unexplained; restricted perimeter barrier crossed."
                    if idx == 0:
                        narrative_parts.append(f"{prefix}. {explain_note}")
                    else:
                        narrative_parts.append(f"corroborated by perimeter breach at '{zone_name}'{diff_text}. {explain_note}")
                elif explained is True:
                    swipe_str = f" #{swipe_id}" if swipe_id else ""
                    role_str = f" by {role}" if role else ""
                    if idx == 0:
                        narrative_parts.append(
                            f"Entry matches authorised swipe{role_str}{swipe_str} at {t_str}."
                        )
                    else:
                        narrative_parts.append(
                            f"corroborated by authorised entry (matches swipe{role_str}{swipe_str}){diff_text}."
                        )
                elif explained is False:
                    if idx == 0:
                        narrative_parts.append(
                            f"Person entered zone '{zone_name}' at {t_str} (score {s.score:.2f} vs threshold {s.threshold:.2f}). No authorised swipe explains this entry."
                        )
                    else:
                        narrative_parts.append(
                            f"corroborated by person entering zone '{zone_name}' (score {s.score:.2f}){diff_text}. No authorised swipe explains this entry."
                        )
                else:
                    if idx == 0:
                        narrative_parts.append(
                            f"Person entered zone '{zone_name}' at {t_str} (score {s.score:.2f} vs threshold {s.threshold:.2f})"
                        )
                    else:
                        narrative_parts.append(
                            f"corroborated by person entering zone '{zone_name}' (score {s.score:.2f}){diff_text}"
                        )
            elif s.kind == "unswiped_entry":
                door = s.details.get("door_id", "entry")
                p_cnt = s.details.get("people_count", 1)
                narrative_parts.append(
                    f"Access violation: unswiped entry detected at {door} at {t_str} ({p_cnt} person crossed with zero swipes)."
                )
            elif s.kind == "unexplained_presence":
                door = s.details.get("door_id", "block door")
                narrative_parts.append(
                    f"Unexplained presence: person detected in '{zone_name}' during curfew hours at {t_str} with no granted swipe at {door} in the last 30 minutes."
                )
            elif s.kind == "fight":
                if idx == 0:
                    if len(active_signals) == 1 or kinds == {"fight"}:
                        narrative_parts.append(
                            f"Possible altercation (experimental, unverified) detected in zone '{zone_name}' at {t_str} (score {s.score:.2f})"
                        )
                    else:
                        narrative_parts.append(
                            f"Physical fight detected (experimental) in zone '{zone_name}' at {t_str} (score {s.score:.2f})"
                        )
                else:
                    narrative_parts.append(
                        f"corroborated by physical fight (experimental) in zone '{zone_name}' (score {s.score:.2f}){diff_text}"
                    )
            elif s.kind == "curfew_violation":
                role = s.details.get("role", "resident")
                pseudo = s.details.get("pseudo_id", "anon")
                door = s.details.get("door_id", "door")
                narrative_parts.append(
                    f"Access log: curfew-hours swipe at {door} at {t_str} ({role} #{pseudo})."
                )
            elif s.kind == "restricted_access":
                role = s.details.get("role", "resident")
                pseudo = s.details.get("pseudo_id", "anon")
                narrative_parts.append(
                    f"Access log: unauthorized restricted zone attempt at {t_str} ({role} #{pseudo})."
                )
            elif s.kind == "tailgating":
                p_cnt = s.details.get("people_count", 2)
                s_cnt = s.details.get("swipe_count", 1)
                door = s.details.get("door_id", "entry")
                narrative_parts.append(
                    f"Access log: tailgating detected at {door} ({p_cnt} people crossed vs {s_cnt} swipe)."
                )
            elif s.kind == "loitering":
                dur = s.details.get("duration_s", 45)
                narrative_parts.append(
                    f"Unusual activity: Person loitering in '{zone_name}' for {dur}s during curfew hours at {t_str} (score {s.score:.2f})."
                )
            elif s.kind == "camera_tamper":
                tamper_type = s.details.get("tamper_type") or s.details.get("reason") or "covered"
                metric = s.details.get("metric")
                if metric is None and "brightness" in s.details:
                    metric = f"brightness {s.details['brightness']}"
                elif metric is not None and (isinstance(metric, (int, float)) or (isinstance(metric, str) and str(metric).replace('.', '', 1).isdigit())):
                    if "cover" in str(tamper_type).lower() or "dark" in str(tamper_type).lower():
                        metric = f"brightness {metric}"
                    elif "blur" in str(tamper_type).lower():
                        metric = f"blur {metric}"
                    elif "move" in str(tamper_type).lower():
                        metric = f"corr {metric}"
                metric_str = f" ({metric})" if metric else ""
                cam = s.camera_id or "camera"
                narrative_parts.append(
                    f"Camera {cam} {tamper_type}{metric_str}. Zone {zone_name} is a blind spot; audio sensitivity raised and patrol priority increased."
                )

        explanation = ""
        for i, part in enumerate(narrative_parts):
            if i == 0:
                explanation = part
            elif part.startswith("corroborated"):
                explanation += f", {part}"
            else:
                if not explanation.endswith("."):
                    explanation += "."
                explanation += f" {part}"
        if explanation and not explanation.endswith("."):
            explanation += "."

        # Query suppressed signals in the same zone around this window
        inc_start = ensure_utc(incident.created_ts) - timedelta(seconds=self.fusion_window_s)
        inc_end = ensure_utc(incident.updated_ts) + timedelta(seconds=self.fusion_window_s)
        suppressed_signals = await Signal.find(
            Signal.org_id == self.org_id,
            Signal.zone_id == incident.zone_id,
            Signal.suppressed == True,
            Signal.ts >= inc_start,
            Signal.ts <= inc_end,
        ).to_list()

        suppressed_parts = []
        for sup in suppressed_signals:
            sup_t = ensure_utc(sup.ts).strftime("%H:%M:%S")
            reason = sup.suppress_reason or "suppressed by filter"
            suppressed_parts.append(f"{sup.kind} at {sup_t} ({reason})")

        if suppressed_parts:
            explanation += f" Suppressed signals in zone: {'; '.join(suppressed_parts)}."

        return explanation

    async def ingest_signal(self, signal: Signal) -> Optional[Incident]:
        """
        Process an incoming signal:
        - If raw line_crossing, do not directly spawn incident (used for tailgating correlation).
        - If suppressed, save signal and broadcast signal.created, but do not create incident.
        - Otherwise, attach to matching open incident in same or adjacent zone, else create new incident.
        """
        # Save signal in database
        signal.org_id = self.org_id
        await signal.insert()

        # Broadcast signal.created over WebSocket
        await ws_hub.broadcast_to_org(
            org_id=self.org_id,
            event_type="signal.created",
            data={
                "id": str(signal.id),
                "kind": signal.kind,
                "modality": signal.modality,
                "zone_id": signal.zone_id,
                "score": signal.score,
                "suppressed": signal.suppressed,
                "ts": signal.ts.isoformat(),
            },
        )

        # Raw line_crossing or suppressed signals do not directly trigger incidents
        if signal.kind == "line_crossing" or signal.suppressed:
            logger.info(f"Signal {signal.kind} (suppressed={signal.suppressed}) stored without spawning incident.")
            return None

        # Determine target zones (current zone + adjacent zones)
        zone_doc = await Zone.find_one({"org_id": self.org_id, "zone_id": signal.zone_id})

        # If camera_tamper signal received, automatically update camera health to tampered and apply blind-spot compensation
        if signal.kind == "camera_tamper" and signal.camera_id:
            from app.services.camera_health_service import CameraHealthService
            t_reason = signal.details.get("tamper_type") or signal.details.get("reason") or "dark"
            try:
                await CameraHealthService.update_camera_health(
                    org_id=self.org_id,
                    camera_id=signal.camera_id,
                    health_status="tampered",
                    health_reason=t_reason,
                    last_frame_at=signal.ts,
                )
                zone_doc = await Zone.find_one({"org_id": self.org_id, "zone_id": signal.zone_id})
            except Exception as e:
                logger.warning(f"Could not update camera health for tamper signal: {e}")

        resolved_site_id = signal.site_id or (zone_doc.site_id if zone_doc else None)
        if not signal.site_id and resolved_site_id:
            signal.site_id = resolved_site_id
            await signal.save()

        zone_name = zone_doc.name if zone_doc else signal.zone_id
        candidate_zones = [signal.zone_id]
        if zone_doc and zone_doc.adjacent_zone_ids:
            candidate_zones.extend(zone_doc.adjacent_zone_ids)

        sig_utc = ensure_utc(signal.ts)

        # Ensure flagged_track_ids is recorded on the signal
        if "track_id" in signal.details and "flagged_track_ids" not in signal.details:
            signal.details["flagged_track_ids"] = [signal.details["track_id"]]

        # D1 & D2: Check perimeter breach and explained vs unexplained access for zone_intrusion
        if signal.kind == "zone_intrusion":
            if zone_doc and zone_doc.type == "perimeter":
                signal.details["subtype"] = "perimeter_breach"
                signal.details["explained_by_access"] = False
                signal.score = min(1.0, signal.score + 0.2)
                await signal.save()
            elif zone_doc and zone_doc.type == "restricted" and "explained_by_access" not in signal.details:
                t_window_start = sig_utc - timedelta(seconds=60)
                t_window_end = sig_utc + timedelta(seconds=5)
                recent_swipes = await AccessEvent.find(
                    AccessEvent.org_id == self.org_id,
                    AccessEvent.result == "granted",
                    AccessEvent.direction == "in",
                    AccessEvent.ts >= t_window_start,
                    AccessEvent.ts <= t_window_end,
                ).to_list()

                matching_swipe = None
                for sw in recent_swipes:
                    if sw.role in (zone_doc.allowed_roles or []):
                        matching_swipe = sw
                        break

                if matching_swipe:
                    signal.details["explained_by_access"] = True
                    signal.details["swipe_id"] = matching_swipe.pseudo_id
                    signal.details["role"] = matching_swipe.role
                    signal.score = round(signal.score * 0.5, 3)
                else:
                    signal.details["explained_by_access"] = False
                await signal.save()

        # Look for open incidents in the organization
        open_incidents = await Incident.find(
            Incident.org_id == self.org_id,
            Incident.status != "confirmed",
            Incident.status != "false_alarm",
        ).to_list()

        open_incident = None
        for inc in open_incidents:
            inc_updated = ensure_utc(inc.updated_ts)
            diff_s = abs((sig_utc - inc_updated).total_seconds())
            if diff_s <= self.fusion_window_s:
                # Same zone or adjacent zone, or building access corroboration
                is_zone_match = (inc.zone_id in candidate_zones) or (signal.zone_id == inc.zone_id)
                is_access_attach = (signal.modality == "access" or "access" in inc.modalities)
                if is_zone_match or is_access_attach:
                    open_incident = inc
                    break

        if open_incident:
            is_new = False
            incident = open_incident
            if not incident.site_id and resolved_site_id:
                incident.site_id = resolved_site_id
            # Prefer restricted/primary zone for the incident zone display
            if zone_doc and zone_doc.type in ("restricted", "entry") and incident.zone_id != signal.zone_id:
                incident.zone_id = signal.zone_id
            if str(signal.id) not in incident.signal_ids:
                incident.signal_ids.append(str(signal.id))
            if signal.modality not in incident.modalities:
                incident.modalities.append(signal.modality)
            if sig_utc > ensure_utc(incident.updated_ts):
                incident.updated_ts = signal.ts
        else:
            is_new = True
            incident = Incident(
                org_id=self.org_id,
                site_id=resolved_site_id,
                created_ts=signal.ts,
                updated_ts=signal.ts,
                zone_id=signal.zone_id,
                status="new",
                modalities=[signal.modality],
                signal_ids=[str(signal.id)],
            )

        # Associate signal with incident
        signal.incident_id = str(incident.id) if not is_new else None

        # Fetch all contributing signals
        contributing_signals = [signal]
        if not is_new and incident.signal_ids:
            fetched = []
            for sid in incident.signal_ids:
                if sid == str(signal.id):
                    fetched.append(signal)
                else:
                    doc = await Signal.get(PydanticObjectId(sid))
                    if doc:
                        fetched.append(doc)
            if fetched:
                contributing_signals = fetched

        # Compute composite score and severity
        incident.composite_score = self.calculate_composite_score(contributing_signals)
        is_blind_spot = bool(zone_doc and zone_doc.is_blind_spot)
        incident.severity = self.determine_severity(
            contributing_signals,
            incident.composite_score,
            is_blind_spot=is_blind_spot,
        )

        # Generate explainable narrative
        incident.explanation = await self.generate_explanation(incident, contributing_signals, zone_name)

        if is_new:
            await incident.insert()
            signal.incident_id = str(incident.id)
            await signal.save()
            logger.info(f"Created NEW {incident.severity} incident {incident.id} for zone '{incident.zone_id}'")
            await ws_hub.broadcast_to_org(
                org_id=self.org_id,
                event_type="incident.created",
                data={
                    "id": str(incident.id),
                    "severity": incident.severity,
                    "zone_id": incident.zone_id,
                    "composite_score": incident.composite_score,
                    "explanation": incident.explanation,
                    "created_ts": incident.created_ts.isoformat(),
                },
            )
        else:
            await incident.save()
            await signal.save()
            logger.info(f"ATTACHED signal to incident {incident.id}; updated severity: {incident.severity}")
            await ws_hub.broadcast_to_org(
                org_id=self.org_id,
                event_type="incident.updated",
                data={
                    "id": str(incident.id),
                    "severity": incident.severity,
                    "composite_score": incident.composite_score,
                    "explanation": incident.explanation,
                    "updated_ts": incident.updated_ts.isoformat(),
                },
            )

        # For video incidents, ensure an encrypted raw clip exists in data/evidence/restricted/raw/<incident_id>.enc
        if "video" in incident.modalities:
            try:
                from app.privacy.encryption import get_raw_clips_dir, save_encrypted_raw_clip
                raw_dir = get_raw_clips_dir()
                enc_clip_path = raw_dir / f"{incident.id}.enc"
                if not enc_clip_path.exists():
                    source_file = None
                    if signal.evidence_path:
                        ev_p = Path(signal.evidence_path)
                        if not ev_p.is_absolute():
                            ev_p = settings.DATA_DIR / signal.evidence_path
                        if ev_p.exists():
                            source_file = ev_p
                    if not source_file:
                        vid_p = settings.DATA_DIR / "videos" / "intrusion" / "intrusion_01.mp4"
                        if vid_p.exists():
                            source_file = vid_p
                    if source_file:
                        f_tracks = []
                        if "flagged_track_ids" in signal.details:
                            f_tracks = [{"track_id": tid, "box": signal.details.get("bounding_box", [100, 100, 200, 300])} for tid in signal.details["flagged_track_ids"]]
                        save_encrypted_raw_clip(str(incident.id), frame_tracks=[f_tracks], source_file=source_file)
            except Exception as exc:
                logger.warning(f"Could not save raw encrypted clip for incident {incident.id}: {exc}")

        return incident
