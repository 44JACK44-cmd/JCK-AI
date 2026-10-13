"""
Device pairing endpoints — secure linking between Android and Windows agent.
Pairing codes are short-lived; device tokens are hashed before storage.
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from core.security import create_access_token, decode_access_token
from database.models import Device
from database.session import get_db

router = APIRouter()

# In-memory pairing codes (short-lived, single use)
_pending_pairs: dict = {}


class PairStartRequest(BaseModel):
    device_name: str = Field(min_length=1, max_length=128)
    platform: str = Field(default="android")


class PairConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class DeviceResponse(BaseModel):
    id: int
    name: str
    is_revoked: bool
    last_seen: Optional[str]
    created_at: str


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/pair/start")
async def start_pairing(request: PairStartRequest, db: Session = Depends(get_db)):
    """User-initiated pairing: generates a short-lived code shown on the PC."""
    if not settings.device_pairing_enabled:
        raise HTTPException(status_code=403, detail="Device pairing is disabled")
    active = db.execute(select(Device).where(Device.is_revoked == False)).scalars().all()
    if len(active) >= settings.device_pairing_max_devices:
        raise HTTPException(status_code=429, detail="Maximum paired devices reached")

    code = f"{secrets.randbelow(10**6):06d}"
    _pending_pairs[code] = {
        "device_name": request.device_name,
        "platform": request.platform,
        "expires": datetime.utcnow() + timedelta(minutes=settings.device_pairing_timeout_minutes),
    }
    return {
        "code": code,
        "expires_in_minutes": settings.device_pairing_timeout_minutes,
        "message": "Introduce este código en la aplicación de Windows para completar el emparejamiento",
    }


@router.post("/pair/confirm")
async def confirm_pairing(request: PairConfirmRequest, db: Session = Depends(get_db)):
    """Confirm a pairing code and issue a scoped device token."""
    entry = _pending_pairs.get(request.code)
    if not entry:
        raise HTTPException(status_code=404, detail="Invalid pairing code")
    if datetime.utcnow() > entry["expires"]:
        _pending_pairs.pop(request.code, None)
        raise HTTPException(status_code=410, detail="Pairing code expired")

    _pending_pairs.pop(request.code, None)
    token = create_access_token(
        subject=f"device:{entry['device_name']}",
        extra_claims={"kind": "device", "scope": ["tasks:read", "tasks:cancel", "status:read"]},
    )
    device = Device(
        name=entry["device_name"],
        token_hash=_hash_token(token),
        scope=["tasks:read", "tasks:cancel", "status:read"],
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return {
        "device_id": device.id,
        "device_name": device.name,
        "token": token,
        "scope": device.scope,
        "message": "Dispositivo vinculado. Guarda el token de forma segura.",
    }


@router.get("/", response_model=List[DeviceResponse])
async def list_devices(db: Session = Depends(get_db)):
    devices = db.execute(select(Device).order_by(Device.created_at.desc())).scalars().all()
    return [
        DeviceResponse(
            id=d.id,
            name=d.name,
            is_revoked=d.is_revoked,
            last_seen=d.last_seen.isoformat() if d.last_seen else None,
            created_at=d.created_at.isoformat() if d.created_at else None,
        )
        for d in devices
    ]


@router.delete("/{device_id}")
async def revoke_device(device_id: int, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.is_revoked = True
    device.token_hash = ""
    db.commit()
    return {"revoked": device_id}


async def authenticate_device(token: str, db: Session) -> Optional[Device]:
    payload = decode_access_token(token)
    if not payload or payload.get("kind") != "device":
        return None
    device_hash = _hash_token(token)
    device = db.execute(select(Device).where(Device.token_hash == device_hash)).scalar_one_or_none()
    if not device or device.is_revoked:
        return None
    device.last_seen = datetime.utcnow()
    db.commit()
    return device
