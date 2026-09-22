from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, String, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ContentStatus(StrEnum):
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AUDIO_READY = "AUDIO_READY"
    VIDEO_READY = "VIDEO_READY"


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(String(10), default="de")
    hook: Mapped[str] = mapped_column(Text)
    script: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(300))
    caption: Mapped[str] = mapped_column(Text)
    cta: Mapped[str] = mapped_column(String(300))
    sources: Mapped[list[dict]] = mapped_column(JSON, default=list)
    status: Mapped[ContentStatus] = mapped_column(Enum(ContentStatus), default=ContentStatus.REVIEW)
    audio_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    video_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(300))
    account_type: Mapped[str] = mapped_column(String(40), default="")
    credentials: Mapped[str] = mapped_column(Text)  # Fernet encrypted, never returned by API


class ContentOrigin(Base):
    __tablename__ = "content_origins"
    content_id: Mapped[int] = mapped_column(primary_key=True)
    live_script: Mapped[bool] = mapped_column(Boolean, default=False)
    live_video: Mapped[bool] = mapped_column(Boolean, default=False)


class OAuthAttempt(Base):
    __tablename__ = "oauth_attempts"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublishJob(Base):
    __tablename__ = "publish_jobs"
    __table_args__ = (UniqueConstraint("content_id", "platform", name="one_post_per_content_platform"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(index=True)
    platform: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    automatic_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    made_for_kids: Mapped[bool] = mapped_column(Boolean, default=False)
    synthetic_media: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    remote_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    account_id: Mapped[str] = mapped_column(String(200))
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    video_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(300))


class AutomationSettings(Base):
    __tablename__ = "automation_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(30), default="after_approval")
    platforms: Mapped[list[str]] = mapped_column(JSON, default=list)
    timezone: Mapped[str] = mapped_column(String(100), default="Europe/Berlin")
    times: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["09:00"])
    made_for_kids: Mapped[bool] = mapped_column(Boolean, default=False)
    synthetic_media: Mapped[bool] = mapped_column(Boolean, default=False)
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
