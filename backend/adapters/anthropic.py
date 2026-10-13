"""
Placeholder for Anthropic Claude adapter.
Will be implemented in Phase 3.
"""
from adapters.base import AIProvider, ProviderStatus
from typing import Dict, Any, List, Optional

class AnthropicAdapter(AIProvider):
    """Placeholder adapter for Anthropic Claude."""
    
    @property
    def provider_id(self) -> str:
        return "anthropic"
    
    @property
    def provider_name(self) -> str:
        return "Anthropic Claude"
    
    async def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Anthropic Claude",
            "provider_id": self.provider_id,
            "description": "Claude AI models with free tier",
            "capabilities": ["chat_completion", "reasoning"],
            "models": [],
            "requires_auth": True,
            "free_tier_available": True,
            "status": "AUTH_REQUIRED",
        }
    
    async def check_status(self) -> Dict[str, Any]:
        return {
            "available": False,
            "status": ProviderStatus.AUTH_REQUIRED.value,
            "message": "Anthropic Claude adapter not yet implemented",
            "free_tier_available": True,
        }
    
    async def chat_completion(self, messages, model=None, temperature=0.7, max_tokens=None, stream=False, **kwargs):
        raise NotImplementedError("Anthropic Claude adapter not yet implemented")
    
    async def test_connection(self, api_key=None):
        return {
            "available": False,
            "status": ProviderStatus.UNSUPPORTED.value,
            "message": "Adapter not implemented",
        }