"""Video adapters. Interrupted writes are never silently repeated."""
import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

from app.config import get_settings
from app.social import ProviderError, payload, send, token_for


def media_signature(job_id, expires):
    key = get_settings().engine_api_token
    if not key:
        raise ProviderError("Sicherer Medienzugriff ist nicht konfiguriert.")
    return hmac.new(key.encode(), f"{job_id}:{expires}".encode(), hashlib.sha256).hexdigest()


def video_file(item):
    path = Path(item.video_path or "").resolve()
    if not path.is_relative_to(get_settings().output_dir.resolve()) or not path.is_file():
        raise ProviderError("Die Videodatei fehlt. Video erneut erstellen.")
    return path


def youtube(job, item, account, db, client):
    path = video_file(item)
    token = token_for(account, db, client)
    headers = {"Authorization": "Bearer " + token}
    size = path.stat().st_size
    if not job.remote_key:
        response = send(client, "POST", "https://www.googleapis.com/upload/youtube/v3/videos",
            mutation=True, params={"uploadType": "resumable", "part": "snippet,status"},
            headers={**headers, "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"},
            json={"snippet": {"title": item.title[:100], "description": item.caption[:5000], "categoryId": "22"},
                  "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": job.made_for_kids,
                             "containsSyntheticMedia": job.synthetic_media}})
        location = response.headers.get("Location", "")
        parsed = urlparse(location)
        if parsed.scheme != "https" or parsed.hostname != "www.googleapis.com" or parsed.username or parsed.password:
            raise ProviderError("Ungültige Upload-Adresse von YouTube.", uncertain=True)
        job.remote_key = location
        db.commit()
    response = send(client, "PUT", job.remote_key, headers={**headers, "Content-Length": "0", "Content-Range": f"bytes */{size}"})
    if response.status_code in (200, 201):
        result = payload(response)
    elif response.status_code == 308:
        last = response.headers.get("Range", "")
        offset = int(last.rsplit("-", 1)[-1]) + 1 if last else 0
        if not 0 <= offset < size:
            raise ProviderError("Upload-Fortschritt unklar. YouTube prüfen.", uncertain=True)
        with path.open("rb") as stream:
            stream.seek(offset)
            response = send(client, "PUT", job.remote_key, mutation=True,
                headers={**headers, "Content-Type": "video/mp4", "Content-Length": str(size - offset),
                         "Content-Range": f"bytes {offset}-{size - 1}/{size}"}, content=stream)
        if response.status_code == 308:
            raise ProviderError("YouTube-Upload noch unvollständig. Fortsetzen möglich.")
        result = payload(response)
    else:
        raise ProviderError("YouTube-Uploadstatus unklar.", uncertain=True)
    if not result.get("id"):
        raise ProviderError("YouTube hat keine Video-ID bestätigt.", uncertain=True)
    job.remote_id = result["id"]
    job.remote_url = "https://www.youtube.com/watch?v=" + result["id"]
    privacy = result.get("status", {}).get("privacyStatus")
    job.status = "PUBLISHED" if privacy == "public" else "UPLOADED"
    if privacy != "public":
        job.error = "Hochgeladen, aber öffentliche Sichtbarkeit nicht bestätigt. In YouTube Studio prüfen (API-Audit kann erforderlich sein)."


def instagram(job, item, account, db, client):
    s = get_settings()
    token = token_for(account, db, client)
    headers = {"Authorization": "Bearer " + token}
    base = f"https://graph.instagram.com/{s.instagram_api_version}"
    if not job.remote_key:
        expires = int(time.time()) + 3600
        video_url = s.public_engine_url.rstrip("/") + f"/media/{job.id}?" + urlencode({
            "expires": expires, "signature": media_signature(job.id, expires)})
        data = {"media_type": "STORIES" if job.platform == "instagram_story" else "REELS", "video_url": video_url}
        if job.platform == "instagram_reel":
            data.update(caption=item.caption[:2200], share_to_feed="true")
        result = payload(send(client, "POST", f"{base}/{account.account_id}/media", headers=headers, data=data, mutation=True))
        job.remote_key = str(result["id"])
        db.commit()
    for _ in range(60):
        result = payload(send(client, "GET", f"{base}/{job.remote_key}", headers=headers, params={"fields": "status_code"}))
        state = result.get("status_code")
        if state == "PUBLISHED":
            job.status = "PUBLISHED"
            return
        if state == "FINISHED":
            break
        if state in ("ERROR", "EXPIRED"):
            raise ProviderError("Instagram konnte das Video nicht verarbeiten. Format und Container prüfen.")
        time.sleep(5)
    else:
        raise ProviderError("Instagram verarbeitet das Video noch. Später erneut versuchen.")
    result = payload(send(client, "POST", f"{base}/{account.account_id}/media_publish", headers=headers,
                          data={"creation_id": job.remote_key}, mutation=True))
    if not result.get("id"):
        raise ProviderError("Instagram hat keine Beitrags-ID bestätigt.", uncertain=True)
    job.remote_id = str(result["id"])
    job.status = "PUBLISHED"
    db.commit()
    try:
        info = payload(send(client, "GET", f"{base}/{job.remote_id}", headers=headers, params={"fields": "permalink"}))
        link = info.get("permalink", "")
        if urlparse(link).scheme == "https" and urlparse(link).hostname in ("www.instagram.com", "instagram.com"):
            job.remote_url = link
    except ProviderError:
        pass
