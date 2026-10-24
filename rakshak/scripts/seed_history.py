"""
Seed realistic historical incidents and signals for RakshakAI demo.
Concentrated over the past 30 days on:
- Terrace: late night curfew breaches (22:00 - 04:00)
- Common Room: evening altercations & noise distress (18:00 - 23:00)
- Block B Entry & Corridor 2F: tailgating & student SOS reports

Mixed review outcomes: confirmed (~60%), false alarms (~25%), pending/investigating (~15%).
All marked with source="seed_history", cleanly removable via:
POST /api/v1/scenarios/reset?include_history=true
"""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random
import sys
import zoneinfo

backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.db.mongo import init_db, close_db
from app.models.incident import Incident
from app.models.organization import Organization, Site
from app.models.signal import Signal
from app.models.zone import Zone


async def seed_history(close_when_done: bool = True) -> None:
    await init_db()
    print("--- Seeding Historical Incident Data (Past 30 Days) ---")

    # 1. Resolve Sunrise Organization
    org = await Organization.find_one(Organization.slug == "sunrise")
    if not org:
        org = await Organization.find_one()
    if not org:
        print("Error: No organization found in database. Run scripts/seed_db.py first.")
        if close_when_done:
            await close_db()
        return

    org_id = str(org.id)
    org_name = org.name
    tz_str = org.settings.get("timezone", "Asia/Kolkata") if org.settings else "Asia/Kolkata"
    try:
        org_tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        org_tz = timezone.utc

    site = await Site.find_one(Site.org_id == org_id)
    site_id = str(site.id) if site else None

    # 2. Clear previous historical seeds for this org
    del_inc = await Incident.find({"org_id": org_id, "source": "seed_history"}).delete()
    del_sig = await Signal.find({"org_id": org_id, "source": "seed_history"}).delete()
    if del_inc or del_sig:
        print(f"Cleaned up previous history: {del_inc.deleted_count} incidents, {del_sig.deleted_count} signals removed.")

    # 3. Target zone specs
    zones = await Zone.find({"org_id": org_id}).to_list()
    zone_ids = [z.zone_id for z in zones]

    # Map zones or fallback to standard demo zones
    terrace_zid = "terrace" if "terrace" in zone_ids else (zone_ids[0] if zone_ids else "terrace")
    common_zid = "common_room" if "common_room" in zone_ids else (zone_ids[1] if len(zone_ids) > 1 else terrace_zid)
    entry_zid = "block_b_entry" if "block_b_entry" in zone_ids else (zone_ids[2] if len(zone_ids) > 2 else terrace_zid)
    corridor_zid = "corridor_2f" if "corridor_2f" in zone_ids else (zone_ids[3] if len(zone_ids) > 3 else terrace_zid)

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(org_tz)

    rng = random.Random(42)  # Deterministic seed for reproducible demo analytics

    incidents_to_create = []
    signals_to_create = []

    # Helper to calculate UTC datetime from days_ago and local hour/minute
    def make_event_time(days_ago: int, local_hour: int, local_minute: int) -> datetime:
        target_day = (now_local - timedelta(days=days_ago)).date()
        local_dt = datetime(target_day.year, target_day.month, target_day.day, local_hour, local_minute, tzinfo=org_tz)
        return local_dt.astimezone(timezone.utc)

    # -------------------------------------------------------------------------
    # Group A: Terrace Late Night (28 incidents)
    # Hours: 23, 0, 1, 2, 3 (heavy concentration at 23:00 and 01:00)
    # -------------------------------------------------------------------------
    terrace_hours = [22, 23, 23, 23, 0, 0, 1, 1, 1, 2, 2, 3]
    for i in range(28):
        days_ago = rng.randint(1, 29)
        l_hr = rng.choice(terrace_hours)
        l_min = rng.randint(5, 55)
        ev_ts = make_event_time(days_ago, l_hr, l_min)

        # Distribute review outcomes: 17 confirmed, 7 false alarm, 4 investigating/new
        if i < 17:
            status = "confirmed"
            ack_s = rng.randint(40, 95)
            rev_s = rng.randint(300, 900)
            ack_ts = ev_ts + timedelta(seconds=ack_s)
            rev_ts = ev_ts + timedelta(seconds=rev_s)
            rev_by = "warden@sunrise.demo"
            rev_note = "Confirmed unauthorized rooftop access during curfew hours."
            severity = rng.choice(["high", "critical", "high", "medium"])
        elif i < 24:
            status = "false_alarm"
            ack_s = rng.randint(50, 120)
            rev_s = rng.randint(400, 1100)
            ack_ts = ev_ts + timedelta(seconds=ack_s)
            rev_ts = ev_ts + timedelta(seconds=rev_s)
            rev_by = "warden@sunrise.demo"
            rev_note = "False alarm: Authorized HVAC maintenance crew."
            severity = rng.choice(["medium", "low", "medium"])
        else:
            status = rng.choice(["investigating", "new"])
            ack_ts = ev_ts + timedelta(seconds=55) if status == "investigating" else None
            rev_ts = None
            rev_by = None
            rev_note = None
            severity = "high"

        kind = rng.choice(["zone_intrusion", "zone_intrusion", "loitering", "camera_tamper"])
        modality = "video"
        score = round(rng.uniform(0.82, 0.96), 2)

        inc = Incident(
            org_id=org_id,
            site_id=site_id,
            zone_id=terrace_zid,
            severity=severity,
            composite_score=score,
            modalities=[modality],
            status=status,
            created_ts=ev_ts,
            updated_ts=rev_ts or ack_ts or ev_ts,
            acknowledged_by="guard_on_duty" if ack_ts else None,
            acknowledged_ts=ack_ts,
            reviewer=rev_by,
            reviewed_ts=rev_ts,
            review_note=rev_note,
            explanation=f"Person detected on Terrace during curfew hours (score {score:.2f}).",
            source="seed_history",
        )
        incidents_to_create.append(inc)

        sig = Signal(
            org_id=org_id,
            site_id=site_id,
            zone_id=terrace_zid,
            ts=ev_ts,
            modality=modality,
            kind=kind,
            score=score,
            details={"label": "person", "duration_s": rng.randint(45, 120)},
            source="seed_history",
        )
        signals_to_create.append((inc, sig))

    # -------------------------------------------------------------------------
    # Group B: Common Room Evening (20 incidents)
    # Hours: 18, 19, 20, 21, 22
    # -------------------------------------------------------------------------
    common_hours = [18, 19, 19, 20, 20, 21, 21, 22]
    for i in range(20):
        days_ago = rng.randint(1, 29)
        l_hr = rng.choice(common_hours)
        l_min = rng.randint(2, 58)
        ev_ts = make_event_time(days_ago, l_hr, l_min)

        # 12 confirmed, 5 false alarm, 3 new/investigating
        if i < 12:
            status = "confirmed"
            ack_s = rng.randint(30, 80)
            rev_s = rng.randint(250, 750)
            ack_ts = ev_ts + timedelta(seconds=ack_s)
            rev_ts = ev_ts + timedelta(seconds=rev_s)
            rev_by = "warden@sunrise.demo"
            rev_note = "Confirmed student altercation; security dispatched."
            severity = rng.choice(["high", "critical", "critical"])
        elif i < 17:
            status = "false_alarm"
            ack_s = rng.randint(60, 130)
            rev_s = rng.randint(350, 950)
            ack_ts = ev_ts + timedelta(seconds=ack_s)
            rev_ts = ev_ts + timedelta(seconds=rev_s)
            rev_by = "warden@sunrise.demo"
            rev_note = "False alarm: Movie night sports celebration volume."
            severity = rng.choice(["medium", "low"])
        else:
            status = "investigating"
            ack_ts = ev_ts + timedelta(seconds=45)
            rev_ts = None
            rev_by = None
            rev_note = None
            severity = "high"

        kind = rng.choice(["fight", "distress_audio", "fight"])
        modality = "audio" if kind == "distress_audio" else "video"
        score = round(rng.uniform(0.78, 0.94), 2)

        inc = Incident(
            org_id=org_id,
            site_id=site_id,
            zone_id=common_zid,
            severity=severity,
            composite_score=score,
            modalities=[modality],
            status=status,
            created_ts=ev_ts,
            updated_ts=rev_ts or ack_ts or ev_ts,
            acknowledged_by="guard_on_duty" if ack_ts else None,
            acknowledged_ts=ack_ts,
            reviewer=rev_by,
            reviewed_ts=rev_ts,
            review_note=rev_note,
            explanation=f"Aggression / distress detected in Common Room (score {score:.2f}).",
            source="seed_history",
        )
        incidents_to_create.append(inc)

        sig = Signal(
            org_id=org_id,
            site_id=site_id,
            zone_id=common_zid,
            ts=ev_ts,
            modality=modality,
            kind=kind,
            score=score,
            details={"label": "screaming" if modality == "audio" else "aggressive_pose"},
            source="seed_history",
        )
        signals_to_create.append((inc, sig))

    # -------------------------------------------------------------------------
    # Group C: Entry & Corridor 2F (14 incidents)
    # Mixed hours: tailgating, student_sos, restricted_access
    # -------------------------------------------------------------------------
    entry_hours = [8, 9, 13, 14, 17, 21, 23, 1]
    for i in range(14):
        days_ago = rng.randint(1, 29)
        l_hr = rng.choice(entry_hours)
        l_min = rng.randint(5, 50)
        ev_ts = make_event_time(days_ago, l_hr, l_min)
        target_z = entry_zid if i % 2 == 0 else corridor_zid

        # 9 confirmed, 3 false alarm, 2 new
        if i < 9:
            status = "confirmed"
            ack_s = rng.randint(35, 75)
            rev_s = rng.randint(200, 600)
            ack_ts = ev_ts + timedelta(seconds=ack_s)
            rev_ts = ev_ts + timedelta(seconds=rev_s)
            rev_by = "warden@sunrise.demo"
            rev_note = "Tailgating / unauthorized entry confirmed on access log."
            severity = rng.choice(["medium", "high", "critical"])
        elif i < 12:
            status = "false_alarm"
            ack_s = rng.randint(60, 110)
            rev_s = rng.randint(300, 800)
            ack_ts = ev_ts + timedelta(seconds=ack_s)
            rev_ts = ev_ts + timedelta(seconds=rev_s)
            rev_by = "warden@sunrise.demo"
            rev_note = "Double door bounce / card scan lag."
            severity = "low"
        else:
            status = "new"
            ack_ts = None
            rev_ts = None
            rev_by = None
            rev_note = None
            severity = "high"

        if target_z == entry_zid:
            kind = "tailgating"
            modality = "access"
        else:
            kind = rng.choice(["student_sos", "restricted_access"])
            modality = "report" if kind == "student_sos" else "access"

        score = round(rng.uniform(0.80, 0.95), 2)

        inc = Incident(
            org_id=org_id,
            site_id=site_id,
            zone_id=target_z,
            severity=severity,
            composite_score=score,
            modalities=[modality],
            status=status,
            created_ts=ev_ts,
            updated_ts=rev_ts or ack_ts or ev_ts,
            acknowledged_by="guard_on_duty" if ack_ts else None,
            acknowledged_ts=ack_ts,
            reviewer=rev_by,
            reviewed_ts=rev_ts,
            review_note=rev_note,
            explanation=f"{kind.replace('_', ' ').title()} event recorded at {target_z}.",
            source="seed_history",
        )
        incidents_to_create.append(inc)

        sig = Signal(
            org_id=org_id,
            site_id=site_id,
            zone_id=target_z,
            ts=ev_ts,
            modality=modality,
            kind=kind,
            score=score,
            details={"type": "unsafe" if kind == "student_sos" else "card_swipe"},
            source="seed_history",
        )
        signals_to_create.append((inc, sig))

    # 4. Insert documents into MongoDB
    for inc, sig in signals_to_create:
        await inc.insert()
        sig.incident_id = str(inc.id)
        await sig.insert()
        inc.signal_ids = [str(sig.id)]
        await inc.save()

    print(f"Successfully seeded {len(incidents_to_create)} historical incidents & signals for '{org_name}'!")
    print(f"  - Terrace (Late Night): 28 incidents")
    print(f"  - Common Room (Evenings): 20 incidents")
    print(f"  - Entry / Corridor: 14 incidents")
    print(f"  - Confirmed: 38 | False Alarm: 15 | Pending/Investigating: 9")
    print(f"  - Timezone: {tz_str}")

    if close_when_done:
        await close_db()


if __name__ == "__main__":
    asyncio.run(seed_history(close_when_done=True))
