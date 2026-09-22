from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal
from app.models import ContentItem, ContentStatus


def test_token_blocks_unauthorized_requests(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "engine_api_token", "test-token-not-a-real-secret")
    assert client.get("/content").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/content", headers={"Authorization": "Bearer test-token-not-a-real-secret"}).status_code == 200


def test_reopen_invalidates_approval(client):
    item = client.post("/content", json={"topic": "Ein Testvideo"}).json()
    client.post(f"/content/{item['id']}/approve", json={"approved": True})
    result = client.post(f"/content/{item['id']}/reopen")
    assert result.status_code == 200
    assert result.json()["status"] == "REVIEW"
    assert client.post(f"/content/{item['id']}/render").status_code == 409


def test_video_download_and_range(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "output_dir", tmp_path)
    item = client.post("/content", json={"topic": "Download Test"}).json()
    assert client.get(f"/content/{item['id']}/video").status_code == 409
    asset = tmp_path / "short.mp4"
    asset.write_bytes(b"test-video-content")
    with SessionLocal() as db:
        record = db.get(ContentItem, item["id"])
        record.status = ContentStatus.VIDEO_READY
        record.video_path = str(asset)
        db.commit()
    video = client.get(f"/content/{item['id']}/video?download=1")
    assert video.status_code == 200
    assert video.content == b"test-video-content"
    assert "attachment" in video.headers["content-disposition"]
    partial = client.get(f"/content/{item['id']}/video", headers={"Range": "bytes=0-3"})
    assert partial.status_code == 206
    assert partial.content == b"test"


def test_null_patch_does_not_destroy_content(client):
    item = client.post("/content", json={"topic": "Null-Felder"}).json()
    response = client.patch(f"/content/{item['id']}", json={"hook": None})
    assert response.status_code == 200
    assert response.json()["hook"] == item["hook"]
