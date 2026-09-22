# Omid · Content Studio

Responsive Web-Oberfläche zur AI Content Engine V1, für iPhone und Desktop.

## Enthalten

- deutscher Workspace mit Entwurfsübersicht, Hook-/Skript-/CTA-Editor
- separate Beitrag- und Quellenansicht, Wortzahl und grobe Sprechdauer
- manuelle Freigabe im Editor; optional vollautomatische Verarbeitung im Zeitplan
- Textvorschau, MP4-Wiedergabe mit `playsInline`, Download und JSON-Export
- deutlich gekennzeichneter Demo-Modus: nur im Arbeitsspeicher dieses Tabs
- serverseitiger, auf bekannte Routen begrenzter Proxy zur FastAPI-Engine
- Engine-Erweiterung: Bearer-Token, Video-/Range-Download, Freigabe zurücksetzen
- Veröffentlichungsplanung für Instagram Reels/Video-Stories und YouTube
- OAuth-Kontoverbindung, verschlüsselte Tokens und persistente Veröffentlichungsjobs
- keine API-Schlüssel im Browser; Livebetrieb benötigt die eingerichtete Engine

## Neu in V1.2

Unter „Veröffentlichen & planen“ findest du Einzeltermine, tägliche Slots mit
Zeitzone, die Warteschlange und Kontoverbindungen. Nach Freigabe verarbeitet die
Automatik freigegebene Inhalte; vollautomatisch auch bestehende Live-Entwürfe.
Sie recherchiert und erstellt keine neuen Nachrichten oder Themen.

Die Oberfläche funktioniert auch ohne Engine als klar gekennzeichnete Vorschau.
Die Automatik ist noch nicht live aktiviert. Server, Plattform-Apps und echte
Kontoverbindungen fehlen. Vollständige Einrichtung: `engine/PUBLISHING_SETUP.md`.
Der Download `public/content-engine-v1.2.zip` enthält den aktuellen Engine-Code.

## Was sofort funktioniert

Ohne Server-Konfiguration ist der Demo-Modus aktiv. Du kannst einen Beispielentwurf
erstellen, bearbeiten, für die aktuelle Sitzung speichern, prüfen und freigeben.
Die Wiedergabe zeigt ein festes, stummes FFmpeg-Beispiel, **kein neu generiertes Video
deines geänderten Skripts**. Das Beispielvideo kann heruntergeladen werden.
Demo-Entwürfe gehen beim Neuladen verloren; nutze vorher den JSON-Export.

Die Textvorschau ist eine Vorschau des Skripts, keine verbindliche Darstellung des
FFmpeg-Layouts. Die V1-Engine erzeugt einen einfachen Hintergrund und Untertitel.
Untertitel sind zeitlich geschätzt, nicht per Forced Alignment synchronisiert.

## Echte Produktion verbinden

Die Web-Oberfläche läuft als privater Site-Worker. Python, SQLAlchemy und FFmpeg
laufen auf einem separaten Server; sie werden nicht innerhalb des Workers ausgeführt.
Ein solcher Server wurde mit dieser Oberfläche **nicht automatisch bereitgestellt**.

1. Aktuelle Engine aus `engine/` auf einem eigenen Server mit Python 3.11+ und FFmpeg
   starten. Nicht das unveränderte V1-ZIP verwenden: Video-Download, Token-Schutz und
   `/reopen` sind in dieser Erweiterung enthalten.
2. Einen langen zufälligen Token generieren und als `ENGINE_API_TOKEN` der Engine
   hinterlegen. Außerhalb lokaler Entwicklung `APP_ENV=production` verwenden.
3. OpenAI- und ElevenLabs-Variablen gemäß `engine/.env.example` setzen.
   `ALLOW_DEMO_FALLBACK=false` verhindert versehentliche stumme Videos im Echtbetrieb.
4. Den Server hinter HTTPS betreiben. SQLite und `OUTPUT_DIR` auf einem persistenten
   Volume speichern. Für V1 genau **einen Uvicorn-Prozess** verwenden.
5. Serverseitige Site-Variablen setzen:

   - `CONTENT_ENGINE_URL`: HTTPS-Basisadresse ohne abschließenden API-Pfad
   - `CONTENT_ENGINE_TOKEN`: derselbe Token, als Secret

6. Site mit den neuen Einstellungen veröffentlichen; im Studio auf
   **Engine verbinden → Verbindung prüfen & verbinden** klicken.

Die Oberfläche liest dann bestehende Datensätze von der Engine. Demo-Entwürfe werden
nicht automatisch übertragen. Alle AI-Anbieterzugänge verbleiben bei der Engine.
Der private Site-Zugriff ist die Benutzer-Autorisierung; diese Einbenutzer-Version
nicht öffentlich freigeben. Mehrmandantenfähigkeit ist nicht implementiert.

### Engine lokal starten

```bash
cd engine
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Für Windows: `.venv\Scripts\activate` statt `source …`.
Lokales HTTP ist für Python-Entwicklung möglich; der veröffentlichte Site-Proxy
akzeptiert absichtlich nur HTTPS und einen Token.

Ein Dockerfile ist in `engine/` enthalten. API-Tokens über Secret-Management oder
eine lokale Env-Datei übergeben, nicht in ein Image oder Git einbauen. `/data` als
persistent beschreibbares Volume für den Benutzer `studio` einbinden.

### Oberfläche entwickeln

```bash
pnpm install --frozen-lockfile
pnpm dev
```

In ChatGPT Work wird der verwaltete Vorschauprozess verwendet. Die Konfiguration
für Sites befindet sich in `.openai/hosting.json`; Secrets stehen dort niemals.

## API-Ablauf

`POST /content → PATCH /content/{id} → POST /content/{id}/approve → POST /content/{id}/render`

- `GET /content/{id}/video`: MP4 inline mit Range-Unterstützung für Safari
- `GET /content/{id}/video?download=1`: Datei herunterladen
- `POST /content/{id}/reopen`: zurück zu REVIEW, Freigabe und Dateiverweise invalidieren
- bestehende Dateien bleiben bis zum nächsten Render bestehen; es wird nichts gelöscht

Hook, Hauptteil und CTA werden gemeinsam vertont und untertitelt. Ein laufender
Render blockiert weitere Render-/Reopen-Anfragen im selben Prozess. V1 ist eine
Einprozess-Pipeline mit persistenter Publishing-Queue. Objektstorage und mehrere
Worker sind nicht implementiert. Bei Verbindungsabbruch kann
der Server weiterarbeiten: Status neu laden, bevor ein Render erneut gestartet wird.

Quellenlinks werden nicht automatisch abgerufen. Das Modell erhält nur die
übergebenen Notizen. Es gibt keine automatische Faktenprüfung.

## Prüfen

```bash
pnpm exec tsc --noEmit
cd engine
pytest
```

`python render_demo.py` regeneriert das stumme Beispielvideo ohne bezahlte API-Aufrufe.
Die Browser-Tools `read_content_studio` und `start_short_draft` sind optional per
WebMCP verfügbar. Sie umgehen weder Freigaben noch Authentifizierung.
