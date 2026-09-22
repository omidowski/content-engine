# Mit dem Content Studio verbinden

Diese V1.1 ergänzt die ursprüngliche Engine um Token-Schutz, Video-Downloads,
Range-Anfragen für Safari und das Zurücksetzen einer Freigabe.

1. Python 3.11+, FFmpeg und die Pakete aus `pyproject.toml` installieren.
2. `.env.example` nach `.env` kopieren; einen langen zufälligen `ENGINE_API_TOKEN`
   lokal generieren und geheim halten. Für einen Server `APP_ENV=production` setzen.
3. Echte OpenAI-/ElevenLabs-Zugänge setzen. `ALLOW_DEMO_FALLBACK=false` verhindert,
   dass versehentlich stumme Demo-Videos statt echter Voice-overs erzeugt werden.
4. Engine mit genau einem Prozess starten:

   `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`

   Diese Bindung nur hinter einer Firewall bzw. einem HTTPS-Reverse-Proxy verwenden.
   Für rein lokale Tests stattdessen `--host 127.0.0.1` verwenden.
5. HTTPS-Zugang einrichten und Datenbank/OUTPUT_DIR persistent speichern.
6. Im privaten Site serverseitig `CONTENT_ENGINE_URL` (HTTPS) und
   `CONTENT_ENGINE_TOKEN` (derselbe Token als Secret) setzen und neu veröffentlichen.
7. Im Content Studio **Engine verbinden** öffnen und die Verbindung prüfen.

API-Keys gehören nicht in den Browser, Git oder Chat. Ein Server wurde nicht
automatisch für dich gebucht oder eingerichtet. Die Token-Prüfung schützt die
Engine auch dann, wenn ihre Adresse bekannt wird.

## Erweiterte Endpunkte

- `GET /content/{id}/video` – Video inline, mit HTTP-Range-Unterstützung
- `GET /content/{id}/video?download=1` – MP4-Download
- `POST /content/{id}/reopen` – zurück zu REVIEW, erneute Freigabe erforderlich

Alle Endpunkte verlangen bei gesetztem Token `Authorization: Bearer <token>`.
Hook, Hauptteil und CTA werden gemeinsam gerendert. V1 ist synchron und für einen
Prozess ausgelegt. Nach einem Verbindungsabbruch den Status erneut abrufen, bevor
du den Render-Auftrag wiederholst. Abgelehnte Entwürfe erst mit `/reopen` bearbeiten.

Demo-Ausgaben sind keine automatische Recherche. Quellen werden nur mitgegeben,
nicht heruntergeladen oder auf Wahrheitsgehalt geprüft. Untertitel-Timing ist
geschätzt, nicht wortgenau aus dem Voice-over ausgerichtet.
