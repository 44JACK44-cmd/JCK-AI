"""
SQLAlchemy models for NEXUS AI persistence layer.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship
import enum

from database.base import Base


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(255), default="Nueva conversación")
    provider_id = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    provider_id = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    objective = Column(Text, nullable=False)
    mode = Column(String(16), default="A")  # A=single, B=multi, C=orchestrator
    status = Column(SAEnum(TaskStatus), default=TaskStatus.PENDING)
    providers = Column(JSON, default=list)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    events = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")


class TaskEvent(Base):
    __tablename__ = "task_events"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    event_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=True)
    data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task", back_populates="events")


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(64), nullable=True, index=True)
    objective = Column(Text, nullable=True)
    outcome = Column(Text, nullable=True)
    evaluation = Column(String(32), nullable=True)
    evidence = Column(JSON, default=dict)
    tools_used = Column(JSON, default=list)
    models_used = Column(JSON, default=list)
    errors = Column(JSON, default=list)
    system_version = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    token_hash = Column(String(255), nullable=False)
    scope = Column(JSON, default=list)
    is_revoked = Column(Boolean, default=False)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(64), nullable=True, index=True)
    command = Column(Text, nullable=False)
    cwd = Column(Text, nullable=False)
    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    status = Column(String(32), default="RUNNING")
    duration_ms = Column(Integer, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


class APIKey(Base):
    """Encrypted storage for user-provided provider API keys."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(String(64), unique=True, nullable=False, index=True)
    encrypted_key = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScheduledTask(Base):
    """Periodic task definitions executed by the in-process scheduler."""
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    objective = Column(Text, nullable=False)
    mode = Column(String(16), default="A")  # A=single chat, B=multi-ai
    providers = Column(JSON, default=list)
    interval_minutes = Column(Integer, default=60, nullable=False)
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String(32), nullable=True)
    last_result = Column(Text, nullable=True)
    run_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
