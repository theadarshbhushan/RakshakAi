"""
Risk Analytics Router (/api/v1/analytics).
Provides review-weighted heatmaps, patrol planning, and SLA/incident summaries.
Tenant-scoped with 'incidents:read' permission.

Endpoints:
- GET /heatmap?days=30: Zone x hour-of-day (0-23, org timezone) grid with review-weighted risk scores.
- GET /patrol-plan?shift_start=22:00&shift_end=06:00: Shift-targeted zone risk ranking with boosts and explanations.
- GET /summary?days=30: Totals by severity, false-alarm rate, avg response times, and top incident kinds.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import zoneinfo

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.deps import get_current_user, require_permission
from app.models.incident import Incident
from app.models.organization import Organization
from app.models.signal import Signal
from app.models.user import User
from app.models.zone import Zone

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# Severity weights: critical=4, high=3, medium=2, low=1
SEVERITY_WEIGHTS: Dict[str, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}

# Review weights: confirmed=1.0, investigating/new/acknowledged=0.6, false_alarm=0.1
REVIEW_WEIGHTS: Dict[str, float] = {
    "confirmed": 1.0,
    "investigating": 0.6,
    "new": 0.6,
    "acknowledged": 0.6,
    "false_alarm": 0.1,
}


def calculate_incident_risk_score(severity: str, status: str) -> float:
    """Calculate single incident risk contribution: severity_weight * review_weight."""
    sev_w = SEVERITY_WEIGHTS.get(severity.lower(), 1.0)
    rev_w = REVIEW_WEIGHTS.get(status.lower(), 0.6)
    return round(sev_w * rev_w, 3)


def ensure_utc(dt: Optional[datetime]) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def get_org_timezone(org_id: str) -> str:
    """Fetch org timezone or fallback to Asia/Kolkata / UTC."""
    try:
        org = await Organization.get(PydanticObjectId(org_id))
        if org and org.settings and "timezone" in org.settings:
            return org.settings["timezone"]
    except Exception:
        pass
    return "Asia/Kolkata"


def to_org_hour(dt: datetime, tz_name: str) -> int:
    """Convert UTC datetime to organization timezone and return hour of day (0-23)."""
    utc_dt = ensure_utc(dt)
    try:
        target_tz = zoneinfo.ZoneInfo(tz_name)
        return utc_dt.astimezone(target_tz).hour
    except Exception:
        return utc_dt.hour


def parse_shift_hours(shift_start: str, shift_end: str) -> List[int]:
    """
    Parse shift hours from 'HH:MM' strings into a list of hours (0-23).
    Handles overnight shifts (e.g. 22:00 to 06:00 -> [22, 23, 0, 1, 2, 3, 4, 5]).
    """
    try:
        s_hr = int(shift_start.split(":")[0])
        e_hr = int(shift_end.split(":")[0])
    except Exception:
        s_hr, e_hr = 22, 6

    if s_hr <= e_hr:
        if s_hr == e_hr:
            return list(range(24))
        return list(range(s_hr, e_hr))
    else:
        # Overnight shift crossing midnight
        return list(range(s_hr, 24)) + list(range(0, e_hr))


# =====================================================================
# Response Schemas
# =====================================================================


class HeatmapCell(BaseModel):
    incident_count: int = 0
    confirmed: int = 0
    false_alarms: int = 0
    pending: int = 0
    risk_score: float = 0.0


class ZoneHeatmapRow(BaseModel):
    zone_id: str
    zone_name: str
    hours: Dict[str, HeatmapCell]
    total: HeatmapCell


class HeatmapResponse(BaseModel):
    timeframe_days: int
    timezone: str
    zones: List[ZoneHeatmapRow]
    per_zone: Dict[str, HeatmapCell]
    per_hour: Dict[str, HeatmapCell]
    total: HeatmapCell


class PatrolPlanItem(BaseModel):
    zone_id: str
    zone_name: str
    risk_score: float
    peak_hour: int
    suggested_check_time: str
    reason: str
    open_incidents: int
    recent_tamper: bool
    recent_sos: bool


class PatrolPlanResponse(BaseModel):
    shift_start: str
    shift_end: str
    shift_hours: List[int]
    timezone: str
    plan: List[PatrolPlanItem]


class AnalyticsSummaryResponse(BaseModel):
    timeframe_days: int
    total_incidents: int
    totals_by_severity: Dict[str, int]
    false_alarm_rate: float
    avg_time_to_acknowledge_s: float
    avg_time_to_review_s: float
    top_incident_kinds: List[Dict[str, Any]]
    status_breakdown: Dict[str, int]


# =====================================================================
# 1. Review-Weighted Risk Heatmap
# =====================================================================


@router.get("/heatmap", response_model=HeatmapResponse, dependencies=[Depends(require_permission("incidents:read"))])
async def get_risk_heatmap(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    current_user: User = Depends(get_current_user),
):
    """
    Returns a zone x hour-of-day (0-23, org timezone) grid.
    Each cell contains:
    - incident_count, confirmed, false_alarms, pending
    - risk_score = sum(severity_weight * review_weight)
      severity_weight: critical=4, high=3, medium=2, low=1
      review_weight: confirmed=1.0, investigating/new=0.6, false_alarm=0.1
    Includes per-zone totals and per-hour totals.
    """
    org_id = current_user.org_id
    tz_name = await get_org_timezone(org_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # 1. Fetch zones for org
    zones = await Zone.find({"org_id": org_id}).sort("name").to_list()
    zone_map = {z.zone_id: z.name for z in zones}

    # 2. Fetch incidents for org in timeframe
    incidents = await Incident.find(
        Incident.org_id == org_id,
        Incident.created_ts >= cutoff,
    ).to_list()

    # 3. Initialize grid data structures
    # grid[zone_id][hour] -> stats
    def new_cell_data():
        return {"incident_count": 0, "confirmed": 0, "false_alarms": 0, "pending": 0, "risk_score": 0.0}

    grid_data: Dict[str, Dict[int, Dict[str, Any]]] = {
        z_id: {hr: new_cell_data() for hr in range(24)} for z_id in zone_map
    }
    per_hour_data: Dict[int, Dict[str, Any]] = {hr: new_cell_data() for hr in range(24)}
    per_zone_data: Dict[str, Dict[str, Any]] = {z_id: new_cell_data() for z_id in zone_map}
    overall_total = new_cell_data()

    # 4. Populate grid with review-weighted scoring
    for inc in incidents:
        z_id = inc.zone_id
        if z_id not in grid_data:
            grid_data[z_id] = {hr: new_cell_data() for hr in range(24)}
            per_zone_data[z_id] = new_cell_data()
            zone_map[z_id] = z_id.replace("_", " ").title()

        hr = to_org_hour(inc.created_ts, tz_name)
        risk = calculate_incident_risk_score(inc.severity, inc.status)
        is_conf = inc.status == "confirmed"
        is_fa = inc.status == "false_alarm"
        is_pend = inc.status in ("new", "investigating", "acknowledged")

        # Update cell
        cell = grid_data[z_id][hr]
        cell["incident_count"] += 1
        cell["risk_score"] += risk
        if is_conf:
            cell["confirmed"] += 1
        elif is_fa:
            cell["false_alarms"] += 1
        elif is_pend:
            cell["pending"] += 1

        # Update per zone
        pz = per_zone_data[z_id]
        pz["incident_count"] += 1
        pz["risk_score"] += risk
        if is_conf:
            pz["confirmed"] += 1
        elif is_fa:
            pz["false_alarms"] += 1
        elif is_pend:
            pz["pending"] += 1

        # Update per hour
        ph = per_hour_data[hr]
        ph["incident_count"] += 1
        ph["risk_score"] += risk
        if is_conf:
            ph["confirmed"] += 1
        elif is_fa:
            ph["false_alarms"] += 1
        elif is_pend:
            ph["pending"] += 1

        # Update overall
        overall_total["incident_count"] += 1
        overall_total["risk_score"] += risk
        if is_conf:
            overall_total["confirmed"] += 1
        elif is_fa:
            overall_total["false_alarms"] += 1
        elif is_pend:
            overall_total["pending"] += 1

    # Format output
    zone_rows: List[ZoneHeatmapRow] = []
    for z_id, z_name in zone_map.items():
        hours_dict = {
            str(hr): HeatmapCell(
                incident_count=grid_data[z_id][hr]["incident_count"],
                confirmed=grid_data[z_id][hr]["confirmed"],
                false_alarms=grid_data[z_id][hr]["false_alarms"],
                pending=grid_data[z_id][hr]["pending"],
                risk_score=round(grid_data[z_id][hr]["risk_score"], 2),
            )
            for hr in range(24)
        }
        total_cell = HeatmapCell(
            incident_count=per_zone_data[z_id]["incident_count"],
            confirmed=per_zone_data[z_id]["confirmed"],
            false_alarms=per_zone_data[z_id]["false_alarms"],
            pending=per_zone_data[z_id]["pending"],
            risk_score=round(per_zone_data[z_id]["risk_score"], 2),
        )
        zone_rows.append(ZoneHeatmapRow(
            zone_id=z_id,
            zone_name=z_name,
            hours=hours_dict,
            total=total_cell,
        ))

    per_zone_res = {
        z_id: HeatmapCell(
            incident_count=pz["incident_count"],
            confirmed=pz["confirmed"],
            false_alarms=pz["false_alarms"],
            pending=pz["pending"],
            risk_score=round(pz["risk_score"], 2),
        )
        for z_id, pz in per_zone_data.items()
    }

    per_hour_res = {
        str(hr): HeatmapCell(
            incident_count=ph["incident_count"],
            confirmed=ph["confirmed"],
            false_alarms=ph["false_alarms"],
            pending=ph["pending"],
            risk_score=round(ph["risk_score"], 2),
        )
        for hr, ph in per_hour_data.items()
    }

    return HeatmapResponse(
        timeframe_days=days,
        timezone=tz_name,
        zones=zone_rows,
        per_zone=per_zone_res,
        per_hour=per_hour_res,
        total=HeatmapCell(
            incident_count=overall_total["incident_count"],
            confirmed=overall_total["confirmed"],
            false_alarms=overall_total["false_alarms"],
            pending=overall_total["pending"],
            risk_score=round(overall_total["risk_score"], 2),
        ),
    )


# =====================================================================
# 2. Risk-Based Shift Patrol Planner
# =====================================================================


@router.get("/patrol-plan", response_model=PatrolPlanResponse, dependencies=[Depends(require_permission("incidents:read"))])
async def get_patrol_plan(
    shift_start: str = Query("22:00", description="Shift start time (HH:MM, org timezone)"),
    shift_end: str = Query("06:00", description="Shift end time (HH:MM, org timezone)"),
    days: int = Query(30, ge=1, le=365, description="Historical lookback window in days"),
    current_user: User = Depends(get_current_user),
):
    """
    Ranks zones by expected risk for the shift's hours:
    - Baseline: sum of review-weighted risk_score over shift hours in past N days
    - Boosts:
      + Open incidents pending investigation (+3.0 per open incident)
      + Camera tamper in last 48h (+2.5)
      + Student SOS in last 48h (+3.0)
    Returns ordered patrol recommendations with peak hour, reason text, and suggested check time.
    """
    org_id = current_user.org_id
    tz_name = await get_org_timezone(org_id)
    shift_hours = parse_shift_hours(shift_start, shift_end)
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=days)
    recent_signals_cutoff = now_utc - timedelta(hours=48)

    # 1. Fetch zones
    zones = await Zone.find({"org_id": org_id}).sort("name").to_list()
    zone_map = {z.zone_id: z.name for z in zones}

    # 2. Fetch incidents in timeframe
    incidents = await Incident.find(
        Incident.org_id == org_id,
        Incident.created_ts >= cutoff,
    ).to_list()

    # 3. Fetch recent signals for tamper / student_sos boosts
    recent_tamper_signals = await Signal.find(
        Signal.org_id == org_id,
        Signal.kind == "camera_tamper",
        Signal.ts >= recent_signals_cutoff,
    ).to_list()
    tamper_zones = set(s.zone_id for s in recent_tamper_signals)

    recent_sos_signals = await Signal.find(
        Signal.org_id == org_id,
        Signal.kind == "student_sos",
        Signal.ts >= recent_signals_cutoff,
    ).to_list()
    sos_zones = set(s.zone_id for s in recent_sos_signals)

    # 4. Open incidents in each zone
    open_incidents_by_zone: Dict[str, int] = {z_id: 0 for z_id in zone_map}
    for inc in incidents:
        if inc.status in ("new", "investigating"):
            open_incidents_by_zone[inc.zone_id] = open_incidents_by_zone.get(inc.zone_id, 0) + 1

    # 5. Calculate shift risk and collect incident metadata per zone
    # zone -> hour -> risk
    zone_shift_hourly: Dict[str, Dict[int, float]] = {
        z_id: {hr: 0.0 for hr in shift_hours} for z_id in zone_map
    }
    # zone -> list of confirmed incidents during shift
    zone_shift_confirmed: Dict[str, List[Incident]] = {z_id: [] for z_id in zone_map}

    for inc in incidents:
        z_id = inc.zone_id
        if z_id not in zone_shift_hourly:
            zone_shift_hourly[z_id] = {hr: 0.0 for hr in shift_hours}
            zone_shift_confirmed[z_id] = []
            zone_map[z_id] = z_id.replace("_", " ").title()

        hr = to_org_hour(inc.created_ts, tz_name)
        if hr in shift_hours:
            risk = calculate_incident_risk_score(inc.severity, inc.status)
            zone_shift_hourly[z_id][hr] += risk
            if inc.status == "confirmed":
                zone_shift_confirmed[z_id].append(inc)

    # 6. Rank each zone
    plan_items: List[PatrolPlanItem] = []
    for z_id, z_name in zone_map.items():
        hourly_scores = zone_shift_hourly.get(z_id, {})
        base_shift_risk = sum(hourly_scores.values())

        # Determine peak hour within shift
        if hourly_scores and any(hourly_scores.values()):
            peak_hr = max(hourly_scores, key=hourly_scores.get)
        else:
            peak_hr = shift_hours[0]

        # Calculate boosts
        open_cnt = open_incidents_by_zone.get(z_id, 0)
        has_tamper = z_id in tamper_zones
        has_sos = z_id in sos_zones

        boost = 0.0
        if open_cnt > 0:
            boost += 3.0 * open_cnt
        if has_tamper:
            boost += 2.5
        if has_sos:
            boost += 3.0

        total_risk = round(base_shift_risk + boost, 2)

        # Generate explanatory reason text
        reasons: List[str] = []
        conf_list = zone_shift_confirmed.get(z_id, [])
        if conf_list:
            reasons.append(
                f"{len(conf_list)} confirmed incident{'s' if len(conf_list) > 1 else ''} between {shift_start} and {shift_end} in the last {days} days"
            )

        if has_tamper:
            reasons.append("camera tampered recently")
        if has_sos:
            reasons.append("recent student SOS reported")
        if open_cnt > 0:
            reasons.append(f"{open_cnt} active incident{'s' if open_cnt > 1 else ''} pending review")

        if not reasons:
            reason_text = f"Routine patrol check; low historical activity between {shift_start} and {shift_end}."
        else:
            reason_text = "; ".join(reasons) + "."

        suggested_time = f"{peak_hr:02d}:30"

        plan_items.append(PatrolPlanItem(
            zone_id=z_id,
            zone_name=z_name,
            risk_score=total_risk,
            peak_hour=peak_hr,
            suggested_check_time=suggested_time,
            reason=reason_text,
            open_incidents=open_cnt,
            recent_tamper=has_tamper,
            recent_sos=has_sos,
        ))

    # Sort descending by risk_score
    plan_items.sort(key=lambda item: item.risk_score, reverse=True)

    return PatrolPlanResponse(
        shift_start=shift_start,
        shift_end=shift_end,
        shift_hours=shift_hours,
        timezone=tz_name,
        plan=plan_items,
    )


# =====================================================================
# 3. Analytics Incident Summary & SLA Metrics
# =====================================================================


@router.get("/summary", response_model=AnalyticsSummaryResponse, dependencies=[Depends(require_permission("incidents:read"))])
async def get_analytics_summary(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    current_user: User = Depends(get_current_user),
):
    """
    Summary metrics:
    - Totals by severity (critical, high, medium, low)
    - False-alarm rate (false_alarms / total_incidents)
    - Average time to acknowledge (seconds)
    - Average time to review (seconds)
    - Top incident kinds
    - Status breakdown
    """
    org_id = current_user.org_id
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    incidents = await Incident.find(
        Incident.org_id == org_id,
        Incident.created_ts >= cutoff,
    ).to_list()

    total_count = len(incidents)
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    status_counts = {"new": 0, "acknowledged": 0, "investigating": 0, "confirmed": 0, "false_alarm": 0}

    ack_times_s: List[float] = []
    review_times_s: List[float] = []
    signal_ids_to_fetch: List[str] = []

    for inc in incidents:
        sev = inc.severity.lower()
        if sev in severity_counts:
            severity_counts[sev] += 1
        st = inc.status.lower()
        status_counts[st] = status_counts.get(st, 0) + 1

        c_ts = ensure_utc(inc.created_ts)
        if inc.acknowledged_ts:
            ack_s = (ensure_utc(inc.acknowledged_ts) - c_ts).total_seconds()
            if ack_s >= 0:
                ack_times_s.append(ack_s)
        if inc.reviewed_ts:
            rev_s = (ensure_utc(inc.reviewed_ts) - c_ts).total_seconds()
            if rev_s >= 0:
                review_times_s.append(rev_s)

        if inc.signal_ids:
            signal_ids_to_fetch.extend(inc.signal_ids[:2])

    # False-alarm rate
    false_alarm_cnt = status_counts.get("false_alarm", 0)
    fa_rate = round(false_alarm_cnt / total_count, 3) if total_count > 0 else 0.0

    # Averages
    avg_ack = round(sum(ack_times_s) / len(ack_times_s), 1) if ack_times_s else 0.0
    avg_rev = round(sum(review_times_s) / len(review_times_s), 1) if review_times_s else 0.0

    # Top incident kinds from contributing signals
    kind_counts: Dict[str, int] = {}
    if signal_ids_to_fetch:
        # Sample or query signals
        try:
            from beanie import PydanticObjectId
            p_ids = [PydanticObjectId(sid) for sid in signal_ids_to_fetch if len(sid) == 24]
            signals = await Signal.find({"_id": {"$in": p_ids}}).to_list()
            for s in signals:
                kind_counts[s.kind] = kind_counts.get(s.kind, 0) + 1
        except Exception:
            pass

    # If no signals found, fallback to incident modalities or explanations
    if not kind_counts:
        for inc in incidents:
            for m in inc.modalities:
                kind_counts[m] = kind_counts.get(m, 0) + 1

    top_kinds = [
        {"kind": k, "count": v}
        for k, v in sorted(kind_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return AnalyticsSummaryResponse(
        timeframe_days=days,
        total_incidents=total_count,
        totals_by_severity=severity_counts,
        false_alarm_rate=fa_rate,
        avg_time_to_acknowledge_s=avg_ack,
        avg_time_to_review_s=avg_rev,
        top_incident_kinds=top_kinds,
        status_breakdown=status_counts,
    )
