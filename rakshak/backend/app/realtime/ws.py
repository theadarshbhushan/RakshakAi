"""
Multi-tenant WebSocket Hub for RakshakAI.
Maintains separate connection rooms per tenant organization (org_id).
Guarantees that alerts and real-time events never leak across organizations.
"""
import logging
from typing import Any, Dict, List

from fastapi import WebSocket

logger = logging.getLogger("rakshakai.realtime.ws")


class TenantWebSocketHub:
    def __init__(self) -> None:
        # org_id -> List of active WebSocket connections
        self.rooms: Dict[str, List[WebSocket]] = {}

    async def connect(self, org_id: str, websocket: WebSocket) -> None:
        """Accept connection and add to tenant-specific room."""
        await websocket.accept()
        if org_id not in self.rooms:
            self.rooms[org_id] = []
        self.rooms[org_id].append(websocket)
        logger.info(f"WebSocket client connected to org '{org_id}'. Total in org: {len(self.rooms[org_id])}")

    def disconnect(self, org_id: str, websocket: WebSocket) -> None:
        """Remove connection from tenant room."""
        if org_id in self.rooms and websocket in self.rooms[org_id]:
            self.rooms[org_id].remove(websocket)
            if not self.rooms[org_id]:
                del self.rooms[org_id]
            logger.info(f"WebSocket client disconnected from org '{org_id}'.")

    async def broadcast_to_org(self, org_id: str, event_type: str, data: Dict[str, Any]) -> None:
        """
        Broadcast real-time event ONLY to subscribers within the specified organization room.
        Events: incident.created, incident.updated, incident.escalated, signal.created
        """
        connections = self.rooms.get(org_id, [])
        if not connections:
            return

        payload = {
            "event": event_type,
            "org_id": org_id,
            "data": data,
        }

        dead_sockets: List[WebSocket] = []
        for ws in list(connections):
            try:
                await ws.send_json(payload)
            except Exception as exc:
                logger.warning(f"Failed to send to client in org '{org_id}': {exc}")
                dead_sockets.append(ws)

        for dead in dead_sockets:
            self.disconnect(org_id, dead)


ws_hub = TenantWebSocketHub()
