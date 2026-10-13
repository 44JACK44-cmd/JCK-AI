"""
Base classes for AI provider adapters.
Defines the common interface that all providers must implement.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncGenerator
from enum import Enum
from datetime import datetime
import asyncio
from pydantic import BaseModel, Field


class ProviderStatus(str, Enum):
    """Status of an AI provider."""
    FREE_AVAILABLE = "FREE_AVAILABLE"
    FREE_LIMIT_REACHED = "FREE_LIMIT_REACHED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"
    PAID_ROUTE_BLOCKED = "PAID_ROUTE_BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    RATE_LIMITED = "RATE_LIMITED"
    ERROR = "ERROR"


class MessageRole(str, Enum):
    """Roles for chat messages."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"


class Message(BaseModel):
    """A chat message."""
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    """Request for chat completion."""
    messages: List[Message]
    model: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stream: bool = False
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    tool_choice: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from chat completion."""
    content: str
    model: str
    provider_id: str
    finish_reason: Optional[str] = None
    usage: Dict[str, int] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProviderInfo(BaseModel):
    """Information about an AI provider."""
    name: str
    provider_id: str
    description: str
    capabilities: List[str]
    models: List[Dict[str, Any]]
    requires_auth: bool = True
    auth_method: str = "api_key"
    free_tier_available: bool = False
    limits: Dict[str, Any] = Field(default_factory=dict)
    supported_features: List[str] = Field(default_factory=list)


class AIProvider(ABC):
    """
    Abstract base class for AI provider adapters.
    
    All providers must implement this interface to ensure compatibility
    with the NEXUS AI platform.
    """
    
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider."""
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name of the provider."""
        pass
    
    @abstractmethod
    async def get_provider_info(self) -> Dict[str, Any]:
        """
        Get detailed information about this provider.
        
        Returns:
            Dictionary with provider information including capabilities,
            available models, authentication requirements, and limits.
        """
        pass
    
    @abstractmethod
    async def check_status(self) -> Dict[str, Any]:
        """
        Check the current status and availability of this provider.
        
        Returns:
            Dictionary with status information including availability,
            FREE MODE status, rate limits, and any restrictions.
        """
        pass
    
    @abstractmethod
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
        Send a chat completion request to the provider.
        
        Args:
            messages: List of chat messages.
            model: Model to use (optional, uses default if not specified).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            stream: Whether to stream the response.
            **kwargs: Additional provider-specific parameters.
            
        Returns:
            ChatResponse with the generated content and metadata.
            
        Raises:
            ProviderError: If the request fails.
        """
        pass
    
    async def chat_completion_stream(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat completion response.
        
        Args:
            messages: List of chat messages.
            model: Model to use.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional provider-specific parameters.
            
        Yields:
            Chunks of the generated response as strings.
        """
        response = await self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs
        )
        
        # Handle streaming response
        # This is a simplified version - actual implementation depends on provider
        if isinstance(response.content, str):
            yield response.content
        else:
            # If provider returns a streaming object
            async for chunk in response.content:
                yield chunk
    
    @abstractmethod
    async def test_connection(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Test connection to the provider with optional API key.
        
        Args:
            api_key: Optional API key to test authentication.
            
        Returns:
            Dictionary with test results including success status,
            authentication validity, and available capabilities.
        """
        pass
    
    def validate_free_mode(self) -> bool:
        """
        Validate if this provider can be used in FREE MODE.
        
        Returns:
            True if the provider can be used in FREE MODE, False otherwise.
        """
        info = asyncio.run(self.get_provider_info())
        return info.get("free_tier_available", False)
    
    async def get_available_models(self) -> List[Dict[str, Any]]:
        """
        Get list of available models from this provider.
        
        Returns:
            List of models with their details including cost, capabilities,
            and FREE MODE eligibility.
        """
        info = await self.get_provider_info()
        return info.get("models", [])
    
    def _create_message_dict(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert Message objects to dictionary format for API calls."""
        return [
            {
                "role": msg.role.value,
                "content": msg.content,
                **msg.metadata
            }
            for msg in messages
        ]


class ProviderError(Exception):
    """Base exception for provider-related errors."""
    
    def __init__(self, message: str, provider_id: str, status_code: Optional[int] = None):
        self.message = message
        self.provider_id = provider_id
        self.status_code = status_code
        super().__init__(f"{provider_id}: {message}")


class ProviderRegistry:
    """Registry for managing AI provider adapters."""
    
    def __init__(self):
        self._providers: Dict[str, AIProvider] = {}
    
    def register(self, provider: AIProvider):
        """Register a provider adapter."""
        self._providers[provider.provider_id] = provider
    
    def get(self, provider_id: str) -> Optional[AIProvider]:
        """Get a provider adapter by ID."""
        return self._providers.get(provider_id)
    
    def get_all(self) -> List[AIProvider]:
        """Get all registered provider adapters."""
        return list(self._providers.values())
    
    def get_available(self) -> List[AIProvider]:
        """Get all available providers."""
        available = []
        for provider in self._providers.values():
            try:
                # Check if provider is available (non-blocking check)
                # This is a simplified check - actual implementation would be async
                info = asyncio.run(provider.get_provider_info())
                if info.get("available", True):
                    available.append(provider)
            except:
                continue
        return available
    
    def get_free_providers(self) -> List[AIProvider]:
        """Get providers with FREE tier availability."""
        free_providers = []
        for provider in self._providers.values():
            try:
                if provider.validate_free_mode():
                    free_providers.append(provider)
            except:
                continue
        return free_providers


# Global provider registry
provider_registry = ProviderRegistry()