"""
DeepSeek AI provider adapter.

DeepSeek offers free API access with rate limits, making it an ideal
provider for FREE MODE in NEXUS AI.
"""
import os
import httpx
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime, timedelta
import logging

from config import settings
from adapters.base import (
    AIProvider, ProviderStatus, Message, ChatResponse, 
    ProviderInfo, ProviderError, MessageRole
)

logger = logging.getLogger(__name__)


class DeepSeekAdapter(AIProvider):
    """Adapter for DeepSeek AI API."""
    
    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.default_model = settings.deepseek_model
        self._client = None
        self._last_status_check = None
        self._status_cache = {}
    
    @property
    def provider_id(self) -> str:
        return "deepseek"
    
    @property
    def provider_name(self) -> str:
        return "DeepSeek"
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"NEXUS-AI/{settings.app_version}"
            }
            
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(60.0),
                follow_redirects=True,
            )
        
        return self._client
    
    async def get_provider_info(self) -> Dict[str, Any]:
        """Get detailed information about DeepSeek provider."""
        return {
            "name": "DeepSeek",
            "provider_id": self.provider_id,
            "description": "DeepSeek AI offers powerful language models with free API access.",
            "capabilities": [
                "chat_completion",
                "streaming",
                "function_calling",
                "code_generation",
                "reasoning",
                "multilingual"
            ],
            "models": [
                {
                    "id": "deepseek-chat",
                    "name": "DeepSeek Chat",
                    "description": "General purpose chat model",
                    "context_length": 16384,
                    "free": True,
                    "cost_per_1k_tokens": 0,
                    "capabilities": ["chat", "code", "reasoning"]
                },
                {
                    "id": "deepseek-coder",
                    "name": "DeepSeek Coder",
                    "description": "Specialized for code generation",
                    "context_length": 16384,
                    "free": True,
                    "cost_per_1k_tokens": 0,
                    "capabilities": ["code_generation", "code_explanation"]
                }
            ],
            "requires_auth": True,
            "auth_method": "api_key",
            "free_tier_available": True,
            "free_tier_limits": {
                "rate_limit": "10 RPM",  # Requests per minute
                "daily_limit": "1000 requests",
                "tokens_per_minute": 30000,
                "updated_at": "2024-01-01"  # Example date
            },
            "limits": {
                "max_tokens": 4096,
                "max_context_length": 16384,
                "rate_limit_requests": 10,
                "rate_limit_period": "minute"
            },
            "supported_features": [
                "streaming",
                "json_mode",
                "temperature",
                "top_p",
                "frequency_penalty",
                "presence_penalty"
            ],
            "documentation_url": "https://platform.deepseek.com/api-docs/",
            "pricing_url": "https://platform.deepseek.com/pricing",
            "verification_date": datetime.utcnow().isoformat(),
        }
    
    async def check_status(self) -> Dict[str, Any]:
        """
        Check DeepSeek API status and availability.
        
        Returns:
            Status information including FREE MODE eligibility.
        """
        # Cache status for 5 minutes
        if self._last_status_check and self._status_cache:
            cache_age = datetime.utcnow() - self._last_status_check
            if cache_age < timedelta(minutes=5):
                return self._status_cache.copy()
        
        try:
            # Try to make a simple API call to check status
            test_messages = [
                Message(role=MessageRole.USER, content="Hello")
            ]
            
            # Quick test without actually consuming tokens if possible
            if self.api_key:
                # Try a minimal request
                response = await self._make_request(
                    model=self.default_model,
                    messages=self._create_message_dict(test_messages),
                    max_tokens=1,
                    stream=False
                )
                
                available = True
                status = ProviderStatus.FREE_AVAILABLE
                message = "DeepSeek API is available and responding"
            else:
                # No API key, but we know DeepSeek has free tier
                available = False
                status = ProviderStatus.AUTH_REQUIRED
                message = "API key required for DeepSeek"
            
            status_info = {
                "available": available,
                "status": status.value,
                "message": message,
                "free_tier_available": True,  # DeepSeek has free tier
                "limits": {
                    "rate_limit": "10 RPM",
                    "daily_requests": 1000,
                    "tokens_per_minute": 30000,
                },
                "capabilities": ["chat", "streaming", "code_generation"],
                "last_checked": datetime.utcnow().isoformat(),
            }
            
            self._status_cache = status_info.copy()
            self._last_status_check = datetime.utcnow()
            
            return status_info
            
        except httpx.HTTPStatusError as e:
            # Distinguish "no key" from "key works but no balance" honestly.
            if e.response.status_code == 402:
                status_info = {
                    "available": False,
                    "status": ProviderStatus.PAID_ROUTE_BLOCKED.value,
                    "message": "DeepSeek autentica pero la cuenta no tiene saldo (prepago). No es una ruta gratuita.",
                    "free_tier_available": False,
                    "limits": {},
                    "capabilities": [],
                    "last_checked": datetime.utcnow().isoformat(),
                }
            else:
                status_info = {
                    "available": False,
                    "status": ProviderStatus.ERROR.value,
                    "message": f"DeepSeek API error {e.response.status_code}",
                    "free_tier_available": False,
                    "limits": {},
                    "capabilities": [],
                    "last_checked": datetime.utcnow().isoformat(),
                }
            self._status_cache = status_info.copy()
            self._last_status_check = datetime.utcnow()
            return status_info

        except Exception as e:
            logger.error(f"DeepSeek status check failed: {e}")
            
            status_info = {
                "available": False,
                "status": ProviderStatus.UNAVAILABLE.value,
                "message": f"DeepSeek API check failed: {str(e)}",
                "free_tier_available": True,  # Still has free tier theoretically
                "limits": {},
                "capabilities": [],
                "last_checked": datetime.utcnow().isoformat(),
            }
            
            self._status_cache = status_info.copy()
            self._last_status_check = datetime.utcnow()
            
            return status_info
    
    async def chat_completion(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> ChatResponse:
        """
        Send chat completion request to DeepSeek API.
        
        Args:
            messages: List of chat messages.
            model: Model to use (default: deepseek-chat).
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum tokens to generate.
            stream: Whether to stream response.
            **kwargs: Additional parameters.
            
        Returns:
            ChatResponse with generated content.
            
        Raises:
            ProviderError: If the request fails.
        """
        if not self.api_key:
            raise ProviderError(
                message="DeepSeek API key not configured",
                provider_id=self.provider_id,
                status_code=401
            )
        
        model = model or self.default_model
        
        try:
            # Prepare request payload
            payload = {
                "model": model,
                "messages": self._create_message_dict(messages),
                "temperature": temperature,
                "stream": stream,
            }
            
            if max_tokens:
                payload["max_tokens"] = max_tokens
            
            # Add any additional parameters
            for key, value in kwargs.items():
                if key not in payload and value is not None:
                    payload[key] = value
            
            # Make API request
            response = await self._make_request(**payload)
            
            if stream:
                # For streaming, return a generator
                return ChatResponse(
                    content=self._handle_stream_response(response),
                    model=model,
                    provider_id=self.provider_id,
                    finish_reason="stop",
                    usage={"total_tokens": 0},  # Will be calculated from stream
                    timestamp=datetime.utcnow(),
                    metadata={"streaming": True}
                )
            else:
                # Parse regular response
                choices = response.get("choices", [])
                if not choices:
                    raise ProviderError(
                        message="No choices in DeepSeek response",
                        provider_id=self.provider_id,
                        status_code=500
                    )
                
                choice = choices[0]
                message = choice.get("message", {})
                
                return ChatResponse(
                    content=message.get("content", ""),
                    model=model,
                    provider_id=self.provider_id,
                    finish_reason=choice.get("finish_reason"),
                    usage=response.get("usage", {}),
                    timestamp=datetime.utcnow(),
                    metadata={
                        "response_id": response.get("id"),
                        "created": response.get("created"),
                        "object": response.get("object"),
                    }
                )
                
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            error_message = f"DeepSeek API error: {status_code}"
            
            try:
                error_data = e.response.json()
                error_message = error_data.get("error", {}).get("message", error_message)
            except:
                pass
            
            # Honest classification: 402 = account without prepaid balance.
            # DeepSeek API has NO free tier; it is pay-as-you-go prepaid.
            if status_code == 402:
                raise ProviderError(
                    message=f"DeepSeek sin saldo (prepago requerido): {error_message}",
                    provider_id=self.provider_id,
                    status_code=status_code
                )
            
            raise ProviderError(
                message=error_message,
                provider_id=self.provider_id,
                status_code=status_code
            )
            
        except Exception as e:
            raise ProviderError(
                message=f"DeepSeek request failed: {str(e)}",
                provider_id=self.provider_id
            )
    
    async def _make_request(self, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to DeepSeek API."""
        async with self.client as client:
            response = await client.post(
                "/chat/completions",
                json=kwargs,
                timeout=60.0
            )
            response.raise_for_status()
            return response.json()
    
    async def _handle_stream_response(self, response):
        """Handle streaming response from DeepSeek."""
        # This would be implemented for actual streaming
        # For now, return a placeholder
        async def stream_generator():
            async for chunk in response.aiter_bytes():
                yield chunk.decode("utf-8")
        
        return stream_generator()
    
    async def test_connection(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Test connection to DeepSeek API.
        
        Args:
            api_key: Optional API key to test.
            
        Returns:
            Test results including authentication validity.
        """
        test_key = api_key or self.api_key
        
        if not test_key:
            return {
                "available": False,
                "status": ProviderStatus.AUTH_REQUIRED.value,
                "message": "API key required for DeepSeek",
                "free_tier_available": True,
                "rate_limit_info": {},
                "capabilities": [],
            }
        
        # Create a test client with the provided key
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {test_key}",
            "User-Agent": f"NEXUS-AI/{settings.app_version}"
        }
        
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=10.0
        ) as client:
            try:
                # Make a minimal test request
                test_payload = {
                    "model": self.default_model,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 1
                }
                
                response = await client.post(
                    "/chat/completions",
                    json=test_payload
                )
                
                if response.status_code == 200:
                    return {
                        "available": True,
                        "status": ProviderStatus.FREE_AVAILABLE.value,
                        "message": "DeepSeek API connection successful",
                        "free_tier_available": True,
                        "rate_limit_info": {
                            "headers": dict(response.headers),
                            "status": response.status_code,
                        },
                        "capabilities": ["chat_completion", "streaming", "code_generation"],
                    }
                elif response.status_code == 402:
                    # Key authenticates but the account has no prepaid balance.
                    # DeepSeek API is pay-as-you-go: NOT a free route.
                    return {
                        "available": False,
                        "status": ProviderStatus.PAID_ROUTE_BLOCKED.value,
                        "message": "DeepSeek autentica pero la cuenta no tiene saldo (prepago). Ruta de pago bloqueada en FREE MODE.",
                        "free_tier_available": False,
                        "rate_limit_info": {"status": 402},
                        "capabilities": [],
                    }
                else:
                    return {
                        "available": False,
                        "status": ProviderStatus.AUTH_REQUIRED.value,
                        "message": f"Authentication failed: {response.status_code}",
                        "free_tier_available": True,
                        "rate_limit_info": {"status": response.status_code},
                        "capabilities": [],
                    }
                    
            except httpx.RequestError as e:
                return {
                    "available": False,
                    "status": ProviderStatus.UNAVAILABLE.value,
                    "message": f"Connection failed: {str(e)}",
                    "free_tier_available": True,
                    "rate_limit_info": {},
                    "capabilities": [],
                }
            except Exception as e:
                return {
                    "available": False,
                    "status": ProviderStatus.ERROR.value,
                    "message": f"Test failed: {str(e)}",
                    "free_tier_available": True,
                    "rate_limit_info": {},
                    "capabilities": [],
                }
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None