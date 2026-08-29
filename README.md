# Pocket TTS Studio 🎙️

<img width="1446" height="622" alt="pocket-tts-logo-v2-transparent" src="https://github.com/user-attachments/assets/637b5ed6-831f-4023-9b4c-741be21ab238" />

Lokale, CPU-basierte Sprachgenerierung mit permanentem Voice Cloning, Multi-Language-Unterstützung (Deutsch 24-Layer Qualitätsmodell, Englisch, Französisch, Spanisch, Italienisch, Portugiesisch) und modernem Web-UI.

---

## 🚀 Schnellanleitung nach dem Klonen von Git

Klone das Repository und wechsle in den Ordner:
```bash
git clone <dein-repository-link>
cd pocket-tts
```

Du kannst die Anwendung entweder im **Docker-Container** (empfohlen) oder **direkt lokal mit Python** starten:

---

### 🐳 Option A: In Docker ausführen (Mac, Windows & Linux)
*Keine lokale Python-Installation nötig – benötigt nur Docker Desktop.*

#### 🍏 macOS & 🐧 Linux:
```bash
./start.sh
```
*(Zum Stoppen: `./stop.sh`)*

#### 🪟 Windows:
Einfach Doppelklick auf **`start.bat`** (oder im Terminal `.\start.bat` bzw. `.\start.ps1` ausführen).
*(Zum Stoppen: Doppelklick auf `stop.bat`)*

#### 🔧 Manuell mit Docker Compose (alle Betriebssysteme):
```bash
docker compose up -d --build
```

👉 Öffne anschließend im Browser: **[http://localhost:8000](http://localhost:8000)**

---

### 💻 Option B: Direkt lokal ausführen (ohne Docker)

#### Variante 1: Mit `uv` (Empfohlen, extrem schnell & isoliert)
1. Falls noch nicht vorhanden, `uv` installieren:
   - **macOS / Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - **Windows:** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. Server starten (installiert automatisch alle Abhängigkeiten isoliert):
   ```bash
   uv run pocket-tts serve
   ```

#### Variante 2: Mit Standard-Python (`pip`)
```bash
# 1. Virtuelle Umgebung erstellen (Python 3.10+)
python3 -m venv .venv

# 2. Aktivieren
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate       # Windows

# 3. Paket installieren
pip install -e .

# 4. Server starten
pocket-tts serve
```

👉 Öffne anschließend im Browser: **[http://localhost:8000](http://localhost:8000)**

---

## 🔑 Optional: Eigenes Voice Cloning aktivieren
* Die 26 integrierten Stimmen funktionieren **sofort ohne Login oder Token**.
* Wenn du **eigene Stimmen anlernen / hochladen** möchtest:
  1. Akzeptiere die Bedingungen auf Hugging Face: [https://huggingface.co/kyutai/pocket-tts](https://huggingface.co/kyutai/pocket-tts)
  2. **In Docker:** Trage deinen Token in die Datei `.env` ein (`HF_TOKEN=hf_...`).
  3. **Lokal:** Führe einmalig `uvx hf auth login` oder `huggingface-cli login` aus.

---

## 📁 Ordner & Datenablage
* **[`voices/`](file:///Users/mac-gogomann/_dev/__tool/audio/pocket-tts/voices)**: Enthält die dauerhaft gespeicherten Stimmen (`.wav`, `.mp3`) und Metadaten. Neue Stimmen können auch direkt im Web-Interface hochgeladen werden.
* **[`fertige_files/`](file:///Users/mac-gogomann/_dev/__tool/audio/pocket-tts/fertige_files)**: Jede generierte Audiodatei (`.wav`) und die dazugehörige Konfigurations- und Logdatei (`_config.txt`) werden hier automatisch archiviert.

---

## 🎛️ Features im Web-Interface
* **🌍 Länder-Gruppierung:** Stimmen nach Ländern sortiert (🇩🇪 Deutsch, 🇬🇧 Englisch, 🇫🇷 Französisch, 🇪🇸 Spanisch, 🇮🇹 Italienisch, 🇵🇹 Portugiesisch).
* **⚡ Klangregler im Dropdown:** Geschwindigkeit (`0.5x` - `2.0x`), Tonhöhe (`-6` bis `+6` Halbtöne), Lebendigkeit/Expressivität und Decoder-Schritte.
* **📄 Download:** Direkter Download des Audios sowie der Konfigurations- & Logdatei.
* **🔌 API-Endpunkte:** Kompatibel mit OpenAI Speech (`POST /v1/audio/speech`) sowie `POST /tts`.
