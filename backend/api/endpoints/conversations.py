"""
Conversations endpoints — Mode A persistent per-provider chat history.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.endpoints.providers import _provider_adapters
from api.endpoints.auth import get_current_user_optional
from services.orchestrator import call_provider
from database.models import Conversation, Message as MessageRow, User
from database.session import get_db
from adapters.base import Message, MessageRole

router = APIRouter()


class ConversationCreate(BaseModel):
    title: str = Field(default="Nueva conversación", max_length=255)
    provider_id: Optional[str] = None
    model: Optional[str] = None


class ConversationOut(BaseModel):
    id: int
    title: str
    provider_id: Optional[str]
    model: Optional[str]
    created_at: str
    updated_at: Optional[str]


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    provider_id: Optional[str]
    model: Optional[str]
    created_at: str


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


@router.get("/", response_model=List[ConversationOut])
async def list_conversations(db: Session = Depends(get_db)):
    rows = db.execute(select(Conversation).order_by(Conversation.updated_at.desc()).limit(200)).scalars().all()
    return [
        ConversationOut(
            id=c.id, title=c.title, provider_id=c.provider_id, model=c.model,
            created_at=c.created_at.isoformat() if c.created_at else "",
            updated_at=c.updated_at.isoformat() if c.updated_at else None,
        )
        for c in rows
    ]


@router.post("/", response_model=ConversationOut, status_code=201)
async def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db)):
    if payload.provider_id and payload.provider_id not in _provider_adapters:
        raise HTTPException(status_code=404, detail=f"Proveedor '{payload.provider_id}' no disponible")
    row = Conversation(title=payload.title, provider_id=payload.provider_id, model=payload.model)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ConversationOut(
        id=row.id, title=row.title, provider_id=row.provider_id, model=row.model,
        created_at=row.created_at.isoformat(), updated_at=None,
    )


@router.get("/{conversation_id}/messages", response_model=List[MessageOut])
async def list_messages(conversation_id: int, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = db.execute(
        select(MessageRow).where(MessageRow.conversation_id == conversation_id).order_by(MessageRow.created_at)
    ).scalars().all()
    return [
        MessageOut(
            id=m.id, role=m.role, content=m.content, provider_id=m.provider_id,
            model=m.model, created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in rows
    ]


@router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(conversation_id: int, payload: SendMessage, db: Session = Depends(get_db)):
    """Store the user message, call the conversation's provider, store the reply."""
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not conv.provider_id or conv.provider_id not in _provider_adapters:
        raise HTTPException(status_code=400, detail="La conversación no tiene un proveedor válido asignado")

    history_rows = db.execute(
        select(MessageRow).where(MessageRow.conversation_id == conversation_id).order_by(MessageRow.created_at)
    ).scalars().all()
    messages = [
        Message(role=MessageRole(m.role), content=m.content)
        for m in history_rows[-20:]
        if m.role in ("user", "assistant")
    ]
    messages.append(Message(role=MessageRole.USER, content=payload.content))

    user_msg = MessageRow(conversation_id=conversation_id, role="user", content=payload.content)
    db.add(user_msg)
    db.commit()

    result = await call_provider(conv.provider_id, messages, model=conv.model)
    if result["status"] != "SUCCEEDED":
        raise HTTPException(status_code=502, detail=result["error"] or "El proveedor falló")

    assistant_msg = MessageRow(
        conversation_id=conversation_id,
        role="assistant",
        content=result["content"],
        provider_id=conv.provider_id,
        model=result.get("model"),
        metadata_json={"latency_ms": result.get("latency_ms"), "usage": result.get("usage", {})},
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return MessageOut(
        id=assistant_msg.id, role="assistant", content=assistant_msg.content,
        provider_id=conv.provider_id, model=result.get("model"),
        created_at=assistant_msg.created_at.isoformat() if assistant_msg.created_at else "",
    )


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conv)
    db.commit()
    return {"deleted": conversation_id}
