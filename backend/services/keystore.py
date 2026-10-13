"""
Encrypted API key storage (Level 0 secret handling).

Keys are encrypted at rest with Fernet (AES-128-CBC + HMAC) using a key
derived from JWT_SECRET_KEY. They are never returned in plaintext through
the API — only masked previews are exposed. Adapters fetch keys at call time
via get_api_key().
"""
import base64
import hashlib
import logging
from datetime import datetime
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database.models import APIKey
from database.session import SessionLocal

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    """Derive a stable Fernet key from the master secret."""
    digest = hashlib.sha256(settings.jwt_secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def mask_key(key: str) -> str:
    """Return a safe preview: first 4 + last 4 chars, never the full key."""
    if not key or len(key) < 12:
        return "****"
    return f"{key[:4]}…{key[-4:]}"


def store_api_key(provider_id: str, api_key: str, db: Optional[Session] = None) -> APIKey:
    """Encrypt and persist (or update) an API key for a provider."""
    owned = db is None
    if owned:
        db = SessionLocal()
    try:
        encrypted = _fernet().encrypt(api_key.encode("utf-8")).decode("utf-8")
        row = db.execute(select(APIKey).where(APIKey.provider_id == provider_id)).scalar_one_or_none()
        if row:
            row.encrypted_key = encrypted
            row.updated_at = datetime.utcnow()
        else:
            row = APIKey(provider_id=provider_id, encrypted_key=encrypted)
            db.add(row)
        db.commit()
        db.refresh(row)
        # Sync in-process adapter instances that cache keys at startup
        _sync_adapter_key(provider_id, api_key)
        return row
    finally:
        if owned:
            db.close()


def get_api_key(provider_id: str) -> Optional[str]:
    """
    Decrypt the stored API key for a provider.
    Falls back to environment configuration when no key is stored in DB.
    """
    db = SessionLocal()
    try:
        row = db.execute(select(APIKey).where(APIKey.provider_id == provider_id)).scalar_one_or_none()
        if row and row.encrypted_key:
            try:
                return _fernet().decrypt(row.encrypted_key.encode("utf-8")).decode("utf-8")
            except InvalidToken:
                logger.error(f"Cannot decrypt stored key for {provider_id}; master secret may have changed")
                return None
    finally:
        db.close()
    # Environment fallback
    env_map = {
        "deepseek": settings.deepseek_api_key,
        "google": settings.google_api_key,
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
    }
    return env_map.get(provider_id)


def delete_api_key(provider_id: str) -> bool:
    db = SessionLocal()
    try:
        row = db.execute(select(APIKey).where(APIKey.provider_id == provider_id)).scalar_one_or_none()
        if not row:
            return False
        db.delete(row)
        db.commit()
        _sync_adapter_key(provider_id, None)
        return True
    finally:
        db.close()


def list_stored_keys(db: Optional[Session] = None) -> list:
    """List stored keys with masked previews (never full values)."""
    owned = db is None
    if owned:
        db = SessionLocal()
    try:
        rows = db.execute(select(APIKey)).scalars().all()
        result = []
        for row in rows:
            preview = "****"
            key = None
            try:
                key = _fernet().decrypt(row.encrypted_key.encode("utf-8")).decode("utf-8")
                preview = mask_key(key)
            except InvalidToken:
                preview = "(ilegible: el secreto maestro cambió)"
            result.append({
                "provider_id": row.provider_id,
                "masked": preview,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "env_fallback": key is None and bool(_env_key(row.provider_id)),
            })
        return result
    finally:
        if owned:
            db.close()


def _env_key(provider_id: str) -> Optional[str]:
    env_map = {
        "deepseek": settings.deepseek_api_key,
        "google": settings.google_api_key,
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
    }
    return env_map.get(provider_id)


def _sync_adapter_key(provider_id: str, api_key: Optional[str]) -> None:
    """Update live adapter instances so new keys take effect without restart."""
    try:
        from api.endpoints.providers import _provider_adapters
        adapter = _provider_adapters.get(provider_id)
        if adapter is not None and hasattr(adapter, "api_key"):
            adapter.api_key = api_key
            # Force HTTP client rebuild with the new credential
            if getattr(adapter, "_client", None) is not None:
                adapter._client = None
    except Exception:  # pragma: no cover — import cycles during startup
        pass
