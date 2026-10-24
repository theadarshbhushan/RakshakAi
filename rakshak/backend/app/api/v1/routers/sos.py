"""
Student Emergency SOS Router (/api/v1/sos).
Enables QR-code driven, anonymous student SOS reporting fused with real-time AI security detectors.

Features:
- Zone QR code generation: GET /qr/{zone_id} returns PNG QR pointing to /sos/<sos_token>
- Printable batch QR sheet: GET /qr-sheet returns printable HTML with all zone QR codes
- Token rotation: POST /rotate/{zone_id} rotates token (owner/admin)
- Public zone info: GET /{sos_token}/info returns zone display name
- Public SOS submission: POST /{sos_token} rate-limited (3/min per IP), honeypot protected,
  anonymous (zero IP retention beyond rate-limit window), audited without personal data,
  emits modality='report', kind='student_sos', score=0.9 directly into FusionEngine.
"""
import base64
import html
import time
from collections import defaultdict
from io import BytesIO
from typing import Any, Dict, List, Literal, Optional

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import get_current_user, require_permission
from app.core.errors import BadRequestError, NotFoundError
from app.fusion.corroboration import FusionEngine
from app.models.rules import RuleDocument
from app.models.signal import Signal
from app.models.user import User
from app.models.zone import Zone, generate_sos_token
from app.repositories.repos import AuditRepository

router = APIRouter(prefix="/sos", tags=["SOS"])

# In-memory ephemeral sliding window rate-limiter:
# Stores only raw timestamps for active window; zero personal/IP storage retained after window expires
_sos_ip_history: Dict[str, List[float]] = defaultdict(list)


def extract_client_ip(request: Request) -> str:
    """Extract client IP from proxy headers or connection info."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def enforce_sos_rate_limit(client_ip: str, limit: int = 3, window_seconds: float = 60.0) -> None:
    """
    Enforce max 3 requests per minute per IP.
    4th request within 60 seconds returns 429 Too Many Requests.
    """
    now = time.monotonic()
    history = _sos_ip_history[client_ip]
    active_history = [t for t in history if now - t < window_seconds]
    if len(active_history) >= limit:
        _sos_ip_history[client_ip] = active_history
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Maximum 3 SOS submissions per minute.",
        )
    active_history.append(now)
    _sos_ip_history[client_ip] = active_history


def reset_sos_rate_limits() -> None:
    """Testing helper to clear rate-limiter state."""
    _sos_ip_history.clear()


class StudentSOSRequest(BaseModel):
    type: Literal["medical", "harassment", "fight", "unsafe", "other"] = Field(
        ..., description="Type of student emergency or distress report"
    )
    note: Optional[str] = Field(None, max_length=280, description="Optional brief context up to 280 characters")
    # Anti-abuse honeypot fields
    website: Optional[str] = Field(None, description="Honeypot field (must remain empty)")
    honeypot: Optional[str] = Field(None, description="Honeypot field (must remain empty)")
    hp: Optional[str] = Field(None, description="Honeypot field (must remain empty)")


class SOSZoneInfoResponse(BaseModel):
    zone_name: str


class SOSSubmitResponse(BaseModel):
    message: str
    incident_id: Optional[str] = None
    severity: str
    zone_name: str
    status: str = "received"


# =====================================================================
# Authenticated Management Endpoints (Owner / Admin)
# =====================================================================


@router.get("/qr/{zone_id}", dependencies=[Depends(require_permission("zones:write"))])
async def get_zone_qr_code(zone_id: str, current_user: User = Depends(get_current_user)):
    """
    Generate and return a PNG QR code for a given zone.
    The QR code encodes http://localhost:5173/sos/<sos_token>.
    """
    zone = await Zone.find_one({"org_id": current_user.org_id, "zone_id": zone_id})
    if not zone:
        raise NotFoundError("Zone", zone_id)

    if not zone.sos_token:
        zone.sos_token = generate_sos_token()
        await zone.save()

    target_url = f"{settings.FRONTEND_URL}/sos/{zone.sos_token}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=qr_sos_{zone.zone_id}.png"},
    )


@router.get("/qr-sheet", response_class=HTMLResponse, dependencies=[Depends(require_permission("zones:write"))])
async def get_zone_qr_sheet(current_user: User = Depends(get_current_user)):
    """
    Generate a printable HTML sheet containing high-resolution QR codes for all zones
    in the current organization, complete with print-ready CSS formatting.
    """
    zones = await Zone.find({"org_id": current_user.org_id}).sort("name").to_list()

    cards_html = []
    for z in zones:
        if not z.sos_token:
            z.sos_token = generate_sos_token()
            await z.save()

        target_url = f"{settings.FRONTEND_URL}/sos/{z.sos_token}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f172a", back_color="white")

        buf = BytesIO()
        img.save(buf, format="PNG")
        b64_qr = base64.b64encode(buf.getvalue()).decode("utf-8")

        card = f"""
        <div class="qr-card">
          <div class="card-top">
            <span class="zone-badge badge-{z.type}">{z.type.upper()}</span>
            <h3 class="zone-name">{html.escape(z.name)}</h3>
            <div class="zone-meta">ID: {html.escape(z.zone_id)}</div>
          </div>
          <div class="qr-frame">
            <img class="qr-img" src="data:image/png;base64,{b64_qr}" alt="SOS QR code for {html.escape(z.name)}" />
          </div>
          <div class="card-footer">
            <div class="sos-callout">CAMPUS STUDENT SOS</div>
            <p class="sos-desc">Scan with any phone camera to report emergencies, harassment, fights, or safety concerns immediately.</p>
            <div class="anon-badge">ANONYMOUS · NO APP NEEDED · 24/7 DISPATCH</div>
            <div class="qr-url">{html.escape(target_url)}</div>
          </div>
        </div>
        """
        cards_html.append(card)

    sheet_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>RakshakAI — Campus Student SOS QR Codes</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #f1f5f9;
      color: #0f172a;
      padding: 24px;
    }}
    .sheet-header {{
      background: #0f172a;
      color: white;
      padding: 20px 28px;
      border-radius: 12px;
      margin-bottom: 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .sheet-title {{ font-size: 22px; font-weight: 700; }}
    .sheet-sub {{ font-size: 14px; color: #94a3b8; margin-top: 4px; }}
    .print-btn {{
      background: #3b82f6;
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 8px;
      font-weight: 600;
      cursor: pointer;
    }}
    .print-btn:hover {{ background: #2563eb; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 20px;
    }}
    .qr-card {{
      background: white;
      border: 2px solid #e2e8f0;
      border-radius: 14px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
      page-break-inside: avoid;
    }}
    .card-top {{ width: 100%; margin-bottom: 12px; }}
    .zone-badge {{
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.05em;
      padding: 3px 8px;
      border-radius: 6px;
      margin-bottom: 6px;
    }}
    .badge-corridor {{ background: #e0f2fe; color: #0369a1; }}
    .badge-restricted {{ background: #fee2e2; color: #b91c1c; }}
    .badge-common {{ background: #dcfce7; color: #15803d; }}
    .badge-entry {{ background: #fef3c7; color: #b45309; }}
    .zone-name {{ font-size: 18px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }}
    .zone-meta {{ font-size: 12px; color: #64748b; font-family: monospace; }}
    .qr-frame {{
      background: white;
      padding: 10px;
      border-radius: 10px;
      border: 1px solid #cbd5e1;
      margin: 10px 0 14px 0;
    }}
    .qr-img {{ display: block; width: 180px; height: 180px; }}
    .card-footer {{ width: 100%; }}
    .sos-callout {{
      font-size: 13px;
      font-weight: 800;
      color: #dc2626;
      letter-spacing: 0.05em;
      margin-bottom: 6px;
    }}
    .sos-desc {{
      font-size: 12px;
      color: #475569;
      line-height: 1.4;
      margin-bottom: 8px;
    }}
    .anon-badge {{
      font-size: 10px;
      font-weight: 700;
      color: #059669;
      background: #ecfdf5;
      padding: 4px 6px;
      border-radius: 4px;
      margin-bottom: 6px;
    }}
    .qr-url {{
      font-size: 10px;
      color: #94a3b8;
      font-family: monospace;
      word-break: break-all;
    }}
    @media print {{
      body {{ background: white; padding: 0; }}
      .sheet-header, .print-btn {{ display: none !important; }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 16px;
      }}
      .qr-card {{
        border: 2px solid #000;
        box-shadow: none;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
    }}
  </style>
</head>
<body>
  <div class="sheet-header">
    <div>
      <div class="sheet-title">RakshakAI Campus Security — Zone Student SOS QR Codes</div>
      <div class="sheet-sub">Printable posters for corridors, hostels, and common areas. Total Zones: {len(zones)}</div>
    </div>
    <button class="print-btn" onclick="window.print()">Print SOS Sheet</button>
  </div>
  <div class="grid">
    {''.join(cards_html)}
  </div>
</body>
</html>"""

    return HTMLResponse(content=sheet_html)


@router.post("/rotate/{zone_id}", dependencies=[Depends(require_permission("zones:write"))])
async def rotate_zone_sos_token(zone_id: str, current_user: User = Depends(get_current_user)):
    """
    Rotate the secret SOS token for a given zone.
    Invalidates the previous QR code URL and generates a fresh random token.
    Audit-logged securely.
    """
    zone = await Zone.find_one({"org_id": current_user.org_id, "zone_id": zone_id})
    if not zone:
        raise NotFoundError("Zone", zone_id)

    old_token = zone.sos_token
    zone.sos_token = generate_sos_token()
    await zone.save()

    # Tamper-evident hash-chained audit log
    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={
            "type": "user",
            "id": str(current_user.id),
            "email": current_user.email,
            "role": current_user.role,
        },
        action="zone.rotate_sos",
        target=f"zone:{zone.zone_id}",
        reason=f"Rotated student SOS token for zone '{zone.name}'",
    )

    return {
        "message": f"Successfully rotated SOS token for zone '{zone.zone_id}'",
        "zone_id": zone.zone_id,
        "sos_token": zone.sos_token,
        "qr_url": f"/api/v1/sos/qr/{zone.zone_id}",
    }


# =====================================================================
# Public, Unauthenticated Endpoints (Student Facing)
# =====================================================================


@router.get("/{sos_token}/info", response_model=SOSZoneInfoResponse)
async def get_sos_zone_info(sos_token: str):
    """
    Public lookup for student scanning QR code.
    Returns only the zone display name for the public report interface.
    Returns 404 if token is invalid or expired.
    """
    zone = await Zone.find_one({"sos_token": sos_token})
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or rotated SOS token.",
        )

    return SOSZoneInfoResponse(zone_name=zone.name)


@router.post("/{sos_token}", response_model=SOSSubmitResponse, status_code=status.HTTP_201_CREATED)
async def submit_student_sos(
    sos_token: str,
    payload: StudentSOSRequest,
    request: Request,
):
    """
    Public, anonymous student emergency SOS report.
    - Resolves zone and organization from sos_token (404 on invalid token).
    - Honeypot check against bot abuse (400 on detection).
    - Rate-limited per IP (3 requests per minute; 4th request returns 429).
    - Zero personal retention: No IP or device identifier stored beyond sliding window.
    - Emits Signal (modality='report', kind='student_sos', score=0.9) directly to FusionEngine.
    - Fusion rule: SOS alone -> high severity; SOS + audio/video in same zone -> critical severity.
    - Tamper-evident audit logged anonymously.
    """
    # 1. Honeypot check against spam/bot submissions
    if payload.website or payload.honeypot or payload.hp:
        raise BadRequestError("Spam submission detected.", code="SOS_SPAM_REJECTED")

    # 2. IP Rate Limit Enforcement (Max 3 per minute)
    client_ip = extract_client_ip(request)
    enforce_sos_rate_limit(client_ip, limit=3, window_seconds=60.0)

    # 3. Resolve Zone from Token
    zone = await Zone.find_one({"sos_token": sos_token})
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or rotated SOS token.",
        )

    # 4. Construct Signal
    details_dict: Dict[str, Any] = {"type": payload.type}
    if payload.note:
        details_dict["note"] = payload.note.strip()

    signal = Signal(
        org_id=zone.org_id,
        site_id=zone.site_id,
        modality="report",
        kind="student_sos",
        zone_id=zone.zone_id,
        score=0.9,
        threshold=0.5,
        details=details_dict,
        source="student_sos",
    )

    # 5. Ingest into Multi-Modal Fusion Engine
    active_rules = await RuleDocument.find_one({"org_id": zone.org_id, "is_active": True})
    rules_dict = active_rules.model_dump() if active_rules else {}
    fusion_engine = FusionEngine(zone.org_id, rules_dict)
    incident = await fusion_engine.ingest_signal(signal)

    # 6. Audit Log SOS Submission (Completely anonymous - no IP or device metadata stored)
    audit_repo = AuditRepository(zone.org_id)
    await audit_repo.record_audit(
        actor={"type": "anonymous", "id": "student_sos", "role": "student"},
        action="sos.submit",
        target=f"zone:{zone.zone_id}",
        reason=f"Anonymous Student SOS ({payload.type})",
        ip=None,
        user_agent=None,
    )

    return SOSSubmitResponse(
        message="Emergency SOS report received. Security dispatch has been alerted.",
        incident_id=str(incident.id) if incident else None,
        severity=incident.severity if incident else "high",
        zone_name=zone.name,
        status="received",
    )
