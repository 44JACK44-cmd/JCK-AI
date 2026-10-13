"""
AI Providers endpoints.
Manages available AI providers, their status, and FREE MODE policy.
"""
from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from config import settings
from adapters.base import AIProvider, ProviderStatus
from adapters.deepseek import DeepSeekAdapter
from adapters.google import GoogleGeminiAdapter
from adapters.anthropic import AnthropicAdapter
from adapters.openai import OpenAIAdapter

router = APIRouter()


class ProviderResponse(BaseModel):
    """Response model for AI provider information."""
    name: str
    provider_id: str
    available: bool
    free: bool
    status: str
    capabilities: List[str] = Field(default_factory=list)
    limits: Dict[str, Any] = Field(default_factory=dict)
    last_checked: datetime = Field(default_factory=datetime.utcnow)
    model: str = ""
    requires_auth: bool = True
    auth_method: str = "api_key"


class ProviderCheckRequest(BaseModel):
    """Request model for checking provider status."""
    provider_id: str
    api_key: str = None


class ProviderCheckResponse(BaseModel):
    """Response model for provider check."""
    provider_id: str
    available: bool
    status: str
    message: str
    free_tier_available: bool = False
    rate_limit_info: Dict[str, Any] = Field(default_factory=dict)
    capabilities_verified: List[str] = Field(default_factory=list)


class FREE_MODEResponse(BaseModel):
    """Response model for FREE MODE status."""
    enabled: bool
    strict: bool
    blocked_providers: List[str]
    allowed_providers: List[str]
    policy_version: str = "1.0"
    last_updated: datetime = Field(default_factory=datetime.utcnow)


# Provider adapters instances
_provider_adapters = {
    "deepseek": DeepSeekAdapter(),
    "google": GoogleGeminiAdapter(),
    "anthropic": AnthropicAdapter(),
    "openai": OpenAIAdapter(),
}


@router.get("/", response_model=List[ProviderResponse])
async def get_providers():
    """
    Get all available AI providers with their current status.
    
    Returns:
        List of providers with availability, FREE MODE status, and capabilities.
    """
    providers = []
    
    for adapter in _provider_adapters.values():
        try:
            status_info = await adapter.check_status()
            provider_info = await adapter.get_provider_info()
            
            providers.append(ProviderResponse(
                name=provider_info["name"],
                provider_id=provider_info["provider_id"],
                available=status_info["available"],
                free=status_info["free_tier_available"],
                status=status_info["status"],
                capabilities=provider_info["capabilities"],
                limits=status_info.get("limits", {}),
                last_checked=datetime.utcnow(),
                model=provider_info.get("default_model", ""),
                requires_auth=provider_info.get("requires_auth", True),
                auth_method=provider_info.get("auth_method", "api_key"),
            ))
        except Exception as e:
            # If adapter fails, mark as unavailable
            providers.append(ProviderResponse(
                name=adapter.__class__.__name__.replace("Adapter", ""),
                provider_id=adapter.provider_id,
                available=False,
                free=False,
                status="UNAVAILABLE",
                capabilities=[],
                limits={"error": str(e)},
                last_checked=datetime.utcnow(),
                requires_auth=True,
                auth_method="api_key",
            ))
    
    return providers


@router.get("/available", response_model=List[ProviderResponse])
async def get_available_providers():
    """
    Get only available AI providers.
    
    Returns:
        List of available providers that can be used immediately.
    """
    all_providers = await get_providers()
    return [p for p in all_providers if p.available]


@router.get("/free", response_model=List[ProviderResponse])
async def get_free_providers():
    """
    Get AI providers with FREE tier availability.
    
    Returns:
        List of providers that offer free access.
    """
    all_providers = await get_providers()
    return [p for p in all_providers if p.free and p.available]


@router.post("/check", response_model=ProviderCheckResponse)
async def check_provider_status(request: ProviderCheckRequest):
    """
    Check status of a specific provider with optional API key.
    
    Args:
        request: Provider check request with provider_id and optional api_key.
    
    Returns:
        Detailed status information about the provider.
    """
    if request.provider_id not in _provider_adapters:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{request.provider_id}' not found"
        )
    
    adapter = _provider_adapters[request.provider_id]
    
    try:
        # If API key is provided, test authentication
        if request.api_key:
            test_result = await adapter.test_connection(api_key=request.api_key)
            return ProviderCheckResponse(
                provider_id=request.provider_id,
                available=test_result["available"],
                status=test_result["status"],
                message=test_result["message"],
                free_tier_available=test_result.get("free_tier_available", False),
                rate_limit_info=test_result.get("rate_limit_info", {}),
                capabilities_verified=test_result.get("capabilities", []),
            )
        else:
            # Just check general status
            status_info = await adapter.check_status()
            return ProviderCheckResponse(
                provider_id=request.provider_id,
                available=status_info["available"],
                status=status_info["status"],
                message=status_info.get("message", "Status checked"),
                free_tier_available=status_info.get("free_tier_available", False),
                rate_limit_info=status_info.get("limits", {}),
                capabilities_verified=status_info.get("capabilities", []),
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check provider status: {str(e)}"
        )


@router.get("/free-mode", response_model=FREE_MODEResponse)
async def get_free_mode_status():
    """
    Get current FREE MODE policy status.
    
    Returns:
        FREE MODE configuration and which providers are blocked/allowed.
    """
    all_providers = await get_providers()
    
    blocked = []
    allowed = []
    
    for provider in all_providers:
        if provider.available:
            if provider.free:
                allowed.append(provider.provider_id)
            elif settings.free_mode_strict:
                blocked.append(provider.provider_id)
            else:
                allowed.append(provider.provider_id)
    
    return FREE_MODEResponse(
        enabled=settings.free_mode_enabled,
        strict=settings.free_mode_strict,
        blocked_providers=blocked,
        allowed_providers=allowed,
    )


@router.get("/quota")
async def get_free_quota():
    """
    Free-tier quota per model (Copilot-style message counter).

    Returns how many messages were served in the current window, the exact
    limit when Google has reported it, and when each model's quota resets.
    """
    from services.quota import snapshot, WINDOW_SECONDS
    models = snapshot()
    active = [m for m in models if m["available"]]
    exhausted = [m for m in models if not m["available"]]
    # Optimistic: only blocked when we KNOW every observed model is exhausted
    can_chat = bool(active) or not exhausted
    return {
        "provider_id": "google",
        "window_seconds": WINDOW_SECONDS,
        "models": models,
        "can_chat": can_chat,
        "active_models": [m["model"] for m in active],
        "exhausted_models": [m["model"] for m in exhausted],
    }


@router.get("/{provider_id}/capabilities")
async def get_provider_capabilities(provider_id: str):
    """
    Get detailed capabilities of a specific provider.
    
    Args:
        provider_id: ID of the provider.
    
    Returns:
        Detailed capabilities information.
    """
    if provider_id not in _provider_adapters:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_id}' not found"
        )
    
    adapter = _provider_adapters[provider_id]
    provider_info = await adapter.get_provider_info()
    
    return {
        "provider_id": provider_id,
        "name": provider_info["name"],
        "capabilities": provider_info["capabilities"],
        "models": provider_info.get("models", []),
        "authentication": {
            "required": provider_info.get("requires_auth", True),
            "method": provider_info.get("auth_method", "api_key"),
            "free_tier_available": provider_info.get("free_tier_available", False),
        },
        "limits": provider_info.get("limits", {}),
        "supported_features": provider_info.get("supported_features", []),
    }


@router.get("/{provider_id}/models")
async def get_provider_models(provider_id: str):
    """
    Get available models for a specific provider.
    
    Args:
        provider_id: ID of the provider.
    
    Returns:
        List of available models with their capabilities.
    """
    if provider_id not in _provider_adapters:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_id}' not found"
        )
    
    adapter = _provider_adapters[provider_id]
    provider_info = await adapter.get_provider_info()
    
    models = provider_info.get("models", [])
    
    # Filter based on FREE MODE
    if settings.free_mode_enabled and settings.free_mode_strict:
        models = [
            model for model in models 
            if model.get("free", False) or model.get("cost", 0) == 0
        ]
    
    return {
        "provider_id": provider_id,
        "models": models,
        "count": len(models),
        "free_mode_filter_applied": settings.free_mode_enabled and settings.free_mode_strict,
    }