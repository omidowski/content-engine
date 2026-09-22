"""Server-only OAuth and provider HTTP helpers. No provider payloads in error logs."""
import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import OAuthAttempt, SocialAccount

router = APIRouter()
PROVIDERS = {"youtube", "instagram"}


class ProviderError(Exception):
    def __init__(self, message: str, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def crypt():
    try:
        return Fernet(get_settings().token_encryption_key.encode())
    except Exception:
        raise ProviderError("Server-Schlüssel für Kontoverbindungen fehlt oder ist ungültig.") from None


def seal(value):
    return crypt().encrypt(json.dumps(value).encode()).decode()


def unseal(value):
    try:
        return json.loads(crypt().decrypt(value.encode()))
    except Exception:
        raise ProviderError("Kontoverbindung kann nicht entschlüsselt werden. Server-Schlüssel prüfen.") from None


def valid_origin(value):
    parsed = urlparse(value)
    return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and
                not parsed.password and parsed.path in ("", "/") and not parsed.query and not parsed.fragment)


def configured(provider):
    s = get_settings()
    if provider not in PROVIDERS or not valid_origin(s.public_engine_url) or not valid_origin(s.studio_url):
        return False
    try:
        crypt()
    except ProviderError:
        return False
    return bool(s.engine_api_token and ((s.google_client_id and s.google_client_secret) if provider == "youtube"
                else (s.instagram_client_id and s.instagram_client_secret)))


def callback_url(provider):
    return get_settings().public_engine_url.rstrip("/") + f"/oauth/{provider}/callback"


def send(client, method, url, *, mutation=False, **kwargs):
    try:
        response = client.request(method, url, **kwargs)
    except httpx.HTTPError:
        raise ProviderError("Plattform nicht erreichbar. Verbindung prüfen.", uncertain=mutation) from None
    if response.status_code >= 400:
        raise ProviderError(f"Plattform meldet HTTP {response.status_code}. Konto, Berechtigungen und Kontingent prüfen.",
                            uncertain=mutation and response.status_code >= 500)
    return response


def payload(response):
    try:
        return response.json()
    except ValueError:
        raise ProviderError("Unlesbare Plattformantwort. Ergebnis auf der Plattform prüfen.", uncertain=True) from None


def token_for(account, db, client):
    data = unseal(account.credentials)
    threshold = 300 if account.provider == "youtube" else 7 * 86400
    if data.get("expires_at", 0) > time.time() + threshold:
        return data["access_token"]
    s = get_settings()
    if account.provider == "youtube":
        if not data.get("refresh_token"):
            raise ProviderError("YouTube bitte erneut verbinden; dauerhafter Zugriff fehlt.")
        new = payload(send(client, "POST", "https://oauth2.googleapis.com/token", data={
            "client_id": s.google_client_id, "client_secret": s.google_client_secret,
            "grant_type": "refresh_token", "refresh_token": data["refresh_token"],
        }))
    else:
        new = payload(send(client, "GET", "https://graph.instagram.com/refresh_access_token", params={
            "grant_type": "ig_refresh_token", "access_token": data["access_token"],
        }))
    data.update(new)
    data["expires_at"] = time.time() + int(new.get("expires_in", 3600))
    account.credentials = seal(data)
    db.commit()
    return data["access_token"]


@router.get("/publishing/connections")
def connections(db: Session = Depends(get_db)):
    result = []
    for provider in ("instagram", "youtube"):
        account = db.get(SocialAccount, provider)
        result.append({"provider": provider, "configured": configured(provider),
                       "connected": bool(account), "label": account.label if account else None,
                       "account_type": account.account_type if account else None})
    return result


@router.post("/publishing/connections/{provider}/connect")
def begin_connect(provider: str, db: Session = Depends(get_db)):
    if not configured(provider):
        raise HTTPException(409, "Plattform-App und sichere Server-Adressen zuerst konfigurieren.")
    state = secrets.token_urlsafe(32)
    db.execute(delete(OAuthAttempt).where(OAuthAttempt.expires_at < utcnow()))
    db.add(OAuthAttempt(state_hash=hashlib.sha256(state.encode()).hexdigest(), provider=provider,
                       expires_at=utcnow() + timedelta(minutes=10)))
    db.commit()
    return {"url": get_settings().public_engine_url.rstrip("/") + f"/oauth/{provider}/start?" + urlencode({"state": state})}


@router.get("/oauth/{provider}/start")
def oauth_start(provider: str, state: str, db: Session = Depends(get_db)):
    attempt = db.get(OAuthAttempt, hashlib.sha256(state.encode()).hexdigest())
    if not attempt or attempt.provider != provider or aware(attempt.expires_at) < utcnow() or not configured(provider):
        raise HTTPException(400, "Anmeldung abgelaufen. Im Studio neu verbinden.")
    s = get_settings()
    params = {"client_id": s.google_client_id if provider == "youtube" else s.instagram_client_id,
              "redirect_uri": callback_url(provider), "response_type": "code", "state": state}
    if provider == "youtube":
        params.update(scope="https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
                      access_type="offline", prompt="consent")
        url = "https://accounts.google.com/o/oauth2/v2/auth"
    else:
        params.update(scope="instagram_business_basic,instagram_business_content_publish", enable_fb_login="0", force_authentication="1")
        url = "https://www.instagram.com/oauth/authorize"
    response = RedirectResponse(url + "?" + urlencode(params), status_code=303)
    response.set_cookie("oauth_" + provider, state, max_age=600, secure=True, httponly=True, samesite="lax", path=f"/oauth/{provider}")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/oauth/{provider}/callback")
def oauth_callback(provider: str, request: Request, state: str = "", code: str = "", error: str = "", db: Session = Depends(get_db)):
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    attempt = db.get(OAuthAttempt, state_hash)
    cookie = request.cookies.get("oauth_" + provider, "")
    if not attempt or attempt.provider != provider or not cookie or not secrets.compare_digest(cookie, state) or aware(attempt.expires_at) < utcnow():
        raise HTTPException(400, "Ungültige oder abgelaufene Anmeldung. Im Studio neu verbinden.")
    # Consume state atomically before exchanging the single-use authorization code.
    claimed = db.execute(delete(OAuthAttempt).where(OAuthAttempt.state_hash == state_hash)).rowcount
    db.commit()
    if claimed != 1:
        raise HTTPException(400, "Anmeldung bereits verwendet.")
    outcome = "error"
    if code and not error:
        s = get_settings()
        try:
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                data = {"client_id": s.google_client_id if provider == "youtube" else s.instagram_client_id,
                        "client_secret": s.google_client_secret if provider == "youtube" else s.instagram_client_secret,
                        "grant_type": "authorization_code", "code": code, "redirect_uri": callback_url(provider)}
                endpoint = "https://oauth2.googleapis.com/token" if provider == "youtube" else "https://api.instagram.com/oauth/access_token"
                token = payload(send(client, "POST", endpoint, data=data))
                if provider == "youtube":
                    if not token.get("refresh_token"):
                        raise ProviderError("Dauerhafter Zugriff fehlt.")
                    channels = payload(send(client, "GET", "https://www.googleapis.com/youtube/v3/channels",
                        headers={"Authorization": "Bearer " + token["access_token"]}, params={"part": "snippet", "mine": "true"}))["items"]
                    if len(channels) != 1:
                        raise ProviderError("Bitte genau einen YouTube-Kanal verbinden.")
                    identity, label, kind = channels[0]["id"], channels[0]["snippet"]["title"], "CHANNEL"
                else:
                    token = payload(send(client, "GET", "https://graph.instagram.com/access_token", params={
                        "grant_type": "ig_exchange_token", "client_secret": s.instagram_client_secret, "access_token": token["access_token"]}))
                    profile = payload(send(client, "GET", f"https://graph.instagram.com/{s.instagram_api_version}/me",
                        headers={"Authorization": "Bearer " + token["access_token"]}, params={"fields": "user_id,username,account_type"}))
                    identity, label, kind = str(profile["user_id"]), profile["username"], profile.get("account_type", "")
                token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
                account = db.get(SocialAccount, provider)
                if not account:
                    account = SocialAccount(provider=provider)
                    db.add(account)
                account.account_id, account.label, account.account_type = identity, label, kind
                account.credentials = seal(token)
                db.commit()
                outcome = "connected"
        except Exception:
            db.rollback()  # Never reflect a token, OAuth code or provider response into the browser.
    response = RedirectResponse(get_settings().studio_url.rstrip("/") + "/?" + urlencode({"social": outcome}), status_code=303)
    response.delete_cookie("oauth_" + provider, path=f"/oauth/{provider}", secure=True, httponly=True, samesite="lax")
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response
