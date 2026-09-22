# Content Engine V1.2 – Veröffentlichung einrichten

Implementiert: Instagram Reels (auch im Feed), Video-Stories für Business-Konten,
YouTube-Videos/Shorts, OAuth-Kontoverbindung, verschlüsselte Token, persistente
Warteschlange, Einzeltermine und tägliche Zeitpläne. Diese Erweiterung verarbeitet
vorhandene Inhalte. Sie recherchiert keine Nachrichten und erzeugt keine neuen
Themen automatisch. Bildbeiträge, Karussells und eigenständige Audio-Podcasts sind
nicht Teil dieser Video-Engine.

## 1. Server auf Railway

Den Inhalt dieses Engine-Verzeichnisses in ein vom Nutzer bestätigtes privates
GitHub-Repository übertragen. Bei einem Repository mit der gesamten Web-App in
Railway das Root Directory `/engine` und die Konfigurationsdatei
`/engine/railway.toml` wählen. Bei einem reinen Engine-Repository liegen Dockerfile
und railway.toml im Repository-Wurzelverzeichnis.

- Einen Service mit genau **einer Replik und einem Uvicorn-Worker** verwenden.
- Ein persistentes Volume unter `/data` anbinden. SQLite, OAuth-Verbindungen,
  Zeitpläne, Jobs und Videos liegen darauf. Regelmäßige Backups einrichten.
- Railway mountet Volumes als root: `RAILWAY_RUN_UID=0` setzen, wenn das
  Containerkonto sonst keinen Zugriff auf das Volume hat.
- `APP_ENV=production`, `ALLOW_DEMO_FALLBACK=false`,
  `DATABASE_URL=sqlite:////data/content.db`, `OUTPUT_DIR=/data/output`.
- `ENGINE_API_TOKEN` als zufälliges Secret setzen. Derselbe Wert muss im Studio
  als `CONTENT_ENGINE_TOKEN` hinterlegt sein.
- HTTPS-Domain erzeugen und als `PUBLIC_ENGINE_URL` setzen. Im Studio diese
  Adresse als `CONTENT_ENGINE_URL` eintragen.
- Healthcheck `/ready` ist öffentlich und enthält nur den Bereitschaftsstatus.
  `/health` und alle Content-/Publishing-Endpunkte benötigen Bearer-Auth.
- Access-Logs deaktiviert lassen: OAuth-Codes und signierte Medien-URLs dürfen
  nicht in Serverzugriffsprotokollen landen. Auch beim vorgeschalteten Proxy
  Query-Strings dieser Routen nicht protokollieren.
- `PUBLISHING_WORKER_ENABLED=true` startet den Hintergrunddienst. Die tägliche
  Automatik bleibt bis zur Aktivierung im Studio pausiert.

`railway.toml` und Dockerfile sind vorbereitet. Ohne Repository und API-Zugänge
kann diese Anleitung keinen laufenden Server oder Plattformfreigaben ersetzen.

## 2. AI und Verschlüsselung

OpenAI- und ElevenLabs-Zugangsdaten gemäß `.env.example` serverseitig setzen.
Die Engine blockiert Veröffentlichungen, solange Demo-Fallback erlaubt ist.
Auch früher erzeugte Demo-Ausgaben bleiben gesperrt, wenn später Keys ergänzt
werden. Bestehende Ausgaben ohne Herkunftsnachweis ebenfalls neu erzeugen.

`TOKEN_ENCRYPTION_KEY` einmal mit `Fernet.generate_key()` aus `cryptography.fernet`
erzeugen und als Server-Secret speichern. Diesen Schlüssel nicht bei jedem
Deployment ändern. Die Datenbank enthält ausschließlich verschlüsselte
OAuth-Zugangsdaten. Den Schlüssel getrennt von Datenbankbackups sichern.

## 3. YouTube verbinden

In Google Cloud die YouTube Data API v3 aktivieren und einen OAuth-Client vom
Typ Webanwendung anlegen. Client-ID und Secret als `GOOGLE_CLIENT_ID` und
`GOOGLE_CLIENT_SECRET` hinterlegen. Den OAuth-Zustimmungsbildschirm und bei
Testbetrieb den eigenen Google-Nutzer als Testnutzer konfigurieren.

Exakte Redirect-URI: `https://DEINE-ENGINE-DOMAIN/oauth/youtube/callback`.
Das Studio fordert `youtube.upload` und `youtube.readonly` an, prüft den
gewählten Kanal und speichert einen Refresh-Token. Danach im Studio unter
„Veröffentlichen & planen → Konten → YouTube“ anmelden.

Neue ungeprüfte API-Projekte können Uploads nur privat veröffentlichen. Das
YouTube-API-Audit für öffentliche Uploads ist von der OAuth-Verifizierung
getrennt. Testmodus kann zeitlich begrenzte Refresh-Tokens verursachen.
Die App zeigt bei nicht bestätigter öffentlicher Sichtbarkeit „Hochgeladen“
anstatt „Veröffentlicht“ an. Ob YouTube ein Video als Short einordnet,
entscheidet YouTube anhand seiner Formatregeln.

## 4. Instagram verbinden

Eine Meta-App mit **Instagram API with Instagram Login** einrichten. Die
Instagram-App-ID und das zugehörige Secret als `INSTAGRAM_CLIENT_ID` und
`INSTAGRAM_CLIENT_SECRET` setzen. Kein Facebook-Login-Token verwenden.
Business- oder Creator-Konto hinzufügen; Stories benötigen ein Business-Konto.

Exakte Redirect-URI: `https://DEINE-ENGINE-DOMAIN/oauth/instagram/callback`.
Benötigte Scopes: `instagram_business_basic`,
`instagram_business_content_publish`. Für Konten außerhalb der zulässigen
App-Rollen ist die entsprechende Meta-Prüfung nötig. Die API-Version ist über
`INSTAGRAM_API_VERSION` konfigurierbar. Der initiale Stand ist `v25.0`.

Im Studio Instagram verbinden. Kurzlebige Tokens werden serverseitig in
langlebige Tokens getauscht; vor Ablauf wird eine Verlängerung versucht.
Instagram lädt nur das geplante Video über einen signierten, eine Stunde
gültigen Medienlink. Alle anderen Inhalte bleiben geschützt.

## 5. Ablauf und Fehlerbehandlung

- **Nach Freigabe:** ältester freigegebener, noch ungeplanter Inhalt pro Slot.
- **Vollautomatisch:** auch vorhandene Live-Entwürfe im Status REVIEW werden
  ohne Einzelprüfung freigegeben, gerendert und veröffentlicht.
- Kein passender Inhalt: Slot wird übersprungen und im Studio erläutert.
- Sommerzeit: nicht existierende Uhrzeiten werden übersprungen, doppelte
  Herbst-Uhrzeiten einmal ausgeführt. Verpasste Slots werden nicht nachgeholt.
- Ein Slot bedeutet frühester Verarbeitungsbeginn, keine sekundengenaue
  Veröffentlichung. Rendering und Plattformverarbeitung können Minuten dauern.
- Pro Inhalt/Plattform genau ein Job. Erneutes Klicken erzeugt keine Doppelposts.
- Geplante oder laufende Inhalte sind gegen Bearbeitung gesperrt. Wartende Jobs
  zuerst stornieren. Nach einer Inhaltsänderung lässt sich der alte Job nicht
  erneut starten; dafür einen neuen Entwurf erstellen.
- Vollständige Provider-Fehlermeldungen werden nicht an Browser oder Logs gegeben.
- Bei unklarem Ergebnis nach einem Schreibzugriff Status UNCERTAIN statt blindem
  Retry. YouTube kann dieselbe gespeicherte Upload-Sitzung prüfen und fortsetzen.
  Unklare Instagram-Veröffentlichungen müssen auf Instagram geprüft werden;
  die App sendet sie nicht automatisch erneut.
- Neu gestartete Server markieren unterbrochene Jobs als UNCERTAIN.
- Fehlgeschlagene Jobs können gezielt erneut gestartet werden. Es gibt keine
  unbegrenzten automatischen Wiederholungen.
- Pausieren stoppt neue automatische Jobs; bereits geplante Einzeljobs bleiben.
- Konto trennen entfernt lokale Tokens, storniert wartende Plattform-Jobs und
  pausiert den Zeitplan. Anbieterberechtigungen separat beim Anbieter widerrufen.

Die Tests verwenden simulierte Plattformantworten. Ein echter OAuth-Durchlauf,
echte Uploads, App-Reviews und Railway-Betrieb müssen mit den tatsächlichen
Konten und Zugängen geprüft werden. Noch keine solchen Tests durchgeführt.

## Primärquellen

- https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
- https://developers.google.com/youtube/v3/docs/videos/insert
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login
- https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
- https://docs.railway.com/volumes

## Validierung

`python -m pytest` prüft den Produktionsablauf, Freigaben, OAuth-State/Cookie und
Replay-Schutz, signierten Medienzugriff, Doppelpost-Schutz, Demo-Sperre,
Sommerzeit, private YouTube-Uploads und unsichere Instagram-Antworten.
