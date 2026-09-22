import hmac
import hashlib
import json
from functools import wraps
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import AutomationSettings, ContentItem, ContentStatus, ContentOrigin, PublishJob, SocialAccount
from app.publishers import instagram, media_signature, video_file, youtube
from app.social import ProviderError, aware, configured, utcnow

router = APIRouter()
Platform = Literal["instagram_reel", "instagram_story", "youtube"]
ACTIVE = ("QUEUED", "RUNNING", "UNCERTAIN")
queue_lock = threading.RLock()
stop_event = threading.Event()


def serial_queue(fn):
    @wraps(fn)
    def guarded(*args, **kwargs):
        with queue_lock:
            return fn(*args, **kwargs)
    return guarded


class ScheduleInput(BaseModel):
    content_id: int
    platforms: list[Platform] = Field(min_length=1, max_length=3)
    scheduled_at: datetime
    made_for_kids: bool = False
    synthetic_media: bool = False

    @field_validator("scheduled_at")
    @classmethod
    def zoned(cls, value):
        if value.tzinfo is None:
            raise ValueError("Datum benötigt eine Zeitzone.")
        return value.astimezone(timezone.utc)


class AutomationInput(BaseModel):
    enabled: bool = False
    mode: Literal["after_approval", "fully_automatic"] = "after_approval"
    platforms: list[Platform] = Field(default_factory=list, max_length=3)
    timezone: str = "Europe/Berlin"
    times: list[str] = Field(default_factory=lambda: ["09:00"], min_length=1, max_length=5)
    made_for_kids: bool = False
    synthetic_media: bool = False

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unbekannte Zeitzone.")
        return value

    @field_validator("times")
    @classmethod
    def valid_times(cls, values):
        import re
        if any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) for value in values):
            raise ValueError("Uhrzeiten im Format HH:MM erwartet.")
        return sorted(set(values))


def next_slot(now, zone, times):
    tz = ZoneInfo(zone)
    local = aware(now).astimezone(tz)
    for day in range(3):
        date = (local + timedelta(days=day)).date()
        for clock in sorted(times):
            hour, minute = map(int, clock.split(":"))
            candidate = datetime(date.year, date.month, date.day, hour, minute, tzinfo=tz)
            utc = candidate.astimezone(timezone.utc)
            if utc.astimezone(tz).replace(tzinfo=None) != candidate.replace(tzinfo=None):
                continue
            if utc > aware(now):
                return utc
    raise ValueError("Kein nächster Zeitpunkt gefunden.")


def readiness(platforms, db):
    s = get_settings()
    if not s.publishing_worker_enabled:
        raise ProviderError("Veröffentlichungsdienst ist auf dem Server noch nicht aktiviert.")
    if s.allow_demo_fallback or not (s.openai_api_key and s.elevenlabs_api_key and s.elevenlabs_voice_id):
        raise ProviderError("Live-Produktion einrichten und Demo-Fallback deaktivieren, bevor Inhalte gepostet werden.")
    for platform in platforms:
        provider = "youtube" if platform == "youtube" else "instagram"
        account = db.get(SocialAccount, provider)
        if not configured(provider) or not account:
            raise ProviderError(f"{provider.title()} zuerst verbinden.")
        if platform == "instagram_story" and account.account_type != "BUSINESS":
            raise ProviderError("Instagram-Stories benötigen ein Business-Konto.")


def job_view(job, db):
    return {"id": job.id, "content_id": job.content_id, "title": job.title,
            "platform": job.platform, "status": job.status, "scheduled_at": aware(job.scheduled_at),
            "published_at": aware(job.published_at) if job.published_at else None,
            "attempts": job.attempts, "error": job.error, "remote_url": job.remote_url,
            "remote_id": job.remote_id, "automatic_approval": job.automatic_approval}


def settings_row(db):
    row = db.get(AutomationSettings, 1)
    if not row:
        row = AutomationSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def automation_view(row):
    result = {name: getattr(row, name) for name in AutomationInput.model_fields}
    result.update(next_run=aware(row.next_run) if row.next_run else None, last_error=row.last_error,
                  worker_enabled=get_settings().publishing_worker_enabled)
    return result


def add_jobs(item, platforms, when, db, auto=False, made_for_kids=False, synthetic_media=False):
    jobs = []
    for platform in dict.fromkeys(platforms):
        account = db.get(SocialAccount, "youtube" if platform == "youtube" else "instagram")
        job = PublishJob(content_id=item.id, platform=platform, scheduled_at=when, automatic_approval=auto,
                         made_for_kids=made_for_kids, synthetic_media=synthetic_media, account_id=account.account_id,
                         content_fingerprint=fingerprint(item), title=item.title)
        db.add(job)
        jobs.append(job)
    db.flush()
    return jobs


def fingerprint(item):
    return hashlib.sha256(json.dumps([item.topic, item.language, item.hook, item.script, item.title, item.caption, item.cta], ensure_ascii=False).encode()).hexdigest()


def verify_origin(item, db, require_video=False):
    origin = db.get(ContentOrigin, item.id)
    if not origin or not origin.live_script or (require_video and not origin.live_video):
        raise ProviderError("Demo- oder ältere ungeprüfte Ausgaben werden nicht gepostet. Neuen Inhalt mit Live-Engine erstellen.")


@router.get("/publishing/jobs")
def list_jobs(db: Session = Depends(get_db)):
    return [job_view(job, db) for job in db.scalars(select(PublishJob).order_by(PublishJob.created_at.desc()).limit(200))]


@router.post("/publishing/jobs", status_code=201)
def schedule(payload: ScheduleInput, db: Session = Depends(get_db)):
    with queue_lock:
        item = db.get(ContentItem, payload.content_id)
        if not item:
            raise HTTPException(404, "Inhalt nicht gefunden.")
        if item.status != ContentStatus.VIDEO_READY:
            raise HTTPException(409, "Zuerst Video fertigstellen.")
        if payload.scheduled_at < utcnow() - timedelta(minutes=1):
            raise HTTPException(422, "Zeitpunkt liegt in der Vergangenheit.")
        try:
            readiness(payload.platforms, db)
            verify_origin(item, db, require_video=True)
            video_file(item)
            jobs = add_jobs(item, payload.platforms, payload.scheduled_at, db,
                            made_for_kids=payload.made_for_kids, synthetic_media=payload.synthetic_media)
            db.commit()
            return [job_view(job, db) for job in jobs]
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Für diesen Inhalt existiert bereits ein Auftrag auf einer gewählten Plattform.") from None
        except ProviderError as exc:
            raise HTTPException(409, str(exc)) from None


@router.get("/publishing/automation")
def get_automation(db: Session = Depends(get_db)):
    with queue_lock:
        return automation_view(settings_row(db))


@router.put("/publishing/automation")
def save_automation(payload: AutomationInput, db: Session = Depends(get_db)):
    with queue_lock:
        if payload.enabled:
            if not payload.platforms:
                raise HTTPException(422, "Mindestens eine Plattform wählen.")
            try:
                readiness(payload.platforms, db)
            except ProviderError as exc:
                raise HTTPException(409, str(exc)) from None
        row = settings_row(db)
        for name, value in payload.model_dump().items():
            setattr(row, name, value)
        row.next_run = next_slot(utcnow(), row.timezone, row.times) if row.enabled else None
        row.last_error = None
        db.commit()
        return automation_view(row)


@router.post("/publishing/jobs/{job_id}/{action}")
def job_action(job_id: int, action: str, db: Session = Depends(get_db)):
    with queue_lock:
        job = db.get(PublishJob, job_id)
        if not job:
            raise HTTPException(404, "Auftrag nicht gefunden.")
        if action == "cancel" and job.status in ("QUEUED", "FAILED"):
            job.status = "CANCELLED"
        elif action == "retry" and (job.status in ("FAILED", "CANCELLED") or (job.status == "UNCERTAIN" and job.platform == "youtube" and job.remote_key)):
            try:
                readiness([job.platform], db)
                item = db.get(ContentItem, job.content_id)
                if not item or fingerprint(item) != job.content_fingerprint:
                    raise ProviderError("Inhalt wurde geändert. Für eine neue Veröffentlichung einen neuen Entwurf erstellen.")
            except ProviderError as exc:
                raise HTTPException(409, str(exc)) from None
            job.status, job.error, job.scheduled_at = "QUEUED", None, utcnow()
        else:
            raise HTTPException(409, "Auftrag läuft bereits oder sein Ergebnis muss auf der Plattform geprüft werden.")
        db.commit()
        return job_view(job, db)


@router.post("/publishing/connections/{provider}/disconnect")
def disconnect(provider: str, db: Session = Depends(get_db)):
    with queue_lock:
        account = db.get(SocialAccount, provider)
        if account:
            targets = ["youtube"] if provider == "youtube" else ["instagram_reel", "instagram_story"]
            running = db.scalar(select(PublishJob.id).where(PublishJob.platform.in_(targets), PublishJob.status == "RUNNING"))
            if running:
                raise HTTPException(409, "Laufende Veröffentlichung zuerst abwarten.")
            db.execute(update(PublishJob).where(PublishJob.platform.in_(targets), PublishJob.status == "QUEUED").values(status="CANCELLED"))
            row = settings_row(db)
            row.enabled, row.next_run = False, None
            db.delete(account)
            db.commit()
        return {"disconnected": True}


@router.get("/media/{job_id}")
def signed_media(job_id: int, expires: int, signature: str, db: Session = Depends(get_db)):
    now = int(time.time())
    if expires < now or expires > now + 3600 or not get_settings().engine_api_token:
        raise HTTPException(403, "Medienlink abgelaufen.")
    if not hmac.compare_digest(media_signature(job_id, expires), signature):
        raise HTTPException(403, "Ungültiger Medienlink.")
    job = db.get(PublishJob, job_id)
    if not job or job.platform not in ("instagram_reel", "instagram_story") or job.status not in ("RUNNING", "UNCERTAIN", "FAILED"):
        raise HTTPException(404, "Video nicht verfügbar.")
    item = db.get(ContentItem, job.content_id)
    if not item or item.status != ContentStatus.VIDEO_READY:
        raise HTTPException(404, "Video nicht verfügbar.")
    try:
        path = video_file(item)
    except ProviderError:
        raise HTTPException(404, "Video nicht verfügbar.") from None
    return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"})


def enqueue_automatic(db, now):
    row = settings_row(db)
    if not row.enabled or not row.next_run or aware(row.next_run) > now:
        return
    row.next_run = next_slot(now, row.timezone, row.times)
    try:
        readiness(row.platforms, db)
        states = [ContentStatus.APPROVED, ContentStatus.AUDIO_READY, ContentStatus.VIDEO_READY]
        if row.mode == "fully_automatic":
            states.append(ContentStatus.REVIEW)
        already = select(PublishJob.content_id).where(PublishJob.platform.in_(row.platforms)).group_by(PublishJob.content_id).having(func.count(PublishJob.id) >= len(set(row.platforms)))
        item = db.scalar(select(ContentItem).join(ContentOrigin, ContentOrigin.content_id == ContentItem.id).where(
            ContentItem.status.in_(states), ~ContentItem.id.in_(already), ContentOrigin.live_script.is_(True),
            or_(ContentItem.status != ContentStatus.VIDEO_READY, ContentOrigin.live_video.is_(True))
        ).order_by(ContentItem.created_at).limit(1))
        if item:
            existing = set(db.scalars(select(PublishJob.platform).where(PublishJob.content_id == item.id)))
            remaining = [platform for platform in row.platforms if platform not in existing]
            add_jobs(item, remaining, now, db, row.mode == "fully_automatic", row.made_for_kids, row.synthetic_media)
        row.last_error = None if item else "Kein passender, noch ungeplanter Inhalt vorhanden."
    except ProviderError as exc:
        row.last_error = str(exc)
    db.commit()


def execute_job(job_id):
    from app.main import render_content
    with SessionLocal() as db:
        job = db.get(PublishJob, job_id)
        try:
            readiness([job.platform], db)
            account = db.get(SocialAccount, "youtube" if job.platform == "youtube" else "instagram")
            if account.account_id != job.account_id:
                raise ProviderError("Verbundenes Konto wurde gewechselt. Auftrag bleibt beim ursprünglichen Konto.")
            item = db.get(ContentItem, job.content_id)
            if not item:
                raise ProviderError("Inhalt nicht gefunden.")
            if fingerprint(item) != job.content_fingerprint:
                raise ProviderError("Inhalt wurde seit der Planung geändert. Auftrag gestoppt.")
            verify_origin(item, db)
            if item.status == ContentStatus.REVIEW and job.automatic_approval:
                item.status = ContentStatus.APPROVED
                db.commit()
            if item.status in (ContentStatus.APPROVED, ContentStatus.AUDIO_READY):
                item = render_content(item.id, db)
            if item.status != ContentStatus.VIDEO_READY:
                raise ProviderError("Inhalt ist nicht zur Veröffentlichung bereit.")
            video_file(item)
            verify_origin(item, db, require_video=True)
            with video_file(item).open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if job.video_fingerprint and job.video_fingerprint != digest:
                raise ProviderError("Videodatei wurde geändert. Bestehender Upload wird nicht fortgesetzt.")
            job.video_fingerprint = digest
            db.commit()
            with httpx.Client(timeout=httpx.Timeout(300, connect=20), follow_redirects=False) as client:
                (youtube if job.platform == "youtube" else instagram)(job, item, account, db, client)
            job.published_at = utcnow()
        except ProviderError as exc:
            job.status = "UNCERTAIN" if exc.uncertain else "FAILED"
            job.error = str(exc)
        except HTTPException:
            job.status, job.error = "FAILED", "Video konnte nicht erstellt werden. Engine-Konfiguration prüfen."
        except Exception:
            db.rollback()
            job = db.get(PublishJob, job_id)
            if job.status not in ("PUBLISHED", "UPLOADED"):
                job.status, job.error = "UNCERTAIN", "Auftrag unterbrochen. Plattform prüfen, bevor erneut veröffentlicht wird."
        db.commit()


def tick():
    with queue_lock, SessionLocal() as db:
        enqueue_automatic(db, utcnow())
        job = db.scalar(select(PublishJob).where(PublishJob.status == "QUEUED", PublishJob.scheduled_at <= utcnow()).order_by(PublishJob.scheduled_at, PublishJob.id).limit(1))
        if not job:
            return
        claimed = db.execute(update(PublishJob).where(PublishJob.id == job.id, PublishJob.status == "QUEUED").values(status="RUNNING", attempts=PublishJob.attempts + 1)).rowcount
        db.commit()
        job_id = job.id
    if claimed:
        execute_job(job_id)


def start_worker():
    stop_event.clear()
    with SessionLocal() as db:
        db.execute(update(PublishJob).where(PublishJob.status == "RUNNING").values(status="UNCERTAIN", error="Server wurde während eines Auftrags neu gestartet. Plattform prüfen."))
        db.commit()
    def loop():
        while not stop_event.is_set():
            try:
                tick()
            except Exception:
                import logging
                logging.getLogger(__name__).error("Publishing worker tick failed; queue remains persisted")
            stop_event.wait(15)
    thread = threading.Thread(target=loop, name="publishing-worker", daemon=True)
    thread.start()
    return thread
