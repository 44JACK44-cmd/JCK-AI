"""
Placeholder for OpenAI adapter.
Will be blocked in FREE MODE.
"""
from adapters.base import AIProvider, ProviderStatus
from config import settings
from typing import Dict, Any, List, Optional

class OpenAIAdapter(AIProvider):
    """Placeholder adapter for OpenAI."""
    
    @property
    def provider_id(self) -> str:
        return "openai"
    
    @property
    def provider_name(self) -> str:
        return "OpenAI"
    
    async def get_provider_info(self) -> Dict[str, Any]:
        blocked = settings.free_mode_enabled and settings.free_mode_strict
        
        return {
            "name": "OpenAI",
            "provider_id": self.provider_id,
            "description": "OpenAI models (paid, blocked in FREE MODE)",
            "capabilities": ["chat_completion", "function_calling"],
            "models": [],
            "requires_auth": True,
            "free_tier_available": False,
            "status": "PAID_ROUTE_BLOCKED" if blocked else "AUTH_REQUIRED",
        }
    
    async def check_status(self) -> Dict[str, Any]:
        blocked = settings.free_mode_enabled and settings.free_mode_strict
        
        return {
            "available": not blocked,
            "status": ProviderStatus.PAID_ROUTE_BLOCKED.value if blocked else ProviderStatus.AUTH_REQUIRED.value,
            "message": "OpenAI is blocked in FREE MODE" if blocked else "OpenAI requires paid API key",
            "free_tier_available": False,
        }
    
    async def chat_completion(self, messages, model=None, temperature=0.7, max_tokens=None, stream=False, **kwargs):
        if settings.free_mode_enabled and settings.free_mode_strict:
            raise Exception("OpenAI is blocked in FREE MODE")
        raise NotImplementedError("OpenAI adapter not yet implemented")
    
    async def test_connection(self, api_key=None):
        blocked = settings.free_mode_enabled and settings.free_mode_strict
        
        return {
            "available": not blocked,
            "status": ProviderStatus.PAID_ROUTE_BLOCKED.value if blocked else ProviderStatus.AUTH_REQUIRED.value,
            "message": "Blocked in FREE MODE" if blocked else "Requires paid API",
        }