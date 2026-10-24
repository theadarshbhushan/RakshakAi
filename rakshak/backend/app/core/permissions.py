"""
Central Role-Based Access Control (RBAC) permission matrix.
Defines granular permissions and role assignments for multi-tenant organizations.
"""
from typing import Dict, List, Set

ROLES = ["owner", "admin", "warden", "guard", "auditor"]

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "owner": {
        "incidents:read", "incidents:ack", "incidents:review", "incidents:escalations",
        "evidence:breakglass", "evidence:read_public", "evidence:read_restricted",
        "signals:read", "signals:write",
        "rules:read", "rules:write",
        "zones:read", "zones:write", "cameras:read", "cameras:write", "sites:read", "sites:write",
        "users:read", "users:manage", "invitations:manage", "api_keys:manage",
        "org:manage", "billing:manage",
        "audit:read", "privacy:manage", "scenarios:run",
        "calibration:read", "calibration:revert",
    },
    "admin": {
        "incidents:read", "incidents:ack", "incidents:review", "incidents:escalations",
        "evidence:breakglass", "evidence:read_public", "evidence:read_restricted",
        "signals:read", "signals:write",
        "rules:read", "rules:write",
        "zones:read", "zones:write", "cameras:read", "cameras:write", "sites:read", "sites:write",
        "users:read", "users:manage", "invitations:manage", "api_keys:manage",
        "audit:read", "privacy:manage", "scenarios:run",
        "calibration:read", "calibration:revert",
    },
    "warden": {
        "incidents:read", "incidents:ack", "incidents:review", "incidents:escalations",
        "evidence:read_public", "signals:read",
        "rules:read", "zones:read", "cameras:read", "sites:read", "users:read",
        "scenarios:run", "calibration:read", "calibration:revert",
    },
    "guard": {
        "incidents:read", "incidents:ack", "incidents:review",
        "evidence:read_public", "signals:read",
        "rules:read", "zones:read", "cameras:read", "sites:read",
        "calibration:read",
    },
    "auditor": {
        "incidents:read", "evidence:read_public", "signals:read",
        "rules:read", "zones:read", "cameras:read", "sites:read",
        "audit:read",
    },
}


def get_permissions_for_role(role: str) -> List[str]:
    """Retrieve full list of granted permissions for a given role."""
    return sorted(list(ROLE_PERMISSIONS.get(role, set())))


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has the specified permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())
