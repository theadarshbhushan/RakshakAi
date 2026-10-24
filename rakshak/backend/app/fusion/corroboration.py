"""
Real Fusion Engine for RakshakAI: multi-modal corroboration and explainability.
Fuses Video, Audio, and Access signals within temporal and spatial adjacency windows.
Calculates Bayesian composite confidence score, determines severity, and generates
human-readable explanation narratives detailing all corroborating and suppressed signals.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from beanie import PydanticObjectId

from app.models.incident import Incident
from app.models.signal import Signal
from app.models.zone import Zone
from app.realtime.ws import ws_hub

logger = logging.getLogger("rakshakai.fusion")

DEFAULT_WEIGHTS = {
    "video": 0.9,
    "audio": 0.8,
    "access": 0.7,
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

    def determine_severity(self, signals: List[Signal], composite_score: float) -> str:
        """
        Severity determination rules:
        - 1 modality & composite < 0.6 -> low
        - 1 modality & composite >= 0.6 -> medium
        - 2 modalities -> high
        - 3 modalities OR (fight AND distress_audio) -> critical
        """
        active_signals = [s for s in signals if not s.suppressed]
        modalities = set(s.modality for s in active_signals)
        kinds = set(s.kind for s in active_signals)

        if len(modalities) >= 3 or ("fight" in kinds and "distress_audio" in kinds):
            return "critical"
        if len(modalities) == 2:
            return "high"
        if len(modalities) <= 1:
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
        sorted_signals = sorted(signals, key=lambda s: ensure_utc(s.ts))
        narrative_parts: List[str] = []
        base_time: Optional[datetime] = None

        for s in sorted_signals:
            s_ts = ensure_utc(s.ts)
            t_str = s_ts.strftime("%H:%M:%S")
            diff_text = ""
            if base_time is None:
                base_time = s_ts
            else:
                diff_s = int(abs((s_ts - base_time).total_seconds()))
                diff_text = f" {diff_s}s later"

            if s.kind == "zone_intrusion":
                narrative_parts.append(
                    f"Person entered zone '{zone_name}' at {t_str} (score {s.score:.2f} vs threshold {s.threshold:.2f})."
                )
            elif s.kind == "fight":
                narrative_parts.append(
                    f"Physical fight detected in zone '{zone_name}' at {t_str}{diff_text} (score {s.score:.2f})."
                )
            elif s.kind == "distress_audio":
                sound_label = s.details.get("label", "Distress sound")
                narrative_parts.append(
                    f"Corroborated by distress audio ({sound_label} {s.score:.2f}){diff_text}."
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

        # Query suppressed signals in the same zone around this window
        suppressed_signals = await Signal.find(
            Signal.org_id == self.org_id,
            Signal.zone_id == incident.zone_id,
            Signal.suppressed == True,
        ).to_list()

        suppressed_parts = []
        for sup in suppressed_signals:
            sup_t = ensure_utc(sup.ts).strftime("%H:%M:%S")
            reason = sup.suppress_reason or "suppressed by filter"
            suppressed_parts.append(f"{sup.kind} at {sup_t} ({reason})")

        explanation = " ".join(narrative_parts)
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
        zone_name = zone_doc.name if zone_doc else signal.zone_id
        candidate_zones = [signal.zone_id]
        if zone_doc and zone_doc.adjacent_zone_ids:
            candidate_zones.extend(zone_doc.adjacent_zone_ids)

        sig_utc = ensure_utc(signal.ts)

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
                is_access_attach = (signal.modality == "access" or inc.zone_id in candidate_zones or signal.zone_id in candidate_zones)
                if is_zone_match or is_access_attach:
                    open_incident = inc
                    break

        if open_incident:
            is_new = False
            incident = open_incident
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
                site_id=signal.site_id,
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
        incident.severity = self.determine_severity(contributing_signals, incident.composite_score)

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

        return incident
