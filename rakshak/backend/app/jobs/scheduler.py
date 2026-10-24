"""
APScheduler background jobs for RakshakAI:
1. SLA escalation check (runs every 10 seconds):
   Finds high/critical incidents unacknowledged beyond sla_ack_seconds -> sets escalated=True
   and broadcasts incident.escalated to the tenant's WebSocket room.
2. Daily retention purge and token cleanup.
"""
import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.models.incident import Incident
from app.models.organization import Organization
from app.models.signal import utc_now
from app.privacy.retention import execute_retention_purge
from app.realtime.ws import ws_hub

logger = logging.getLogger("rakshakai.jobs")
scheduler = AsyncIOScheduler()


async def check_sla_escalations() -> None:
    """
    Check for high and critical incidents that exceed sla_ack_seconds without acknowledgement.
    """
    try:
        # Fetch all organizations to respect per-tenant sla_ack_seconds
        orgs = await Organization.find_all().to_list()
        now = utc_now()

        for org in orgs:
            sla_sec = float(org.settings.get("sla_ack_seconds", 120))
            cutoff = now - timedelta(seconds=sla_sec)

            unack_incidents = await Incident.find({
                "org_id": str(org.id),
                "severity": {"$in": ["high", "critical"]},
                "status": "new",
                "escalated": False,
                "created_ts": {"$lt": cutoff},
            }).to_list()

            for inc in unack_incidents:
                inc.escalated = True
                await inc.save()
                logger.warning(
                    f"SLA breached for incident {inc.id} in org '{org.name}' ({inc.severity}). Escalating!"
                )
                await ws_hub.broadcast_to_org(
                    org_id=str(org.id),
                    event_type="incident.escalated",
                    data={
                        "id": str(inc.id),
                        "severity": inc.severity,
                        "zone_id": inc.zone_id,
                        "created_ts": inc.created_ts.isoformat(),
                        "reason": f"Unacknowledged after {int(sla_sec)}s SLA timeout.",
                    },
                )
    except Exception as exc:
        logger.error(f"Error in SLA escalation job: {exc}")


async def daily_maintenance_job() -> None:
    """Run daily retention cleanup."""
    try:
        logger.info("Running daily maintenance and retention purge...")
        await execute_retention_purge(user="scheduler")
    except Exception as exc:
        logger.error(f"Error in maintenance job: {exc}")


def start_scheduler() -> None:
    """Start APScheduler jobs."""
    if not scheduler.running:
        scheduler.add_job(
            check_sla_escalations,
            "interval",
            seconds=10,
            id="sla_escalation_checker",
            replace_existing=True,
        )
        scheduler.add_job(
            daily_maintenance_job,
            "interval",
            hours=24,
            id="daily_retention_purge",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("APScheduler background jobs started successfully.")


def stop_scheduler() -> None:
    """Shut down scheduler cleanly."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
