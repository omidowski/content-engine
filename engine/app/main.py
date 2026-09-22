from contextlib import asynccontextmanager
from pathlib import Path
from secrets import compare_digest
from threading import Lock
import re

from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.models import ContentItem, ContentStatus, ContentOrigin, PublishJob
from app import publishing, social
from app.schemas import (
    ApprovalRequest,
    ContentCreate,
    ContentRead,
    ContentUpdate,
    HealthResponse,
)
from app.services.content import generate_content
from app.services.video import ffmpeg_available, render
from app.services.voice import synthesize


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().app_env != "development" and not get_settings().engine_api_token:
        raise RuntimeError("ENGINE_API_TOKEN is required outside development")
    Base.metadata.create_all(bind=engine)
    get_settings().output_dir.mkdir(parents=True, exist_ok=True)
    if get_settings().publishing_worker_enabled:
        publishing.start_worker()
    yield
    publishing.stop_event.set()


def require_engine_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    # These routes implement their own one-use OAuth state/cookie or expiring media signature.
    if request.method == "GET" and (request.url.path == "/ready" or re.fullmatch(r"/oauth/(youtube|instagram)/(start|callback)|/media/\d+", request.url.path)):
        return
    token = get_settings().engine_api_token
    if token and not compare_digest(authorization or "", "Bearer " + token):
        raise HTTPException(status_code=401, detail="Invalid engine token")


app = FastAPI(title="AI Content Engine", version="0.2.0", lifespan=lifespan,
              dependencies=[Depends(require_engine_token)])
app.include_router(social.router)
app.include_router(publishing.router)
# V1 uses a single process; serialize renders to avoid duplicate paid TTS calls.
render_lock = Lock()


@app.get("/ready")
def ready():
    return {"status": "ok"}


def no_active_publication(content_id, db):
    if db.scalar(select(PublishJob.id).where(PublishJob.content_id == content_id, PublishJob.status.in_(publishing.ACTIVE))):
        raise HTTPException(409, "Veröffentlichung ist geplant oder läuft. Wartende Aufträge zuerst stornieren.")


def _item_or_404(content_id: int, db: Session) -> ContentItem:
    item = db.get(ContentItem, content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content item not found")
    return item


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    live = bool(settings.openai_api_key and settings.elevenlabs_api_key and settings.elevenlabs_voice_id)
    return HealthResponse(status="ok", mode="live" if live else "demo", ffmpeg_available=ffmpeg_available(settings))


@app.post("/content", response_model=ContentRead, status_code=201)
def create_content(payload: ContentCreate, db: Session = Depends(get_db)) -> ContentItem:
    settings = get_settings()
    try:
        generated = generate_content(payload, settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Content generation failed: {exc}") from exc
    item = ContentItem(topic=payload.topic, language=payload.language, status=ContentStatus.REVIEW, **generated.model_dump())
    db.add(item)
    db.flush()
    db.add(ContentOrigin(content_id=item.id, live_script=bool(settings.openai_api_key)))
    db.commit()
    db.refresh(item)
    return item


@app.get("/content", response_model=list[ContentRead])
def list_content(db: Session = Depends(get_db)) -> list[ContentItem]:
    return list(db.scalars(select(ContentItem).order_by(ContentItem.created_at.desc())))


@app.get("/content/{content_id}", response_model=ContentRead)
def get_content(content_id: int, db: Session = Depends(get_db)) -> ContentItem:
    return _item_or_404(content_id, db)


@app.patch("/content/{content_id}", response_model=ContentRead)
@publishing.serial_queue
def update_content(content_id: int, payload: ContentUpdate, db: Session = Depends(get_db)) -> ContentItem:
    item = _item_or_404(content_id, db)
    if item.status is not ContentStatus.REVIEW:
        raise HTTPException(status_code=409, detail="Only content in REVIEW can be edited")
    no_active_publication(content_id, db)
    for key, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@app.post("/content/{content_id}/approve", response_model=ContentRead)
@publishing.serial_queue
def approve_content(content_id: int, payload: ApprovalRequest, db: Session = Depends(get_db)) -> ContentItem:
    item = _item_or_404(content_id, db)
    no_active_publication(content_id, db)
    if item.status is not ContentStatus.REVIEW:
        raise HTTPException(status_code=409, detail="Only content in REVIEW can be approved or rejected")
    item.status = ContentStatus.APPROVED if payload.approved else ContentStatus.REJECTED
    db.commit()
    db.refresh(item)
    return item


@app.post("/content/{content_id}/render", response_model=ContentRead)
def render_content(content_id: int, db: Session = Depends(get_db)) -> ContentItem:
    if not render_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A render is already running")
    try:
        return _render_content(content_id, db)
    finally:
        render_lock.release()


def _render_content(content_id: int, db: Session) -> ContentItem:
    item = _item_or_404(content_id, db)
    if item.status not in {ContentStatus.APPROVED, ContentStatus.AUDIO_READY}:
        raise HTTPException(status_code=409, detail="Content must be APPROVED before rendering")
    settings = get_settings()
    target_dir = Path(settings.output_dir) / str(item.id)
    try:
        if item.status is ContentStatus.APPROVED:
            narration = " ".join([item.hook, item.script, item.cta])
            audio_path = synthesize(narration, target_dir, settings)
            item.audio_path = str(audio_path.resolve())
            item.status = ContentStatus.AUDIO_READY
            db.commit()
        else:
            audio_path = Path(item.audio_path or "")
        narration = " ".join([item.hook, item.script, item.cta])
        video_path = render(narration, audio_path, target_dir, settings)
    except Exception as exc:
        db.refresh(item)
        raise HTTPException(status_code=502, detail=f"Rendering failed: {exc}") from exc
    item.video_path = str(video_path.resolve())
    item.status = ContentStatus.VIDEO_READY
    origin = db.get(ContentOrigin, item.id)
    if origin:
        origin.live_video = bool(settings.elevenlabs_api_key and settings.elevenlabs_voice_id)
    db.commit()
    db.refresh(item)
    return item


@app.post("/content/{content_id}/reopen", response_model=ContentRead)
@publishing.serial_queue
def reopen_content(content_id: int, db: Session = Depends(get_db)) -> ContentItem:
    if not render_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Wait for rendering to finish")
    try:
        item = _item_or_404(content_id, db)
        no_active_publication(content_id, db)
        item.status = ContentStatus.REVIEW
        item.audio_path = None
        item.video_path = None
        db.commit()
        db.refresh(item)
        return item
    finally:
        render_lock.release()


@app.get("/content/{content_id}/video")
def download_video(content_id: int, download: bool = Query(default=False), db: Session = Depends(get_db)):
    item = _item_or_404(content_id, db)
    if item.status != ContentStatus.VIDEO_READY or not item.video_path:
        raise HTTPException(status_code=409, detail="Video is not ready")
    path = Path(item.video_path).resolve()
    if not path.is_relative_to(get_settings().output_dir.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(path, media_type="video/mp4", filename=f"short-{item.id}.mp4",
                        content_disposition_type="attachment" if download else "inline")
