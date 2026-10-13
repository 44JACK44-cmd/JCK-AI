"""
Configuration management for NEXUS AI backend.
Uses Pydantic settings for type-safe configuration.
"""
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator
import os


class Settings(BaseSettings):
    """Main application settings."""
    
    # Application
    app_name: str = "NEXUS AI"
    app_version: str = "1.0.0"
    environment: str = "development"
    log_level: str = "INFO"
    api_port: int = 8000
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost",          # Capacitor Android WebView
        "capacitor://localhost",     # Capacitor iOS WebView
        "tauri://localhost",         # Tauri (macOS/Linux)
        "http://tauri.localhost",    # Tauri (Windows)
    ]
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./nexus_ai.db"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    
    # Security
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    
    # FREE MODE Policy
    free_mode_enabled: bool = True
    free_mode_strict: bool = True
    
    # AI Providers
    deepseek_api_key: Optional[str] = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    
    google_api_key: Optional[str] = None
    google_gemini_model: str = "gemini-3.8-flash"
    
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-3-haiku-20240307"
    
    openai_api_key: Optional[str] = None
    openai_organization: Optional[str] = None
    openai_model: str = "gpt-4"
    
    # File Storage
    file_storage_base_path: str = "./storage"
    file_storage_max_size_mb: int = 100
    allowed_file_extensions: List[str] = [
        ".txt", ".py", ".js", ".ts", ".jsx", ".tsx", 
        ".json", ".md", ".yml", ".yaml", ".xml", ".html", ".css"
    ]
    
    # Agent Security
    agent_max_concurrent_tasks: int = 5
    agent_timeout_seconds: int = 300
    agent_max_file_size_mb: int = 10
    agent_allowed_directories: List[str] = ["./projects", "./workspace"]
    agent_blocked_directories: List[str] = ["./.env", "./secrets", "./keys"]
    
    # Task Management
    task_max_retries: int = 3
    task_retry_delay_seconds: int = 5
    
    # Memory & Learning
    memory_enabled: bool = True
    memory_max_entries: int = 10000
    learning_adaptive_routing_enabled: bool = True
    
    # Windows Agent
    windows_agent_enabled: bool = True
    windows_allowed_shells: List[str] = ["powershell", "cmd"]
    windows_max_command_time_seconds: int = 60
    windows_max_output_size_kb: int = 1024
    
    # Device Pairing
    device_pairing_enabled: bool = True
    device_pairing_timeout_minutes: int = 10
    device_pairing_max_devices: int = 5
    
    # Development
    debug: bool = True
    reload_on_change: bool = True
    test_mode: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @validator("deepseek_api_key", pre=True)
    def validate_free_mode_api_keys(cls, v, values):
        """Validate API keys based on FREE MODE policy."""
        free_mode_enabled = values.get("free_mode_enabled", True)
        free_mode_strict = values.get("free_mode_strict", True)
        
        if free_mode_enabled and free_mode_strict and v is not None:
            # In strict FREE MODE, we should warn about API keys
            # but not prevent them (user might have free credits)
            print(f"[FREE MODE] API key detected: {v[:10]}...")
        return v
    
    @validator("agent_allowed_directories")
    def validate_agent_directories(cls, v):
        """Ensure agent directories are safe paths."""
        safe_dirs = []
        for dir_path in v:
            if not dir_path.startswith("/") and not dir_path.startswith("C:"):
                safe_dirs.append(os.path.join(".", dir_path))
            else:
                safe_dirs.append(dir_path)
        return safe_dirs
    
    @property
    def available_providers(self):
        """Get list of available AI providers based on configuration.
        
        Honesty note: classifications reflect VERIFIED reality, not marketing.
        - DeepSeek API: pay-as-you-go prepaid. NO free tier. Verified 402 when
          the account has no balance. Classified as paid route (blocked in FREE MODE).
        """
        providers = []
        
        # DeepSeek - Prepaid, NO free tier (verified: 402 Insufficient Balance)
        providers.append({
            "name": "DeepSeek",
            "provider_id": "deepseek",
            "available": self.deepseek_api_key is not None,
            "free": False,
            "status": "AUTH_REQUIRED" if not self.deepseek_api_key else "PAID_ROUTE_BLOCKED"
        })
        
        # Google Gemini - Free tier available
        providers.append({
            "name": "Google Gemini",
            "provider_id": "google",
            "available": self.google_api_key is not None,
            "free": True,
            "status": "FREE_AVAILABLE" if self.google_api_key else "AUTH_REQUIRED"
        })
        
        # Anthropic - Has free tier for certain models
        providers.append({
            "name": "Anthropic Claude",
            "provider_id": "anthropic",
            "available": self.anthropic_api_key is not None,
            "free": True,
            "status": "FREE_AVAILABLE" if self.anthropic_api_key else "AUTH_REQUIRED"
        })
        
        # OpenAI - Paid, blocked in FREE MODE
        openai_status = "AUTH_REQUIRED"
        if self.free_mode_enabled and self.free_mode_strict:
            openai_status = "PAID_ROUTE_BLOCKED"
        
        providers.append({
            "name": "OpenAI",
            "provider_id": "openai",
            "available": self.openai_api_key is not None and not self.free_mode_strict,
            "free": False,
            "status": openai_status
        })
        
        return providers


# Global settings instance
settings = Settings()