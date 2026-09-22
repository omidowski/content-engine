# AI Content Engine V1

Eine ausführbare, human-reviewed Pipeline für vertikale Social Videos:

`Thema → Recherche/Quellen → Hook & Skript → Freigabe → Voice-over → 9:16 MP4`

## Was V1 kann

- FastAPI REST API mit OpenAPI-Dokumentation
- SQLAlchemy-Persistenz (SQLite sofort, PostgreSQL per Konfiguration)
- strukturierte Content-Ausgabe über OpenAI oder lokaler Demo-Fallback
- verpflichtendes Review-Gate vor Audio/Video
- ElevenLabs TTS oder lokales stummes Demo-Audio
- FFmpeg-Rendering als 1080×1920 MP4 mit eingebrannten Untertiteln
- nachvollziehbare Statusmaschine und Tests

V1.2 enthält automatische Veröffentlichung für Instagram Reels/Video-Stories und
YouTube. Einrichtung und Grenzen stehen in `PUBLISHING_SETUP.md`. Die Automatik
startet pausiert und benötigt einen persistenten Server sowie verbundene Konten.
Analytics und automatische Nachrichtenrecherche sind nicht enthalten.

## Schnellstart

Voraussetzungen: Python 3.11+ und FFmpeg.

```bash
cd ai-content-engine
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --reload
```

Öffne danach `http://127.0.0.1:8000/docs`.

Ohne API-Keys läuft die Engine automatisch im Demo-Modus. Für echte Generierung die Keys in `.env` setzen. Niemals `.env` committen.

## Beispiel-Workflow

```bash
# 1. Draft erstellen
curl -s -X POST http://127.0.0.1:8000/content \
  -H 'Content-Type: application/json' \
  -d '{"topic":"5 AI Agents für Unternehmen","language":"de"}'

# 2. Inhalt prüfen/ändern und freigeben
curl -s -X POST http://127.0.0.1:8000/content/1/approve \
  -H 'Content-Type: application/json' \
  -d '{"approved":true}'

# 3. Audio und MP4 erzeugen
curl -s -X POST http://127.0.0.1:8000/content/1/render
```

Die Dateien landen standardmäßig in `output/<content-id>/`.

## API

| Methode | Route | Zweck |
|---|---|---|
| `GET` | `/health` | Konfiguration/Abhängigkeiten prüfen |
| `POST` | `/content` | Draft und Quellen erzeugen |
| `GET` | `/content` | Inhalte auflisten |
| `GET` | `/content/{id}` | Inhalt abrufen |
| `PATCH` | `/content/{id}` | Draft vor Freigabe bearbeiten |
| `POST` | `/content/{id}/approve` | Freigeben oder ablehnen |
| `POST` | `/content/{id}/render` | Voice und MP4 rendern |

## PostgreSQL

```env
DATABASE_URL=postgresql+psycopg://content:content@localhost:5432/content
```

Dann `pip install -e '.[postgres,dev]'` ausführen. Für Produktion gehören Schema-Migrationen (Alembic), Authentifizierung, Object Storage und ein Job-Queue-System in Sprint 2.

## Tests

```bash
pytest
```

## Sicherheits- und Qualitätsgrenzen

- Quellen werden in V1 aus explizit übergebenen URLs/Notizen oder aus der Modellantwort übernommen; sie sind **kein Beweis**, dass eine Aussage stimmt.
- Vor jeder Freigabe Quellen öffnen und Fakten prüfen, besonders bei News, Politik, Gesundheit und Finanzen.
- Nur Medien verwenden, für die Nutzungsrechte vorliegen.
- Stimmen nur mit Zustimmung klonen/nutzen und synthetische Inhalte plattformgerecht kennzeichnen.
- Plattform-Tokens und API-Keys ausschließlich als Secrets speichern.
