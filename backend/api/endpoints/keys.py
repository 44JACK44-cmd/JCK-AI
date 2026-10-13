"""
API Keys management endpoints.
Store, list (masked), verify and delete provider API keys.
Keys are encrypted at rest and never returned in plaintext.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from adapters.base import ProviderStatus
from api.endpoints.providers import _provider_adapters
from config import settings
from services import keystore

router = APIRouter()

# Providers the user may register keys for (free-tier or user's own keys)
MANAGEABLE_PROVIDERS = {"deepseek", "google", "anthropic", "openai"}


class KeySaveRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=64)
    api_key: str = Field(min_length=8, max_length=512)


class KeyInfo(BaseModel):
    provider_id: str
    masked: str
    updated_at: Optional[str] = None
    env_fallback: bool = False


class KeyVerifyResponse(BaseModel):
    provider_id: str
    available: bool
    status: str
    message: str
    free_route: bool = False


@router.get("/", response_model=List[KeyInfo])
async def list_keys():
    """List stored keys with masked previews (full values never exposed)."""
    stored = keystore.list_stored_keys()
    # Also surface env-configured keys not in DB
    known = {k["provider_id"] for k in stored}
    for pid in MANAGEABLE_PROVIDERS:
        if pid not in known and _env_key(pid):
            stored.append({
                "provider_id": pid,
                "masked": keystore.mask_key(_env_key(pid)),
                "updated_at": None,
                "env_fallback": True,
            })
    return [KeyInfo(**k) for k in stored]


@router.post("/", response_model=KeyInfo)
async def save_key(request: KeySaveRequest):
    """Encrypt and store an API key for a provider."""
    if request.provider_id not in MANAGEABLE_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Proveedor '{request.provider_id}' no gestionable")
    row = keystore.store_api_key(request.provider_id, request.api_key)
    return KeyInfo(
        provider_id=row.provider_id,
        masked=keystore.mask_key(request.api_key),
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        env_fallback=False,
    )


@router.post("/{provider_id}/verify", response_model=KeyVerifyResponse)
async def verify_key(provider_id: str):
    """
    Verify the stored key against the real provider API.
    Performs a minimal real request (max_tokens=1) and classifies honestly.
    """
    if provider_id not in MANAGEABLE_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Proveedor '{provider_id}' no gestionable")
    adapter = _provider_adapters.get(provider_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Sin adaptador implementado")
    result = await adapter.test_connection()
    status = result.get("status", ProviderStatus.ERROR.value)
    # A route is only "free" if the provider genuinely verified a free tier
    free_route = bool(result.get("free_tier_available")) and status == ProviderStatus.FREE_AVAILABLE.value
    return KeyVerifyResponse(
        provider_id=provider_id,
        available=result.get("available", False),
        status=status,
        message=result.get("message", ""),
        free_route=free_route,
    )


@router.delete("/{provider_id}")
async def delete_key(provider_id: str):
    """Delete a stored key (falls back to env config if present)."""
    if provider_id not in MANAGEABLE_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Proveedor '{provider_id}' no gestionable")
    deleted = keystore.delete_api_key(provider_id)
    if not deleted and not _env_key(provider_id):
        raise HTTPException(status_code=404, detail="No hay clave almacenada")
    return {"deleted": provider_id, "env_fallback_remains": bool(_env_key(provider_id))}


def _env_key(provider_id: str) -> Optional[str]:
    return {
        "deepseek": settings.deepseek_api_key,
        "google": settings.google_api_key,
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
    }.get(provider_id)
