import datetime
import io
import logging
import os
import re
import sys
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import typer
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing_extensions import Annotated

from pocket_tts.data.audio import stream_audio_chunks
from pocket_tts.data.audio_effects import apply_audio_effects
from pocket_tts.default_parameters import (
    DEFAULT_EOS_THRESHOLD,
    DEFAULT_FRAMES_AFTER_EOS,
    DEFAULT_NOISE_CLAMP,
    DEFAULT_SAMPLER_DECODE_STEPS,
    MAX_TOKEN_PER_CHUNK,
    get_default_text_for_language,
    get_default_voice_for_language,
)
from pocket_tts.models.tts_model import TTSModel
from pocket_tts.utils.utils import _ORIGINS_OF_PREDEFINED_VOICES
from pocket_tts.voice_manager import LANGUAGE_INFO, VoiceManager, normalize_language_code

logger = logging.getLogger(__name__)

cli_app = typer.Typer(
    help="Kyutai Pocket TTS - Text-to-Speech generation tool", pretty_exceptions_show_locals=False
)

# ------------------------------------------------------
# State and Model Pool
# ------------------------------------------------------

tts_model: Any = None
voice_manager: Any = None
loaded_models: dict[str, Any] = {}
output_dir: Path = Path(os.environ.get("OUTPUT_DIR") or os.environ.get("FERTIGE_FILES_DIR") or "./fertige_files").resolve()
output_dir.mkdir(parents=True, exist_ok=True)


def get_model_name_for_code(code: str) -> str:
    lang = normalize_language_code(code)
    return LANGUAGE_INFO.get(lang, {}).get("model", "english")


def get_tts_model(language_or_code: str | None = None) -> Any:
    """Get or dynamically load the TTSModel for a specific language."""
    global tts_model, loaded_models
    lang_code = normalize_language_code(language_or_code)
    model_name = get_model_name_for_code(lang_code)

    if model_name in loaded_models:
        return loaded_models[model_name]

    device = os.environ.get("DEVICE", "cpu")
    quantize = os.environ.get("QUANTIZE", "0").lower() in ("1", "true", "yes")

    logger.info("Loading model '%s' for language '%s' on %s...", model_name, lang_code, device)
    try:
        model = TTSModel.load_model(language=model_name, quantize=quantize)
    except Exception as e:
        logger.warning("Could not load model '%s', falling back to default: %s", model_name, e)
        if tts_model is not None:
            return tts_model
        model = TTSModel.load_model(language="english", quantize=quantize)

    model.to(device)
    loaded_models[model_name] = model
    if tts_model is None:
        tts_model = model
    return model


def ensure_initialized():
    """Ensure at least default model and voice manager are initialized."""
    global tts_model, voice_manager, output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if tts_model is None:
        default_lang = os.environ.get("DEFAULT_LANGUAGE") or os.environ.get("LANGUAGE") or "german_24l"
        tts_model = get_tts_model(default_lang)

    if voice_manager is None:
        voices_dir = os.environ.get("VOICES_DIR") or os.environ.get("POCKET_TTS_VOICES_DIR") or "./voices"
        voice_manager = VoiceManager(voices_dir=voices_dir, tts_model=tts_model)
    elif voice_manager.tts_model is None:
        voice_manager.set_model(tts_model)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_initialized()
    yield


# ------------------------------------------------------
# Request Models
# ------------------------------------------------------

class TTSRequest(BaseModel):
    text: str = Field(..., description="Text to convert to speech")
    voice: Optional[str] = Field(None, description="Name of custom voice or built-in voice")
    language: Optional[str] = Field(None, description="Language code (de, en, fr, es, it, pt)")
    speed: Optional[float] = Field(default=1.0, description="Speech rate (0.5 to 2.0)")
    pitch: Optional[float] = Field(default=0.0, description="Pitch shift in semitones (-12 to +12)")
    temperature: Optional[float] = Field(default=None, description="Expression/dynamic temperature (0.1 to 1.5)")
    sampler_decode_steps: Optional[int] = Field(default=None, description="Decode steps (1 to 4)")
    frames_after_eos: Optional[int] = Field(default=None, description="Sentence pause padding (1 to 5)")
    voice_url: Optional[str] = Field(None, description="Optional voice URL (http://, https://, hf://)")


class OpenAISpeechRequest(BaseModel):
    model: str = Field(default="pocket-tts", description="Model identifier")
    input: str = Field(..., description="Text to speak")
    voice: str = Field(default="default", description="Voice name (custom or built-in)")
    language: Optional[str] = Field(default=None, description="Language code")
    response_format: Optional[str] = Field(default="wav", description="Audio format (wav supported)")
    speed: Optional[float] = Field(default=1.0, description="Speech rate factor (0.5 to 2.0)")


# ------------------------------------------------------
# FastAPI Web App
# ------------------------------------------------------

web_app = FastAPI(
    title="Kyutai Pocket TTS API",
    description="Text-to-Speech API with persistent voice management, multi-language routing, audio tuning & archiving",
    version="1.2.0",
    lifespan=lifespan,
)
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def save_generation_record(
    audio_bytes: bytes,
    text: str,
    voice_name: str,
    language_code: str,
    model_name: str,
    speed: float,
    pitch: float,
    temperature: float,
    sampler_decode_steps: int,
    frames_after_eos: int,
    duration_sec: float,
    processing_time_sec: float,
) -> tuple[str, Path, Path]:
    """Save the generated audio file and its config/log file in fertige_files."""
    now = datetime.datetime.now(datetime.timezone.utc)
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:6]
    clean_voice = re.sub(r"[^a-zA-Z0-9_\-]", "_", voice_name or "default")
    file_id = f"tts_{ts_str}_{clean_voice}_{uid}"

    wav_file = output_dir / f"{file_id}.wav"
    config_file = output_dir / f"{file_id}_config.txt"

    wav_file.write_bytes(audio_bytes)

    rtf = duration_sec / max(processing_time_sec, 0.001)
    config_content = f"""================================================================================
                       POCKET-TTS GENERATION CONFIG & LOG
================================================================================
File ID:          {file_id}
Date & Time UTC:  {now.strftime('%Y-%m-%d %H:%M:%S UTC')}
Audio File:       {wav_file.name}
Text:             "{text}"

---------------------------- CONFIGURATION -------------------------------------
Language Code:    {language_code} ({LANGUAGE_INFO.get(language_code, {}).get('label', 'Unknown')})
Model:            {model_name}
Voice:            {voice_name}
Speed Factor:     {speed:.2f}x
Pitch Shift:      {pitch:+.1f} semitones
Temperature:      {temperature}
Decode Steps:     {sampler_decode_steps}
Frames after EOS: {frames_after_eos}
Sample Rate:      24000 Hz

---------------------------- GENERATION LOG ------------------------------------
Processing Time:  {processing_time_sec:.2f} seconds
Audio Duration:   {duration_sec:.2f} seconds
Real-Time Factor: {rtf:.2f}x faster than real-time
Status:           SUCCESS
================================================================================
"""
    config_file.write_text(config_content, encoding="utf-8")
    logger.info("Saved output to %s and config to %s", wav_file, config_file)
    return file_id, wav_file, config_file


@web_app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the web interface."""
    ensure_initialized()
    static_path = Path(__file__).parent / "static" / "index.html"
    content = static_path.read_text(encoding="utf-8")
    default_text = get_default_text_for_language(str(tts_model.origin)) if tts_model and tts_model.origin else "Hallo Welt, willkommen bei Pocket TTS!"
    content = content.replace("DEFAULT_TEXT_PROMPT", default_text)
    return content


@web_app.get("/health")
async def health():
    ensure_initialized()
    voice_info = voice_manager.list_voices() if voice_manager else {}
    return {
        "status": "healthy",
        "active_model": str(tts_model.origin) if tts_model else None,
        "device": str(tts_model.device) if tts_model else None,
        "sample_rate": tts_model.sample_rate if tts_model else 24000,
        "loaded_models": list(loaded_models.keys()),
        "total_custom_voices": voice_info.get("total_custom", 0),
        "total_builtin_voices": voice_info.get("total_builtin", 0),
        "output_dir": str(output_dir),
    }


@web_app.get("/languages")
async def list_languages():
    """List all available languages and country groupings."""
    return list(LANGUAGE_INFO.values())


@web_app.get("/voices")
async def list_voices():
    """List all available voices grouped by country/language."""
    ensure_initialized()
    return voice_manager.list_voices()


@web_app.post("/voices")
@web_app.post("/voices/add")
async def add_voice(
    name: str = Form(..., description="Unique name for the voice"),
    file: UploadFile = File(..., description="Audio file (WAV, MP3, FLAC, OGG) or .safetensors"),
    language: str = Form("de", description="Country/language code: de, en, fr, es, it, pt"),
):
    """Upload a new voice audio file. It is permanently saved and assigned to a country/language."""
    ensure_initialized()
    if not name.strip():
        raise HTTPException(status_code=400, detail="Voice name cannot be empty")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        result = voice_manager.add_voice(
            name=name,
            audio_bytes=content,
            filename=file.filename,
            language=language,
        )
        return JSONResponse(status_code=201, content=result)
    except Exception as e:
        logger.error("Error adding voice '%s': %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


@web_app.delete("/voices/{voice_name}")
async def delete_voice(voice_name: str):
    """Delete a custom voice from disk and in-memory cache."""
    ensure_initialized()
    try:
        result = voice_manager.delete_voice(voice_name)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@web_app.get("/download/{file_id}/audio")
async def download_audio(file_id: str):
    """Download the generated audio file from fertige_files."""
    target = output_dir / f"{file_id}.wav"
    if not target.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(target, media_type="audio/wav", filename=f"{file_id}.wav")


@web_app.get("/download/{file_id}/config")
async def download_config(file_id: str):
    """Download the configuration & log text file from fertige_files."""
    target = output_dir / f"{file_id}_config.txt"
    if not target.exists():
        raise HTTPException(status_code=404, detail="Config log file not found")
    return FileResponse(target, media_type="text/plain", filename=f"{file_id}_config.txt")


def process_tts_generation(
    text: str,
    voice: Optional[str] = None,
    language: Optional[str] = None,
    speed: float = 1.0,
    pitch: float = 0.0,
    temperature: Optional[float] = None,
    sampler_decode_steps: Optional[int] = None,
    frames_after_eos: Optional[int] = None,
    voice_url: Optional[str] = None,
    voice_wav_bytes: Optional[bytes] = None,
    voice_wav_suffix: str = ".wav",
) -> tuple[bytes, str, float, float]:
    """Execute TTS generation, apply speed/pitch audio effects, and save records to fertige_files."""
    ensure_initialized()
    start_time = time.monotonic()

    # 1. Determine target language
    target_voice = voice or voice_url
    if not language and target_voice:
        lang_code = voice_manager.get_voice_language(target_voice)
    else:
        lang_code = normalize_language_code(language)

    model = get_tts_model(lang_code)
    model_name = get_model_name_for_code(lang_code)

    # 2. Configure model inference parameters
    if temperature is not None:
        model.temp = float(temperature)
    if sampler_decode_steps is not None:
        model.sampler_decode_steps = int(sampler_decode_steps)

    # 3. Resolve voice state
    if voice_wav_bytes is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=voice_wav_suffix) as temp_file:
            temp_file.write(voice_wav_bytes)
            temp_file.flush()
            temp_file_path = temp_file.name
        try:
            model_state = model.get_state_for_audio_prompt(Path(temp_file_path), truncate=True)
            chosen_voice_name = "uploaded_custom_audio"
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
    else:
        voice_manager.set_model(model)
        chosen_voice_name = target_voice or get_default_voice_for_language(model_name)
        model_state = voice_manager.get_voice_state(chosen_voice_name)

    # 4. Generate raw audio
    raw_audio_tensor = model.generate_audio(
        model_state=model_state,
        text_to_generate=text,
        frames_after_eos=frames_after_eos,
    )
    sample_rate = model.sample_rate

    # 5. Apply speed and pitch effects
    processed_wav_bytes = apply_audio_effects(
        raw_audio_tensor,
        sample_rate=sample_rate,
        speed=speed,
        pitch=pitch,
    )

    elapsed_time = time.monotonic() - start_time
    duration_sec = (raw_audio_tensor.shape[-1] / sample_rate) / max(speed, 0.1)

    # 6. Save in fertige_files directory
    file_id, wav_path, config_path = save_generation_record(
        audio_bytes=processed_wav_bytes,
        text=text,
        voice_name=chosen_voice_name,
        language_code=lang_code,
        model_name=model_name,
        speed=speed,
        pitch=pitch,
        temperature=model.temp,
        sampler_decode_steps=model.sampler_decode_steps,
        frames_after_eos=frames_after_eos or (model.model_recommended_frames_after_eos or 1),
        duration_sec=duration_sec,
        processing_time_sec=elapsed_time,
    )

    return processed_wav_bytes, file_id, duration_sec, elapsed_time


@web_app.post("/tts")
async def text_to_speech_post(
    request: Request,
    text: Optional[str] = Form(None),
    voice: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    speed: float = Form(1.0),
    pitch: float = Form(0.0),
    temperature: Optional[float] = Form(None),
    sampler_decode_steps: Optional[int] = Form(None),
    frames_after_eos: Optional[int] = Form(None),
    voice_url: Optional[str] = Form(None),
    voice_wav: Optional[UploadFile] = File(None),
):
    """Generate speech from text with advanced audio and language settings."""
    text_to_use = text
    voice_to_use = voice
    lang_to_use = language
    speed_to_use = speed
    pitch_to_use = pitch
    temp_to_use = temperature
    steps_to_use = sampler_decode_steps
    eos_to_use = frames_after_eos
    voice_url_to_use = voice_url
    voice_wav_bytes = None
    voice_wav_suffix = ".wav"

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            text_to_use = body.get("text", text_to_use)
            voice_to_use = body.get("voice", voice_to_use)
            lang_to_use = body.get("language", lang_to_use)
            speed_to_use = float(body.get("speed", speed_to_use))
            pitch_to_use = float(body.get("pitch", pitch_to_use))
            temp_to_use = body.get("temperature", temp_to_use)
            steps_to_use = body.get("sampler_decode_steps", steps_to_use)
            eos_to_use = body.get("frames_after_eos", eos_to_use)
            voice_url_to_use = body.get("voice_url", voice_url_to_use)
        except Exception:
            pass

    if not text_to_use or not text_to_use.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    if voice_wav is not None:
        voice_wav_bytes = await voice_wav.read()
        if voice_wav.filename:
            voice_wav_suffix = Path(voice_wav.filename).suffix or ".wav"

    try:
        wav_bytes, file_id, duration_sec, elapsed = process_tts_generation(
            text=text_to_use,
            voice=voice_to_use,
            language=lang_to_use,
            speed=speed_to_use,
            pitch=pitch_to_use,
            temperature=temp_to_use,
            sampler_decode_steps=steps_to_use,
            frames_after_eos=eos_to_use,
            voice_url=voice_url_to_use,
            voice_wav_bytes=voice_wav_bytes,
            voice_wav_suffix=voice_wav_suffix,
        )
    except Exception as e:
        logger.error("TTS generation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f"attachment; filename={file_id}.wav",
            "X-File-Id": file_id,
            "X-Audio-Duration": f"{duration_sec:.2f}",
            "X-Processing-Time": f"{elapsed:.2f}",
        },
    )


@web_app.get("/tts")
async def text_to_speech_get(
    text: str = Query(..., description="Text to speak"),
    voice: Optional[str] = Query(None, description="Voice name"),
    language: Optional[str] = Query(None, description="Language code (de, en, fr, es, it, pt)"),
    speed: float = Query(1.0, description="Speech rate"),
    pitch: float = Query(0.0, description="Pitch in semitones"),
    temperature: Optional[float] = Query(None, description="Temperature"),
):
    """Simple GET endpoint for audio playback."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        wav_bytes, file_id, duration, elapsed = process_tts_generation(
            text=text,
            voice=voice,
            language=language,
            speed=speed,
            pitch=pitch,
            temperature=temperature,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f"attachment; filename={file_id}.wav",
            "X-File-Id": file_id,
        },
    )


@web_app.post("/v1/audio/speech")
async def openai_speech_endpoint(req: OpenAISpeechRequest):
    """OpenAI-compatible Text-to-Speech endpoint."""
    if not req.input.strip():
        raise HTTPException(status_code=400, detail="Input text cannot be empty")

    voice_target = None if req.voice in ("default", "", "alloy") else req.voice
    try:
        wav_bytes, file_id, duration, elapsed = process_tts_generation(
            text=req.input,
            voice=voice_target,
            language=req.language,
            speed=req.speed or 1.0,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f"attachment; filename={file_id}.wav",
            "X-File-Id": file_id,
        },
    )


@cli_app.command()
def serve(
    host: Annotated[str, typer.Option(help="Host to bind to")] = "0.0.0.0",
    port: Annotated[int, typer.Option(help="Port to bind to")] = 8000,
    voices_dir: Annotated[
        str, typer.Option(help="Directory containing custom voice files (.safetensors or audio)")
    ] = "./voices",
    device: Annotated[str, typer.Option(help="Device to use ('cpu' or 'cuda')")] = "cpu",
    reload: Annotated[bool, typer.Option(help="Enable auto-reload")] = False,
    language: Annotated[
        str | None,
        typer.Option(
            help="Default language for TTS ('german_24l', 'english', 'french_24l', etc.)",
            show_default=False,
        ),
    ] = "german_24l",
    quantize: Annotated[
        bool, typer.Option(help="Apply int8 quantization to reduce memory usage")
    ] = False,
):
    """Start the FastAPI server with multi-language voice management, audio effects, and archiving."""
    global tts_model, voice_manager
    tts_model = get_tts_model(language)
    voice_manager = VoiceManager(voices_dir=voices_dir, tts_model=tts_model)
    logger.info("Server ready on %s:%d with output directory %s", host, port, output_dir)
    uvicorn.run(web_app, host=host, port=port, reload=reload)


# ------------------------------------------------------
# CLI generate command
# ------------------------------------------------------

@cli_app.command()
def generate(
    text: Annotated[str, typer.Option(help="Text to generate")] = None,
    voice: Annotated[str | None, typer.Option(help="Voice to clone or predefined name")] = None,
    quiet: Annotated[bool, typer.Option("-q", "--quiet", help="Disable logging")] = False,
    language: Annotated[str | None, typer.Option(help="Language for model")] = None,
    config: Annotated[str | None, typer.Option(help="Config file")] = None,
    checkpoint: Annotated[str | None, typer.Option(help="Checkpoint")] = None,
    sampler_decode_steps: Annotated[int, typer.Option(help="Steps")] = DEFAULT_SAMPLER_DECODE_STEPS,
    temperature: Annotated[float | None, typer.Option(help="Temperature")] = None,
    noise_clamp: Annotated[float, typer.Option(help="Noise clamp")] = DEFAULT_NOISE_CLAMP,
    eos_threshold: Annotated[float, typer.Option(help="EOS threshold")] = DEFAULT_EOS_THRESHOLD,
    frames_after_eos: Annotated[int, typer.Option(help="Frames after EOS")] = DEFAULT_FRAMES_AFTER_EOS,
    output_path: Annotated[str, typer.Option(help="Output WAV path")] = "./tts_output.wav",
    device: Annotated[str, typer.Option(help="Device")] = "cpu",
    max_tokens: Annotated[int, typer.Option(help="Max tokens")] = MAX_TOKEN_PER_CHUNK,
    quantize: Annotated[bool, typer.Option(help="Quantize")] = False,
):
    """Generate speech using Kyutai Pocket TTS CLI."""
    log_level = logging.ERROR if quiet else logging.INFO
    with enable_logging("pocket_tts", log_level):
        if text is None:
            text = get_default_text_for_language(language)
        if text == "-":
            text = sys.stdin.read()

        if not text.strip():
            logger.error("No input received.")
            raise typer.Exit(code=1)

        model = TTSModel.load_model(
            language=language,
            config=config,
            temp=temperature,
            sampler_decode_steps=sampler_decode_steps,
            noise_clamp=noise_clamp,
            eos_threshold=eos_threshold,
            quantize=quantize,
            checkpoint=checkpoint,
        )
        model.to(device)

        if voice is None:
            voice = get_default_voice_for_language(language)
        model_state = model.get_state_for_audio_prompt(voice)

        audio_chunks = model.generate_audio_stream(
            model_state=model_state,
            text_to_generate=text,
            frames_after_eos=frames_after_eos,
            max_tokens=max_tokens,
        )
        stream_audio_chunks(output_path, audio_chunks, model.config.mimi.sample_rate)


@cli_app.command()
def export_voice(
    audio_path: Annotated[str, typer.Argument(help="Audio file")],
    export_path: Annotated[str, typer.Argument(help="Output safetensors path")],
    quiet: Annotated[bool, typer.Option("-q", "--quiet")] = False,
    language: Annotated[str | None, typer.Option()] = None,
    config: Annotated[str | None, typer.Option()] = None,
):
    """Convert and save audio to .safetensors file."""
    log_level = logging.ERROR if quiet else logging.INFO
    with enable_logging("pocket_tts", log_level):
        model = TTSModel.load_model(language=language, config=config)
        state = model.get_state_for_audio_prompt(audio_conditioning=audio_path, truncate=True)
        export_model_state(state, export_path)


if __name__ == "__main__":
    cli_app()
