from pathlib import Path


def test_create_edit_and_approve(client):
    created = client.post("/content", json={"topic": "AI Agents für Unternehmen", "language": "de"})
    assert created.status_code == 201
    item = created.json()
    assert item["status"] == "REVIEW"
    assert item["topic"] == "AI Agents für Unternehmen"

    updated = client.patch(f"/content/{item['id']}", json={"hook": "Ein besserer, geprüfter Hook"})
    assert updated.status_code == 200
    assert updated.json()["hook"] == "Ein besserer, geprüfter Hook"

    approved = client.post(f"/content/{item['id']}/approve", json={"approved": True})
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    blocked = client.patch(f"/content/{item['id']}", json={"hook": "Das darf nicht gehen"})
    assert blocked.status_code == 409


def test_render_requires_approval(client):
    item = client.post("/content", json={"topic": "Sicherer Workflow", "language": "de"}).json()
    response = client.post(f"/content/{item['id']}/render")
    assert response.status_code == 409


def test_full_demo_render_when_ffmpeg_exists(client):
    health = client.get("/health").json()
    if not health["ffmpeg_available"]:
        return
    item = client.post("/content", json={"topic": "Content Automation", "language": "en"}).json()
    client.post(f"/content/{item['id']}/approve", json={"approved": True})
    rendered = client.post(f"/content/{item['id']}/render")
    assert rendered.status_code == 200, rendered.text
    result = rendered.json()
    assert result["status"] == "VIDEO_READY"
    assert Path(result["video_path"]).exists()

