# Voices Directory / Stimmen-Verzeichnis

In diesem Ordner können benutzerdefinierte Stimmen abgelegt werden:

## Unterstützte Formate:
1. **Audio-Dateien (`.wav`, `.mp3`, `.flac`, `.ogg`, `.m4a`):**
   - Legen Sie z. B. `mein_sprecher.wav` in diesen Ordner.
   - Beim Start des Servers (oder bei der ersten Anfrage) konvertiert Pocket-TTS diese Datei automatisch einmalig in `mein_sprecher.safetensors`.
   - Danach steht die Stimme sofort unter dem Namen `mein_sprecher` über die API und das Web-UI zur Verfügung.

2. **Pre-Exportierte Safetensors (`.safetensors`):**
   - Mit `pocket-tts export-voice audio.wav stimme.safetensors` erstellte Dateien können direkt hier abgelegt werden.
   - Werden blitzschnell (< 5 ms) ohne Vorberechnungszeit geladen.

## Verwendung via API:
- **Alle Stimmen auflisten:** `GET /voices`
- **Neue Stimme hochladen:** `POST /voices` (Form-Data: `name`, `file`)
- **Stimme löschen:** `DELETE /voices/{name}`
- **TTS mit Stimme generieren:** `POST /tts` (mit `voice="mein_sprecher"`) oder `POST /v1/audio/speech` (OpenAI-Format)
