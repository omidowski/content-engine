import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs

import httpx
import pytest
from cryptography.fernet import Fernet

from app.config import get_settings
from app.database import SessionLocal
from app.models import ContentItem, ContentOrigin, ContentStatus, PublishJob, SocialAccount, AutomationSettings
from app import publishing, publishers, social


@pytest.fixture
def live(client, monkeypatch, tmp_path):
    item = client.post("/content", json={"topic": "Publishing test"}).json()
    s = get_settings()
    for key, value in dict(output_dir=tmp_path, engine_api_token="test-engine-token", token_encryption_key=Fernet.generate_key().decode(),
            public_engine_url="https://engine.example", studio_url="https://studio.example", google_client_id="test-client",
            google_client_secret="test-secret", instagram_client_id="test-ig", instagram_client_secret="test-secret",
            openai_api_key="test-openai", elevenlabs_api_key="test-voice", elevenlabs_voice_id="test-voice-id",
            allow_demo_fallback=False, publishing_worker_enabled=True).items():
        monkeypatch.setattr(s, key, value)
    client.headers["Authorization"] = "Bearer test-engine-token"
    path = tmp_path / "video.mp4"
    path.write_bytes(b"video-bytes")
    with SessionLocal() as db:
        record = db.get(ContentItem, item["id"])
        record.status, record.video_path = ContentStatus.VIDEO_READY, str(path)
        origin = db.get(ContentOrigin, record.id)
        origin.live_script = origin.live_video = True
        for provider in ("instagram", "youtube"):
            db.add(SocialAccount(provider=provider, account_id=provider + "-account", label="Test account", account_type="BUSINESS",
                credentials=social.seal({"access_token": "test-access", "refresh_token": "test-refresh", "expires_at": time.time() + 30 * 86400})))
        db.commit()
    return client, item["id"]


def schedule(client, content_id, platform="youtube"):
    return client.post("/publishing/jobs", json={"content_id": content_id, "platforms": [platform],
                       "scheduled_at": datetime.now(timezone.utc).isoformat()})


def test_schedule_duplicate_edit_lock_and_cancel(live):
    client, content_id = live
    response = schedule(client, content_id)
    assert response.status_code == 201
    job_id = response.json()[0]["id"]
    assert schedule(client, content_id).status_code == 409
    assert client.post(f"/content/{content_id}/reopen").status_code == 409
    assert client.post(f"/publishing/jobs/{job_id}/cancel").json()["status"] == "CANCELLED"
    assert client.post(f"/content/{content_id}/reopen").status_code == 200
    assert client.patch(f"/content/{content_id}", json={"title": "A changed title"}).status_code == 200
    assert client.post(f"/publishing/jobs/{job_id}/retry").status_code == 409


def test_demo_provenance_cannot_publish_even_with_live_keys(live):
    client, content_id = live
    with SessionLocal() as db:
        db.get(ContentOrigin, content_id).live_video = False
        db.commit()
    assert schedule(client, content_id).status_code == 409
    assert client.get("/publishing/jobs").json() == []


def test_auth_and_signed_media_are_scoped(live):
    client, content_id = live
    job_id = schedule(client, content_id, "instagram_reel").json()[0]["id"]
    with SessionLocal() as db:
        db.get(PublishJob, job_id).status = "RUNNING"
        db.commit()
    client.headers.pop("Authorization")
    assert client.get("/publishing/jobs").status_code == 401
    assert client.get("/ready").status_code == 200
    assert client.get("/health").status_code == 401
    expiry = int(time.time()) + 300
    signature = publishers.media_signature(job_id, expiry)
    url = f"/media/{job_id}?expires={expiry}&signature={signature}"
    assert client.get(url, headers={"Range": "bytes=0-4"}).content == b"video"
    assert client.get(url.replace(signature, "bad")).status_code == 403
    assert client.get(url.replace(str(expiry), str(expiry - 600))).status_code == 403
    assert client.get(url.replace(f"/media/{job_id}", f"/media/{job_id+1}")).status_code == 403


def test_timezone_dst_and_naive_input(live):
    client, content_id = live
    assert publishing.next_slot(datetime(2026, 3, 29, 0, tzinfo=timezone.utc), "Europe/Berlin", ["02:30"]) == datetime(2026, 3, 30, 0, 30, tzinfo=timezone.utc)
    first = publishing.next_slot(datetime(2026, 10, 25, 0, tzinfo=timezone.utc), "Europe/Berlin", ["02:30"])
    assert first == datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    assert publishing.next_slot(first, "Europe/Berlin", ["02:30"]).day == 26
    assert client.post("/publishing/jobs", json={"content_id":content_id,"platforms":["youtube"],"scheduled_at":"2026-10-01T09:00"}).status_code == 422
    assert client.put("/publishing/automation", json={"times":["25:00"]}).status_code == 422


def test_youtube_private_upload_and_no_duplicate_tick(live, monkeypatch):
    client, content_id = live
    calls = []
    original = httpx.Client
    def handler(request):
        calls.append(request)
        if request.method == "POST":
            assert b'"privacyStatus":"public"' in request.content
            return httpx.Response(200, headers={"Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test"})
        if request.headers.get("Content-Range", "").startswith("bytes */"):
            return httpx.Response(308)
        assert request.content == b"video-bytes"
        return httpx.Response(201, json={"id":"video-test","status":{"privacyStatus":"private"}})
    monkeypatch.setattr(publishing.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert schedule(client, content_id).status_code == 201
    publishing.tick()
    publishing.tick()
    result = client.get("/publishing/jobs").json()[0]
    assert result["status"] == "UPLOADED"
    assert result["remote_url"].endswith("video-test")
    assert "remote_key" not in result
    assert len(calls) == 3


def test_instagram_publish_timeout_is_not_retried(live, monkeypatch):
    client, content_id = live
    original = httpx.Client
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/media"):
            assert b"media_type=REELS" in request.content
            assert b"signature" in request.content
            return httpx.Response(200, json={"id":"container"})
        if request.method == "GET":
            return httpx.Response(200, json={"status_code":"FINISHED"})
        raise httpx.ReadTimeout("simulated timeout", request=request)
    monkeypatch.setattr(publishing.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    job_id = schedule(client, content_id, "instagram_reel").json()[0]["id"]
    publishing.tick()
    assert client.get("/publishing/jobs").json()[0]["status"] == "UNCERTAIN"
    publishing.tick()
    assert len(calls) == 3
    assert client.post(f"/publishing/jobs/{job_id}/retry").status_code == 409


def test_full_automatic_review_vs_approved_mode(live, monkeypatch):
    client, content_id = live
    original_client = httpx.Client
    monkeypatch.setattr(publishing.httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(lambda request: httpx.Response(500)), **kwargs))
    with SessionLocal() as db:
        db.get(ContentItem, content_id).status = ContentStatus.REVIEW
        db.commit()
    def setup(mode):
        assert client.put("/publishing/automation", json={"enabled":True,"mode":mode,"platforms":["youtube"]}).status_code == 200
        with SessionLocal() as db:
            db.get(AutomationSettings, 1).next_run = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
    setup("after_approval")
    publishing.tick()
    assert client.get("/publishing/jobs").json() == []
    setup("fully_automatic")
    def render(content_id, db):
        item = db.get(ContentItem, content_id)
        assert item.status == ContentStatus.APPROVED
        item.status = ContentStatus.VIDEO_READY
        db.commit()
        return item
    def publish(job, *args):
        job.status = "PUBLISHED"
    monkeypatch.setattr("app.main.render_content", render)
    monkeypatch.setattr(publishing, "youtube", publish)
    publishing.tick()
    assert client.get("/publishing/jobs").json()[0]["status"] == "PUBLISHED"
    assert client.get("/content/" + str(content_id)).json()["status"] == "VIDEO_READY"


def test_oauth_state_cookie_and_replay(live):
    client, _ = live
    response = client.post("/publishing/connections/youtube/connect")
    assert response.status_code == 200
    parsed = urlparse(response.json()["url"])
    state = parse_qs(parsed.query)["state"][0]
    start = client.get(parsed.path + "?" + parsed.query, follow_redirects=False)
    assert start.status_code == 303
    assert "HttpOnly" in start.headers["set-cookie"] and "Secure" in start.headers["set-cookie"]
    callback = "/oauth/youtube/callback?state=" + state + "&error=access_denied"
    assert client.get(callback, follow_redirects=False).status_code == 400
    result = client.get(callback, headers={"Cookie": "oauth_youtube=" + state}, follow_redirects=False)
    assert result.status_code == 303
    assert result.headers["location"] == "https://studio.example/?social=error"
    assert client.get(callback, headers={"Cookie": "oauth_youtube=" + state}, follow_redirects=False).status_code == 400
    body = client.get("/publishing/connections").text
    assert "test-access" not in body and "credentials" not in body


@pytest.mark.parametrize("provider", ["youtube", "instagram"])
def test_oauth_success_stores_encrypted_credentials(live, monkeypatch, provider):
    client, _ = live
    original = httpx.Client
    def handler(request):
        if request.url.path.endswith("/channels"):
            return httpx.Response(200, json={"items":[{"id":"new-channel","snippet":{"title":"My channel"}}]})
        if request.url.path.endswith("/me"):
            return httpx.Response(200, json={"user_id":"new-instagram","username":"my-account","account_type":"BUSINESS"})
        return httpx.Response(200, json={"access_token":"new-access-token","refresh_token":"new-refresh-token","expires_in":3600})
    monkeypatch.setattr(social.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    url = client.post(f"/publishing/connections/{provider}/connect").json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    result = client.get(f"/oauth/{provider}/callback?state={state}&code=test-code", headers={"Cookie":f"oauth_{provider}={state}"}, follow_redirects=False)
    assert result.status_code == 303 and result.headers["location"].endswith("?social=connected")
    with SessionLocal() as db:
        account = db.get(SocialAccount, provider)
        assert "new-access-token" not in account.credentials
        assert social.unseal(account.credentials)["access_token"] == "new-access-token"
    assert "new-access-token" not in client.get("/publishing/connections").text


def test_resumable_upload_uses_same_session(live, monkeypatch):
    client, content_id = live
    original = httpx.Client
    step = {"uploads":0,"sessions":0}
    def handler(request):
        if request.method == "POST":
            step["sessions"] += 1
            return httpx.Response(200, headers={"Location":"https://www.googleapis.com/upload/youtube/v3/videos?upload_id=one"})
        if request.headers.get("Content-Range", "").startswith("bytes */"):
            return httpx.Response(308, headers={"Range":"bytes=0-4"} if step["uploads"] else {})
        step["uploads"] += 1
        if step["uploads"] == 1:
            raise httpx.ReadTimeout("simulated interruption", request=request)
        assert request.content == b"-bytes"
        assert request.headers["Content-Range"] == "bytes 5-10/11"
        return httpx.Response(201, json={"id":"final-video","status":{"privacyStatus":"public"}})
    monkeypatch.setattr(publishing.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    job_id = schedule(client, content_id).json()[0]["id"]
    publishing.tick()
    assert client.get("/publishing/jobs").json()[0]["status"] == "UNCERTAIN"
    assert client.post(f"/publishing/jobs/{job_id}/retry").status_code == 200
    publishing.tick()
    assert client.get("/publishing/jobs").json()[0]["status"] == "PUBLISHED"
    assert step == {"sessions":1,"uploads":2}
