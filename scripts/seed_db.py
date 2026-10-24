"""
Database seeding script for RakshakAI multi-tenant platform.
Performs idempotent upserts to initialize:
1. Organization 'Sunrise Residency' (plan: pro) with Site 'Block B Hostel',
   default rules, zones, cameras, and demo users (owner, admin, warden, guard, auditor).
2. Second organization 'Green Valley Hostel' (plan: free) with owner user,
   used to verify strict tenant isolation.
3. Initializes all MongoDB collections and compound + TTL indexes.
4. Prints the demo credentials table.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
import yaml

# Add backend directory to python path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.mongo import init_db, close_db
from app.models.organization import Organization, Site
from app.models.user import User
from app.models.zone import Zone, Camera
from app.models.rules import RuleDocument
from app.repositories.repos import AuditRepository


async def seed(close_when_done: bool = False) -> None:
    print(f"Connecting to database [ENV={settings.ENV}, USE_MOCK_DB={settings.USE_MOCK_DB}]...")
    await init_db()

    # Load default rules
    rules_data = {}
    if settings.RULES_DEFAULT_PATH.exists():
        with open(settings.RULES_DEFAULT_PATH, "r", encoding="utf-8") as rf:
            rules_data = yaml.safe_load(rf) or {}

    # =========================================================================
    # 1. Tenant: Sunrise Residency (Pro Plan)
    # =========================================================================
    print("\n--- Seeding Organization: Sunrise Residency ---")
    org1 = await Organization.find_one(Organization.slug == "sunrise")
    if not org1:
        org1 = Organization(
            name="Sunrise Residency",
            slug="sunrise",
            plan="pro",
            settings={
                "retention_days": 30,
                "fusion_window_s": 30,
                "sla_ack_seconds": 120,
                "context_ratio": 0.8,
                "timezone": "Asia/Kolkata",
            },
        )
        await org1.insert()
        print(f"Created organization: {org1.name} (id: {org1.id})")
    else:
        print(f"Organization '{org1.name}' already exists.")

    org1_id = str(org1.id)

    # Site 1
    site1 = await Site.find_one({"org_id": org1_id, "name": "Block B Hostel"})
    if not site1:
        site1 = Site(
            org_id=org1_id,
            name="Block B Hostel",
            address="North Campus, Gate 4",
            timezone="Asia/Kolkata",
        )
        await site1.insert()
        print(f"Created site: {site1.name}")

    site1_id = str(site1.id)

    # Rules for Sunrise
    rule1 = await RuleDocument.find_one({"org_id": org1_id, "is_active": True})
    if not rule1:
        rule1 = RuleDocument(
            org_id=org1_id,
            version=1,
            curfew=rules_data.get("curfew", {}),
            zones=rules_data.get("zones", {}),
            tailgating=rules_data.get("tailgating", {}),
            fusion=rules_data.get("fusion", {}),
            weights=rules_data.get("weights", {}),
            updated_by="seed_script",
        )
        await rule1.insert()
        print("Created default rules document for Sunrise.")

    # Zones for Sunrise
    for zid, zconf in rules_data.get("zones", {}).items():
        existing_zone = await Zone.find_one({"org_id": org1_id, "zone_id": zid})
        if not existing_zone:
            zone = Zone(
                org_id=org1_id,
                site_id=site1_id,
                zone_id=zid,
                name=zconf.get("name", zid.replace("_", " ").title()),
                type=zconf.get("type", "common"),
                allowed_roles=zconf.get("allowed_roles", []),
                adjacent_zone_ids=zconf.get("adjacent_zone_ids", []),
            )
            await zone.insert()
            print(f"Created zone: {zone.name} ({zone.zone_id})")
        else:
            raw_doc = await Zone.get_motor_collection().find_one({"_id": existing_zone.id})
            if not raw_doc or "sos_token" not in raw_doc or not raw_doc.get("sos_token"):
                await existing_zone.save()
                print(f"Persisted sos_token for zone: {existing_zone.name}")

    # Cameras for Sunrise
    for cconf in rules_data.get("cameras", []):
        existing_cam = await Camera.find_one({"org_id": org1_id, "camera_id": cconf["camera_id"]})
        if not existing_cam:
            cam = Camera(
                org_id=org1_id,
                site_id=site1_id,
                camera_id=cconf["camera_id"],
                name=cconf["name"],
                zone_id=cconf["zone_id"],
                source_path=cconf["source_path"],
                door_line=cconf.get("door_line"),
            )
            await cam.insert()
            print(f"Created camera: {cam.name} ({cam.camera_id})")

    # Users for Sunrise
    sunrise_users = [
        ("owner@sunrise.demo", "Owner@12345", "owner", "Chief Warden / Owner"),
        ("admin@sunrise.demo", "Admin@12345", "admin", "System Administrator"),
        ("warden@sunrise.demo", "Warden@12345", "warden", "Hostel Block Warden"),
        ("guard@sunrise.demo", "Guard@12345", "guard", "Turnstile Security Guard"),
        ("auditor@sunrise.demo", "Auditor@12345", "auditor", "Compliance Officer / Auditor"),
    ]

    audit_repo1 = AuditRepository(org1_id)
    for email, pw, role, full_name in sunrise_users:
        u = await User.find_one(User.email == email)
        if not u:
            u = User(
                org_id=org1_id,
                email=email,
                full_name=full_name,
                password_hash=get_password_hash(pw),
                role=role,
                is_active=True,
                token_version=1,
            )
            await u.insert()
            print(f"Created user: {u.email} ({u.role})")
            await audit_repo1.record_audit(
                actor={"type": "system", "id": "seed", "email": "seed_script"},
                action="user.seeded",
                target=f"user:{u.id}",
                reason=f"Seeded demo account for {email}",
            )
        else:
            print(f"User '{email}' already exists.")

    # =========================================================================
    # 2. Tenant: Green Valley Hostel (Free Plan) - for Tenant Isolation Demo
    # =========================================================================
    print("\n--- Seeding Organization: Green Valley Hostel (Isolation Demo) ---")
    org2 = await Organization.find_one(Organization.slug == "greenvalley")
    if not org2:
        org2 = Organization(
            name="Green Valley Hostel",
            slug="greenvalley",
            plan="free",
            settings={
                "retention_days": 7,
                "fusion_window_s": 30,
                "sla_ack_seconds": 120,
                "context_ratio": 0.8,
                "timezone": "Asia/Kolkata",
            },
        )
        await org2.insert()
        print(f"Created organization: {org2.name} (id: {org2.id})")

    org2_id = str(org2.id)

    # Green Valley Owner
    gv_owner_email = "owner@greenvalley.demo"
    gv_owner = await User.find_one(User.email == gv_owner_email)
    if not gv_owner:
        gv_owner = User(
            org_id=org2_id,
            email=gv_owner_email,
            full_name="Green Valley Owner",
            password_hash=get_password_hash("Owner@12345"),
            role="owner",
            is_active=True,
            token_version=1,
        )
        await gv_owner.insert()
        print(f"Created user: {gv_owner.email} ({gv_owner.role})")
        audit_repo2 = AuditRepository(org2_id)
        await audit_repo2.record_audit(
            actor={"type": "system", "id": "seed", "email": "seed_script"},
            action="user.seeded",
            target=f"user:{gv_owner.id}",
            reason=f"Seeded demo account for {gv_owner.email}",
        )

    # Print Credentials Table
    print("\n" + "=" * 80)
    print("                    RAKSHAKAI DEMO CREDENTIALS TABLE                   ")
    print("=" * 80)
    print(f"{'Organization':<22} | {'Email':<25} | {'Password':<14} | {'Role':<10}")
    print("-" * 80)
    for email, pw, role, _ in sunrise_users:
        print(f"{'Sunrise Residency':<22} | {email:<25} | {pw:<14} | {role:<10}")
    print(f"{'Green Valley Hostel':<22} | {'owner@greenvalley.demo':<25} | {'Owner@12345':<14} | {'owner':<10}")
    print("=" * 80)
    print("API Documentation: http://localhost:8000/docs")
    print("Health Status:     http://localhost:8000/api/v1/health")
    print("=" * 80 + "\n")

    if close_when_done:
        await close_db()


if __name__ == "__main__":
    asyncio.run(seed(close_when_done=True))
