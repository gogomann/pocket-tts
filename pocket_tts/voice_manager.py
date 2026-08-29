import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import torch

from pocket_tts.models.tts_model import _import_model_state, _is_safetensors_source, export_model_state
from pocket_tts.utils.utils import _ORIGINS_OF_PREDEFINED_VOICES, get_predefined_voice

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus", ".aac"}

LANGUAGE_INFO = {
    "de": {"code": "de", "label": "Deutsch", "flag": "🇩🇪", "model": "german_24l"},
    "en": {"code": "en", "label": "Englisch", "flag": "🇬🇧", "model": "english"},
    "fr": {"code": "fr", "label": "Französisch", "flag": "🇫🇷", "model": "french_24l"},
    "es": {"code": "es", "label": "Spanisch", "flag": "🇪🇸", "model": "spanish_24l"},
    "it": {"code": "it", "label": "Italienisch", "flag": "🇮🇹", "model": "italian_24l"},
    "pt": {"code": "pt", "label": "Portugiesisch", "flag": "🇵🇹", "model": "portuguese_24l"},
}

BUILTIN_VOICE_LANGUAGES = {
    "juergen": "de",
    "estelle": "fr",
    "lola": "es",
    "giovanni": "it",
    "rafael": "pt",
}
for name in _ORIGINS_OF_PREDEFINED_VOICES.keys():
    if name not in BUILTIN_VOICE_LANGUAGES:
        BUILTIN_VOICE_LANGUAGES[name] = "en"


def sanitize_voice_name(name: str) -> str:
    """Sanitize voice name to be safe for filenames and URLs."""
    name = name.strip()
    name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)
    return name.lower()


def normalize_language_code(lang: str | None) -> str:
    if not lang:
        return "en"
    lang_clean = lang.lower().strip()
    if lang_clean in ("de", "german", "german_24l", "deutsch"):
        return "de"
    if lang_clean in ("en", "english", "english_2026-04", "english_2026-01", "englisch"):
        return "en"
    if lang_clean in ("fr", "french", "french_24l", "französisch"):
        return "fr"
    if lang_clean in ("es", "spanish", "spanish_24l", "spanisch"):
        return "es"
    if lang_clean in ("it", "italian", "italian_24l", "italienisch"):
        return "it"
    if lang_clean in ("pt", "portuguese", "portuguese_24l", "portugiesisch"):
        return "pt"
    return "en"


class VoiceManager:
    """Manages persistent custom voices with country/language grouping, model-specific safetensors caching, and in-memory caches."""

    def __init__(self, voices_dir: str | Path | None = None, tts_model: Any = None):
        if voices_dir is None:
            voices_dir = os.environ.get("VOICES_DIR") or os.environ.get("POCKET_TTS_VOICES_DIR") or "./voices"
        self.voices_dir = Path(voices_dir).resolve()
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.tts_model = tts_model
        self._state_cache: dict[str, Any] = {}
        self._custom_voices: dict[str, Path] = {}
        self._metadata_file = self.voices_dir / "voices_metadata.json"
        self._voice_metadata: dict[str, dict[str, Any]] = self._load_metadata()
        self.refresh_voices()

    def _load_metadata(self) -> dict[str, dict[str, Any]]:
        if self._metadata_file.exists():
            try:
                return json.loads(self._metadata_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Could not read voices_metadata.json: %s", e)
        return {}

    def _save_metadata(self) -> None:
        try:
            self._metadata_file.write_text(json.dumps(self._voice_metadata, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Could not save voices_metadata.json: %s", e)

    def set_model(self, tts_model: Any) -> None:
        self.tts_model = tts_model

    def refresh_voices(self) -> None:
        """Scan the voices directory for .safetensors files and audio files."""
        self._custom_voices.clear()
        if not self.voices_dir.exists():
            return

        # 1. Register all existing base .safetensors files (ignoring model-specific caches like _german_24l.safetensors)
        for p in self.voices_dir.glob("*.safetensors"):
            base_name = p.stem.lower()
            # If it's a specific cache file, get root voice name
            for suffix in ["_german_24l", "_english", "_french_24l", "_spanish_24l", "_italian_24l", "_portuguese_24l"]:
                if base_name.endswith(suffix):
                    base_name = base_name[: -len(suffix)]
                    break

            if base_name not in self._custom_voices:
                self._custom_voices[base_name] = p
                if base_name not in self._voice_metadata:
                    self._voice_metadata[base_name] = {"language": "de"}

        # 2. Check for audio files (primary source)
        for p in self.voices_dir.iterdir():
            if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS:
                voice_name = p.stem.lower()
                self._custom_voices[voice_name] = p
                if voice_name not in self._voice_metadata:
                    self._voice_metadata[voice_name] = {"language": "de"}

        self._save_metadata()

    def list_voices(self) -> dict[str, Any]:
        """List all available voices grouped by country/language."""
        self.refresh_voices()
        custom_list = []
        for name, path in sorted(self._custom_voices.items()):
            meta = self._voice_metadata.get(name, {})
            lang = normalize_language_code(meta.get("language", "de"))
            custom_list.append(
                {
                    "name": name,
                    "type": "custom",
                    "language": lang,
                    "flag": LANGUAGE_INFO.get(lang, {}).get("flag", "🌐"),
                    "format": path.suffix.lstrip("."),
                    "path": str(path.relative_to(self.voices_dir.parent) if path.is_relative_to(self.voices_dir.parent) else path),
                    "is_cached": True,
                }
            )

        builtin_list = []
        for name in sorted(_ORIGINS_OF_PREDEFINED_VOICES.keys()):
            lang = BUILTIN_VOICE_LANGUAGES.get(name, "en")
            builtin_list.append(
                {
                    "name": name,
                    "type": "builtin",
                    "language": lang,
                    "flag": LANGUAGE_INFO.get(lang, {}).get("flag", "🌐"),
                }
            )

        # Build voices grouped by country/language
        voices_by_language: dict[str, Any] = {}
        for code, info in LANGUAGE_INFO.items():
            lang_custom = [v for v in custom_list if v["language"] == code]
            lang_builtin = [v for v in builtin_list if v["language"] == code]
            voices_by_language[code] = {
                "code": code,
                "label": info["label"],
                "flag": info["flag"],
                "model": info["model"],
                "custom_voices": lang_custom,
                "builtin_voices": lang_builtin,
                "total": len(lang_custom) + len(lang_builtin),
            }

        return {
            "voices_dir": str(self.voices_dir),
            "languages": list(LANGUAGE_INFO.values()),
            "voices_by_language": voices_by_language,
            "custom_voices": custom_list,
            "builtin_voices": builtin_list,
            "total_custom": len(custom_list),
            "total_builtin": len(builtin_list),
        }

    def get_voice_language(self, voice: str | None) -> str:
        """Find designated language code for a voice."""
        if not voice:
            return "de" if self.tts_model and "german" in str(self.tts_model.origin) else "en"
        voice_key = voice.lower().strip()
        if voice_key in self._voice_metadata:
            return normalize_language_code(self._voice_metadata[voice_key].get("language"))
        if voice_key in BUILTIN_VOICE_LANGUAGES:
            return BUILTIN_VOICE_LANGUAGES[voice_key]
        return "en"

    def get_voice_state(self, voice: str | None) -> Any:
        """Get model state for voice name, adapting to the current model architecture (6L vs 24L)."""
        if self.tts_model is None:
            raise RuntimeError("TTSModel is not loaded in VoiceManager")

        if not voice:
            from pocket_tts.default_parameters import get_default_voice_for_language
            voice = get_default_voice_for_language(str(self.tts_model.origin))

        voice_key = voice.lower().strip()
        model_name = self.tts_model.origin.stem if (self.tts_model.origin is not None and hasattr(self.tts_model.origin, "stem")) else str(self.tts_model.origin or "default")
        cache_key = f"{voice_key}@{model_name}"

        # 1. In-memory cache
        if cache_key in self._state_cache:
            return self._state_cache[cache_key]
        if voice_key in self._state_cache:
            return self._state_cache[voice_key]

        # 2. Check model-specific safetensors file: {voice_key}_{model_name}.safetensors
        specific_safetensors = self.voices_dir / f"{voice_key}_{model_name}.safetensors"
        if specific_safetensors.exists():
            state = _import_model_state(specific_safetensors, self.tts_model.device)
            self._state_cache[cache_key] = state
            self._state_cache[voice_key] = state
            return state

        # 3. Check if raw audio exists in voices dir (best source for any architecture!)
        for ext in AUDIO_EXTENSIONS:
            audio_candidate = self.voices_dir / f"{voice_key}{ext}"
            if audio_candidate.exists():
                logger.info("Computing voice state for '%s' on model '%s'...", voice_key, model_name)
                state = self.tts_model.get_state_for_audio_prompt(audio_candidate, truncate=True)
                try:
                    export_model_state(state, specific_safetensors)
                    export_model_state(state, self.voices_dir / f"{voice_key}.safetensors")
                except Exception as e:
                    logger.warning("Could not export safetensors: %s", e)
                self._state_cache[cache_key] = state
                self._state_cache[voice_key] = state
                return state

        # 4. Check generic .safetensors (e.g. {voice_key}.safetensors)
        generic_safetensors = self.voices_dir / f"{voice_key}.safetensors"
        if generic_safetensors.exists():
            try:
                state = _import_model_state(generic_safetensors, self.tts_model.device)
                self._state_cache[cache_key] = state
                self._state_cache[voice_key] = state
                return state
            except Exception as e:
                logger.warning("Generic safetensors failed for '%s': %s", voice_key, e)

        # 5. Check built-in predefined voices
        if voice in _ORIGINS_OF_PREDEFINED_VOICES or voice_key in _ORIGINS_OF_PREDEFINED_VOICES:
            actual_name = voice if voice in _ORIGINS_OF_PREDEFINED_VOICES else voice_key
            state = self.tts_model._cached_get_state_for_audio_prompt(actual_name)
            self._state_cache[cache_key] = state
            return state

        # 6. Direct file / URL
        if (
            voice.startswith("http://")
            or voice.startswith("https://")
            or voice.startswith("hf://")
            or _is_safetensors_source(voice)
            or Path(voice).exists()
        ):
            state = self.tts_model.get_state_for_audio_prompt(voice, truncate=True)
            return state

        raise ValueError(f"Voice '{voice}' not found.")

    def add_voice(
        self,
        name: str,
        audio_bytes: bytes,
        filename: str | None = None,
        language: str = "de",
    ) -> dict[str, Any]:
        """Save new voice, convert to safetensors, cache in memory, and save country/language metadata."""
        if self.tts_model is None:
            raise RuntimeError("TTSModel is not loaded in VoiceManager")

        safe_name = sanitize_voice_name(name)
        if not safe_name:
            raise ValueError("Voice name cannot be empty")

        lang_code = normalize_language_code(language)
        suffix = Path(filename).suffix.lower() if filename else ".wav"
        if suffix not in AUDIO_EXTENSIONS and suffix != ".safetensors":
            suffix = ".wav"

        # Update metadata
        self._voice_metadata[safe_name] = {
            "name": safe_name,
            "language": lang_code,
            "filename": f"{safe_name}{suffix}",
        }
        self._save_metadata()

        model_name = self.tts_model.origin.stem if (self.tts_model.origin is not None and hasattr(self.tts_model.origin, "stem")) else str(self.tts_model.origin or "default")

        # If it's already a safetensors file:
        if suffix == ".safetensors":
            safetensors_dest = self.voices_dir / f"{safe_name}.safetensors"
            with open(safetensors_dest, "wb") as f:
                f.write(audio_bytes)
            state = _import_model_state(safetensors_dest, self.tts_model.device)
            self._custom_voices[safe_name] = safetensors_dest
            self._state_cache[f"{safe_name}@{model_name}"] = state
            return {
                "name": safe_name,
                "language": lang_code,
                "flag": LANGUAGE_INFO[lang_code]["flag"],
                "status": "created",
                "type": "safetensors",
                "path": str(safetensors_dest),
                "message": f"Voice '{safe_name}' ({LANGUAGE_INFO[lang_code]['label']}) registered successfully.",
            }

        # Save raw audio file
        raw_audio_dest = self.voices_dir / f"{safe_name}{suffix}"
        with open(raw_audio_dest, "wb") as f:
            f.write(audio_bytes)

        try:
            logger.info("Computing voice state for '%s' (%s) on model '%s'...", safe_name, lang_code, model_name)
            model_state = self.tts_model.get_state_for_audio_prompt(raw_audio_dest, truncate=True)
            safetensors_dest = self.voices_dir / f"{safe_name}.safetensors"
            export_model_state(model_state, safetensors_dest)
            specific_dest = self.voices_dir / f"{safe_name}_{model_name}.safetensors"
            try:
                export_model_state(model_state, specific_dest)
            except Exception:
                pass

            self._custom_voices[safe_name] = safetensors_dest
            self._state_cache[safe_name] = model_state
            self._state_cache[f"{safe_name}@{model_name}"] = model_state

            return {
                "name": safe_name,
                "language": lang_code,
                "flag": LANGUAGE_INFO[lang_code]["flag"],
                "status": "created",
                "type": "custom",
                "audio_path": str(raw_audio_dest),
                "safetensors_path": str(safetensors_dest),
                "message": f"Voice '{safe_name}' ({LANGUAGE_INFO[lang_code]['label']}) created and permanently saved.",
            }
        except Exception as e:
            if raw_audio_dest.exists():
                raw_audio_dest.unlink()
            raise RuntimeError(f"Failed to process voice audio: {e}") from e

    def delete_voice(self, name: str) -> dict[str, Any]:
        """Delete custom voice and metadata."""
        safe_name = sanitize_voice_name(name)
        if safe_name in _ORIGINS_OF_PREDEFINED_VOICES:
            raise ValueError(f"Cannot delete built-in voice '{name}'")

        deleted_files = []
        for p in list(self.voices_dir.glob(f"{safe_name}*")):
            if p.is_file():
                p.unlink()
                deleted_files.append(str(p))

        self._custom_voices.pop(safe_name, None)
        self._voice_metadata.pop(safe_name, None)
        self._save_metadata()

        # Clear cache entries matching voice
        for k in list(self._state_cache.keys()):
            if k == safe_name or k.startswith(f"{safe_name}@") or k.startswith(f"{safe_name}_"):
                self._state_cache.pop(k, None)

        if not deleted_files:
            raise FileNotFoundError(f"Custom voice '{name}' not found")

        return {
            "name": safe_name,
            "status": "deleted",
            "deleted_files": deleted_files,
            "message": f"Voice '{safe_name}' deleted successfully.",
        }
