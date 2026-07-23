from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import JobStatus, Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: EmailStr
    display_name: str
    role: Role
    language: str
    is_active: bool
    created_at: datetime


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class ConversationCreate(BaseModel):
    title: str = Field(default="Neue Unterhaltung", min_length=1, max_length=160)
    incognito: bool = False


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    archived: bool | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: str
    content: str
    sources_json: str
    model: str
    token_count: int
    blocked: bool
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    archived: bool
    incognito: bool
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = []


class ChatIn(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=100_000)
    research: bool = False
    model: str | None = Field(default=None, max_length=160)


class FeedbackIn(BaseModel):
    message_id: str
    rating: Literal[-1, 1]
    category: str = Field(default="", max_length=80)
    comment: str = Field(default="", max_length=2000)


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    content: str = Field(min_length=2, max_length=200_000)
    source: str = Field(default="", max_length=4000)
    source_date: datetime | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    category: Literal[
        "confirmed", "unconfirmed", "user_note", "researched", "outdated", "conflicting", "internal"
    ] = "unconfirmed"
    review_at: datetime | None = None


class KnowledgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    content: str
    source: str
    confidence: float
    category: str
    version: int
    review_at: datetime | None
    approved_by: str | None
    created_at: datetime
    updated_at: datetime


class ResearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    max_pages: int | None = Field(default=None, ge=1, le=15)


class ProjectGenerateIn(BaseModel):
    description: str = Field(min_length=10, max_length=30_000)
    name: str = Field(default="generated-project", min_length=2, max_length=80)
    language: str = Field(default="auto", max_length=40)

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        cleaned = "".join(c for c in value if c.isalnum() or c in "-_").strip("-_")
        if not cleaned:
            raise ValueError("Project name must contain letters or numbers")
        return cleaned


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    status: JobStatus
    progress: int
    result_json: str
    error_message: str
    cancel_requested: bool
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime


class AdminUserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class ModelCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    model_name: str = Field(min_length=2, max_length=160)
    context_length: int = Field(default=8192, ge=1024, le=262144)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=64, le=32768)
    system_rules: str = Field(default="", max_length=30_000)


class ApiMessage(BaseModel):
    message: str
    detail: dict[str, Any] | None = None
