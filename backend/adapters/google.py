"""
Google Gemini adapter — real implementation via the official Generative Language API.

Google AI Studio provides a genuine free tier for Gemini models (rate-limited).
Docs: https://ai.google.dev/gemini-api/docs
Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
Auth: x-goog-api-key header.
"""
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from config import settings
from adapters.base import (
    AIProvider, ProviderStatus, Message, ChatResponse,
    ProviderError, MessageRole,
)

logger = logging.getLogger(__name__)

# Known Gemini models with free-tier eligibility (verified against this account 2026-10-12).
# Free tier = "Generative Language Free tier" with per-minute/per-day rate limits.
FREE_MODELS = [
    {
        "id": "gemini-3.8-flash",
        "name": "Gemini 3.8 Flash",
        "description": "Current fast multimodal model with free tier (verified)",
        "context_length": 1048576,
        "free": True,
        "capabilities": ["chat", "code", "reasoning", "multimodal", "vision"],
    },
    {
        "id": "gemini-3-flash-preview",
        "name": "Gemini 3 Flash (preview)",
        "description": "Preview flash model (verified available)",
        "context_length": 1048576,
        "free": True,
        "capabilities": ["chat", "code", "reasoning", "multimodal", "vision"],
    },
    {
        "id": "gemini-3.1-flash-lite",
        "name": "Gemini 3.1 Flash Lite",
        "description": "Lightest model; highest free-tier throughput (verified)",
        "context_length": 1048576,
        "free": True,
        "capabilities": ["chat", "code", "multimodal"],
    },
    {
        "id": "gemini-flash-latest",
        "name": "Gemini Flash (latest alias)",
        "description": "Alias pointing to the latest flash model (verified)",
        "context_length": 1048576,
        "free": True,
        "capabilities": ["chat", "code", "reasoning", "multimodal", "vision"],
    },
]

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GoogleGeminiAdapter(AIProvider):
    """Adapter for Google Gemini via the official Generative Language API."""

    def __init__(self):
        self.api_key = settings.google_api_key
        self.default_model = settings.google_gemini_model or "gemini-3.8-flash"
        self._client: Optional[httpx.AsyncClient] = None
        self._status_cache: Dict[str, Any] = {}
        self._last_status_check: Optional[datetime] = None
        self.supports_native_stream = True

    def _candidate_models(self, model: Optional[str]) -> List[str]:
        """Primary model first, then remaining free models as failover candidates."""
        primary = model or self.default_model
        chain = [primary]
        for m in FREE_MODELS:
            if m["id"] != primary:
                chain.append(m["id"])
        return chain

    @property
    def provider_id(self) -> str:
        return "google"

    @property
    def provider_name(self) -> str:
        return "Google Gemini"

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(60.0),
                follow_redirects=True,
            )
        return self._client

    def _headers(self) -> Dict[str, str]:
        return {"x-goog-api-key": self.api_key} if self.api_key else {}

    async def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": self.provider_name,
            "provider_id": self.provider_id,
            "description": "Google Gemini models with a genuine free tier via AI Studio.",
            "capabilities": ["chat_completion", "streaming", "multimodal", "code_generation", "vision"],
            "models": FREE_MODELS,
            "requires_auth": True,
            "auth_method": "api_key",
            "free_tier_available": True,
            "limits": {
                "free_tier": "15 RPM (flash), 2 RPM (pro) — per AI Studio docs",
                "max_tokens": 8192,
                "max_context_length": 1048576,
            },
            "supported_features": ["streaming", "json_mode", "temperature", "top_p", "top_k"],
            "documentation_url": "https://ai.google.dev/gemini-api/docs",
            "verification_date": datetime.utcnow().isoformat(),
        }

    async def check_status(self) -> Dict[str, Any]:
        if self._last_status_check and self._status_cache:
            cache_age = datetime.utcnow() - self._last_status_check
            if cache_age.total_seconds() < 300:  # 5 min cache
                return self._status_cache.copy()

        if not self.api_key:
            status_info = {
                "available": False,
                "status": ProviderStatus.AUTH_REQUIRED.value,
                "message": "Google API key required (free tier at https://aistudio.google.com/apikey)",
                "free_tier_available": True,
                "limits": {},
                "capabilities": ["chat", "streaming", "multimodal"],
                "last_checked": datetime.utcnow().isoformat(),
            }
        else:
            try:
                # Minimal real request to verify the key and free-tier access
                response = await self.client.post(
                    f"/models/{self.default_model}:generateContent",
                    headers=self._headers(),
                    json={"contents": [{"parts": [{"text": "hi"}]}], "generationConfig": {"maxOutputTokens": 1}},
                    timeout=15.0,
                )
                if response.status_code == 200:
                    status_info = {
                        "available": True,
                        "status": ProviderStatus.FREE_AVAILABLE.value,
                        "message": "Gemini API free tier active",
                        "free_tier_available": True,
                        "limits": {"free_tier": "15 RPM (flash)"},
                        "capabilities": ["chat", "streaming", "multimodal", "code"],
                        "last_checked": datetime.utcnow().isoformat(),
                    }
                elif response.status_code in (401, 403):
                    status_info = {
                        "available": False,
                        "status": ProviderStatus.AUTH_REQUIRED.value,
                        "message": f"API key rejected: {response.status_code}",
                        "free_tier_available": True,
                        "limits": {},
                        "capabilities": [],
                        "last_checked": datetime.utcnow().isoformat(),
                    }
                elif response.status_code == 429:
                    # Primary model quota exhausted: probe an alternate free model
                    alt_model = next(
                        (m["id"] for m in FREE_MODELS if m["id"] != self.default_model), None,
                    )
                    alt_ok = False
                    if alt_model:
                        try:
                            alt = await self.client.post(
                                f"/models/{alt_model}:generateContent",
                                headers=self._headers(),
                                json={"contents": [{"parts": [{"text": "hi"}]}], "generationConfig": {"maxOutputTokens": 1}},
                                timeout=15.0,
                            )
                            alt_ok = alt.status_code == 200
                        except Exception:
                            alt_ok = False
                    if alt_ok:
                        status_info = {
                            "available": True,
                            "status": ProviderStatus.FREE_AVAILABLE.value,
                            "message": f"Free tier active via fallback model {alt_model} (primary model quota temporarily exhausted)",
                            "free_tier_available": True,
                            "limits": {"note": "Per-model quotas; failover automatic"},
                            "capabilities": ["chat", "streaming", "multimodal", "code"],
                            "last_checked": datetime.utcnow().isoformat(),
                        }
                    else:
                        status_info = {
                            "available": True,
                            "status": ProviderStatus.FREE_LIMIT_REACHED.value,
                            "message": "Free tier rate limit reached; retry shortly",
                            "free_tier_available": True,
                            "limits": {},
                            "capabilities": [],
                            "last_checked": datetime.utcnow().isoformat(),
                        }
                else:
                    status_info = {
                        "available": False,
                        "status": ProviderStatus.ERROR.value,
                        "message": f"Gemini API error {response.status_code}: {response.text[:200]}",
                        "free_tier_available": True,
                        "limits": {},
                        "capabilities": [],
                        "last_checked": datetime.utcnow().isoformat(),
                    }
            except Exception as e:
                status_info = {
                    "available": False,
                    "status": ProviderStatus.UNAVAILABLE.value,
                    "message": f"Gemini connection failed: {e}",
                    "free_tier_available": True,
                    "limits": {},
                    "capabilities": [],
                    "last_checked": datetime.utcnow().isoformat(),
                }

        self._status_cache = status_info.copy()
        self._last_status_check = datetime.utcnow()
        return status_info

    def _to_gemini_contents(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert NEXUS messages to Gemini contents format."""
        contents = []
        for msg in messages:
            role = "user" if msg.role == MessageRole.USER else "model"
            contents.append({"role": role, "parts": [{"text": msg.content}]})
        # Gemini requires alternating user/model starting with user
        if contents and contents[0]["role"] != "user":
            contents.insert(0, {"role": "user", "parts": [{"text": "(start)"}]})
        return contents

    async def chat_completion(
        self, messages: List[Message], model: Optional[str] = None,
        temperature: float = 0.7, max_tokens: Optional[int] = None,
        stream: bool = False, **kwargs,
    ) -> ChatResponse:
        if not self.api_key:
            raise ProviderError("Google API key not configured", self.provider_id, 401)
        payload: Dict[str, Any] = {
            "contents": self._to_gemini_contents(messages),
            "generationConfig": {"temperature": temperature},
        }
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens
        for k in ("topP", "topK"):
            if k in kwargs and kwargs[k] is not None:
                payload["generationConfig"][k] = kwargs[k]

        chain = self._candidate_models(model)
        last_error: Optional[ProviderError] = None
        for idx, candidate_model in enumerate(chain):
            try:
                response = await self.client.post(
                    f"/models/{candidate_model}:generateContent",
                    headers=self._headers(), json=payload, timeout=60.0,
                )
            except httpx.RequestError as e:
                detail = str(e) or type(e).__name__
                raise ProviderError(f"Gemini connection failed: {detail}", self.provider_id)

            is_last = idx == len(chain) - 1
            if response.status_code == 429:
                from services import quota
                body = ""
                try:
                    body = response.text
                except Exception:
                    pass
                quota.record_error(candidate_model, 429, body)
                last_error = ProviderError(
                    f"Gemini free-tier rate limit (429) on {candidate_model}; trying fallback model",
                    self.provider_id, 429,
                )
                if not is_last:
                    continue
                raise last_error
            if response.status_code in (404, 500, 502, 503) and not is_last:
                last_error = ProviderError(
                    f"Gemini API error {response.status_code} on {candidate_model}",
                    self.provider_id, response.status_code,
                )
                continue
            if response.status_code >= 400:
                raise ProviderError(
                    f"Gemini API error: {response.status_code}", self.provider_id, response.status_code,
                )

            from services import quota
            quota.record_served(candidate_model)
            data = response.json()
            candidate = (data.get("candidates") or [{}])[0]
            parts = candidate.get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            usage = data.get("usageMetadata", {})
            return ChatResponse(
                content=text, model=candidate_model, provider_id=self.provider_id,
                finish_reason=candidate.get("finishReason"),
                usage={
                    "prompt_tokens": usage.get("promptTokenCount", 0),
                    "completion_tokens": usage.get("candidatesTokenCount", 0),
                    "total_tokens": usage.get("totalTokenCount", 0),
                },
                metadata={"response_id": data.get("responseId")},
            )
        raise last_error or ProviderError("Gemini: no free models available", self.provider_id, 503)

    async def chat_completion_stream(
        self, messages: List[Message], model: Optional[str] = None,
        temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Native streaming via streamGenerateContent (SSE), with model failover."""
        if not self.api_key:
            raise ProviderError("Google API key not configured", self.provider_id, 401)
        payload = {
            "contents": self._to_gemini_contents(messages),
            "generationConfig": {"temperature": temperature},
        }
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        chain = self._candidate_models(model)
        last_error: Optional[ProviderError] = None
        for idx, candidate_model in enumerate(chain):
            emitted = False
            full_text: List[str] = []
            finish_reason: Optional[str] = None
            usage: Dict[str, int] = {}
            try:
                async with self.client.stream(
                    "POST",
                    f"/models/{candidate_model}:streamGenerateContent?alt=sse",
                    headers=self._headers(), json=payload, timeout=60.0,
                ) as response:
                    if response.status_code == 429:
                        from services import quota
                        body = ""
                        try:
                            await response.aread()
                            body = response.text
                        except Exception:
                            pass
                        quota.record_error(candidate_model, 429, body)
                        last_error = ProviderError(
                            f"Gemini free-tier rate limit (429) on {candidate_model}; trying fallback model",
                            self.provider_id, 429,
                        )
                        if idx < len(chain) - 1:
                            continue
                        raise last_error
                    if response.status_code in (404, 500, 502, 503) and idx < len(chain) - 1 and not emitted:
                        last_error = ProviderError(
                            f"Gemini stream error {response.status_code} on {candidate_model}",
                            self.provider_id, response.status_code,
                        )
                        continue
                    response.raise_for_status()
                    from services import quota
                    quota.record_served(candidate_model)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        candidate = (chunk.get("candidates") or [{}])[0]
                        parts = candidate.get("content", {}).get("parts", [])
                        delta = "".join(p.get("text", "") for p in parts)
                        if delta:
                            emitted = True
                            full_text.append(delta)
                            yield {"delta": delta, "model": candidate_model}
                        if candidate.get("finishReason"):
                            finish_reason = candidate["finishReason"]
                        if chunk.get("usageMetadata"):
                            um = chunk["usageMetadata"]
                            usage = {
                                "prompt_tokens": um.get("promptTokenCount", 0),
                                "completion_tokens": um.get("candidatesTokenCount", 0),
                                "total_tokens": um.get("totalTokenCount", 0),
                            }
                yield {"delta": "", "finish_reason": finish_reason, "usage": usage, "model": candidate_model}
                return
            except ProviderError:
                raise
            except httpx.HTTPStatusError as e:
                detail = e.response.status_code
                if detail in (404, 500, 502, 503) and not emitted and idx < len(chain) - 1:
                    last_error = ProviderError(f"Gemini stream error: {detail}", self.provider_id, detail)
                    continue
                raise ProviderError(f"Gemini stream error: {detail}", self.provider_id, detail)
            except httpx.RequestError as e:
                detail = str(e) or type(e).__name__
                raise ProviderError(f"Gemini stream connection failed: {detail}", self.provider_id)
        raise last_error or ProviderError("Gemini: no free models available", self.provider_id, 503)

    async def test_connection(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        test_key = api_key or self.api_key
        if not test_key:
            return {
                "available": False, "status": ProviderStatus.AUTH_REQUIRED.value,
                "message": "Google API key required (free tier: https://aistudio.google.com/apikey)",
                "free_tier_available": True, "rate_limit_info": {}, "capabilities": [],
            }
        saved = self.api_key
        self.api_key = test_key
        try:
            status = await self.check_status()
            return {
                "available": status["available"], "status": status["status"],
                "message": status["message"],
                "free_tier_available": status.get("free_tier_available", True),
                "rate_limit_info": status.get("limits", {}),
                "capabilities": status.get("capabilities", []),
            }
        finally:
            self.api_key = saved
            self._status_cache = {}
            self._last_status_check = None
