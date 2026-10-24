"""
Script to generate synthetic hostel access control logs in CSV format.
Includes normal evening footfall, curfew violations, restricted zone breach attempts,
and swipes timed to pair with tailgating scenarios.
Calculates salted SHA-256 pseudonymized IDs (raw card IDs are stored ONLY in this CSV source).
"""
import csv
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import sys

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.core.config import settings

OUTPUT_DIR = settings.ACCESS_LOGS_DIR
OUTPUT_FILE = OUTPUT_DIR / "access_logs.csv"


def generate_pseudo_id(card_id: str, salt: str) -> str:
    combined = f"{salt}:{card_id}".encode("utf-8")
    return hashlib.sha256(combined).hexdigest()[:8]


def generate_logs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    salt = settings.PSEUDONYM_SALT

    # Base date: today at 18:00 UTC
    base_time = datetime.now(timezone.utc).replace(hour=18, minute=0, second=0, microsecond=0)
    rows = []

    # 1. Normal evening traffic (18:00 - 22:45)
    normal_users = [
        ("CARD_RES_001", "resident", "door_block_b", "block_b_entry", "in", "granted"),
        ("CARD_RES_002", "resident", "door_common_room", "common_room", "in", "granted"),
        ("CARD_RES_003", "resident", "door_block_b", "block_b_entry", "out", "granted"),
        ("CARD_WAR_001", "warden", "door_terrace", "terrace", "in", "granted"),
        ("CARD_RES_004", "resident", "door_block_b", "block_b_entry", "in", "granted"),
        ("CARD_RES_005", "resident", "door_common_room", "common_room", "out", "granted"),
        ("CARD_ADM_001", "admin", "door_server_room", "server_room", "in", "granted"),
    ]

    current_t = base_time
    for card_id, role, door_id, zone_id, direction, result in normal_users:
        current_t += timedelta(minutes=15)
        pseudo = generate_pseudo_id(card_id, salt)
        rows.append({
            "ts": current_t.isoformat(),
            "card_id": card_id,
            "pseudo_id": pseudo,
            "role": role,
            "door_id": door_id,
            "zone_id": zone_id,
            "direction": direction,
            "result": result,
        })

    # 2. Tailgating pair swipe (at 21:15:05)
    tailgate_t = base_time.replace(hour=21, minute=15, second=5)
    rows.append({
        "ts": tailgate_t.isoformat(),
        "card_id": "CARD_RES_010",
        "pseudo_id": generate_pseudo_id("CARD_RES_010", salt),
        "role": "resident",
        "door_id": "door_block_b",
        "zone_id": "block_b_entry",
        "direction": "in",
        "result": "granted",
    })

    # 3. Restricted zone unauthorized access attempts by residents (should be denied)
    # Attempt 1: Resident trying to access Terrace at 22:15
    rz_t1 = base_time.replace(hour=22, minute=15, second=20)
    rows.append({
        "ts": rz_t1.isoformat(),
        "card_id": "CARD_RES_011",
        "pseudo_id": generate_pseudo_id("CARD_RES_011", salt),
        "role": "resident",
        "door_id": "door_terrace",
        "zone_id": "terrace",
        "direction": "in",
        "result": "denied",
    })

    # Attempt 2: Resident trying to access Server Room at 22:45
    rz_t2 = base_time.replace(hour=22, minute=45, second=10)
    rows.append({
        "ts": rz_t2.isoformat(),
        "card_id": "CARD_RES_012",
        "pseudo_id": generate_pseudo_id("CARD_RES_012", salt),
        "role": "resident",
        "door_id": "door_server_room",
        "zone_id": "server_room",
        "direction": "in",
        "result": "denied",
    })

    # 4. Curfew Violations (after 23:00)
    # Curfew 1: Resident swipe at 23:15
    curf_t1 = base_time.replace(hour=23, minute=15, second=0)
    rows.append({
        "ts": curf_t1.isoformat(),
        "card_id": "CARD_RES_020",
        "pseudo_id": generate_pseudo_id("CARD_RES_020", salt),
        "role": "resident",
        "door_id": "door_block_b",
        "zone_id": "block_b_entry",
        "direction": "in",
        "result": "granted",
    })

    # Curfew 2: Resident swipe paired with Scenario 1 (Terrace intrusion) at 23:38:05
    curf_t2 = base_time.replace(hour=23, minute=38, second=5)
    rows.append({
        "ts": curf_t2.isoformat(),
        "card_id": "CARD_RES_021",
        "pseudo_id": "a91f02c3",  # matching Scenario 1
        "role": "resident",
        "door_id": "door_block_b",
        "zone_id": "block_b_entry",
        "direction": "in",
        "result": "granted",
    })

    # Curfew 3: Resident swipe at 01:20
    next_day = base_time + timedelta(days=1)
    curf_t3 = next_day.replace(hour=1, minute=20, second=30)
    rows.append({
        "ts": curf_t3.isoformat(),
        "card_id": "CARD_RES_022",
        "pseudo_id": generate_pseudo_id("CARD_RES_022", salt),
        "role": "resident",
        "door_id": "door_block_b",
        "zone_id": "block_b_entry",
        "direction": "in",
        "result": "granted",
    })

    # Write CSV
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as cf:
        fieldnames = ["ts", "card_id", "pseudo_id", "role", "door_id", "zone_id", "direction", "result"]
        writer = csv.DictWriter(cf, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Successfully generated {len(rows)} access log records into: {OUTPUT_FILE}")


if __name__ == "__main__":
    generate_logs()
