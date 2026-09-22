from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models import ContentStatus


class SourceInput(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl | None = None
    note: str | None = Field(default=None, max_length=2000)


class ContentCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    language: Literal["de", "en"] = "de"
    sources: list[SourceInput] = Field(default_factory=list, max_length=10)


class GeneratedContent(BaseModel):
    hook: str
    script: str
    title: str
    caption: str
    cta: str
    sources: list[dict] = Field(default_factory=list)


class ContentUpdate(BaseModel):
    hook: str | None = Field(default=None, min_length=3)
    script: str | None = Field(default=None, min_length=20)
    title: str | None = Field(default=None, min_length=3)
    caption: str | None = Field(default=None, min_length=3)
    cta: str | None = Field(default=None, min_length=3)


class ApprovalRequest(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=1000)


class ContentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    language: str
    hook: str
    script: str
    title: str
    caption: str
    cta: str
    sources: list[dict]
    status: ContentStatus
    audio_path: str | None
    video_path: str | None
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    mode: str
    ffmpeg_available: bool

