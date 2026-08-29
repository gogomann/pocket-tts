import io
import logging
import math
import subprocess
from pathlib import Path
from typing import Union

import numpy as np
import torch

logger = logging.getLogger(__name__)


def apply_audio_effects(
    audio_input: Union[bytes, torch.Tensor, Path, str],
    sample_rate: int = 24000,
    speed: float = 1.0,
    pitch: float = 0.0,
) -> bytes:
    """Apply speed (time-stretch) and pitch (semitone shift) effects using ffmpeg.

    Args:
        audio_input: WAV audio as bytes, torch Tensor, or file path.
        sample_rate: Audio sampling rate in Hz (default 24000).
        speed: Speed multiplier (e.g. 0.5 to 2.0, default 1.0).
        pitch: Pitch shift in semitones (e.g. -12 to +12, default 0.0).

    Returns:
        Processed audio as 16-bit PCM WAV bytes.
    """
    speed = float(speed)
    pitch = float(pitch)

    # Convert torch Tensor to WAV bytes if needed
    if isinstance(audio_input, torch.Tensor):
        import wave

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            chunk_int16 = (audio_input.clamp(-1, 1) * 32767).short()
            wav_file.writeframes(chunk_int16.detach().cpu().numpy().tobytes())
        input_bytes = buffer.getvalue()
    elif isinstance(audio_input, (str, Path)):
        input_bytes = Path(audio_input).read_bytes()
    else:
        input_bytes = audio_input

    # If no effects applied, return original input bytes
    if abs(speed - 1.0) < 1e-3 and abs(pitch) < 1e-3:
        return input_bytes

    # Build ffmpeg audio filter graph
    # Pitch shift factor r = 2^(pitch/12)
    # When asetrate changes by r, duration changes by 1/r, so we need atempo = speed / r
    r = math.pow(2.0, pitch / 12.0)
    atempo = speed / r

    filter_chains = []

    # 1. Pitch change via asetrate & aresample (if pitch != 0)
    if abs(pitch) >= 1e-3:
        new_rate = int(sample_rate * r)
        filter_chains.append(f"asetrate={new_rate},aresample={sample_rate}")

    # 2. Speed / tempo change via atempo (handles 0.5 to 2.0 per filter instance)
    if abs(atempo - 1.0) >= 1e-3:
        remaining_tempo = atempo
        while remaining_tempo > 2.0:
            filter_chains.append("atempo=2.0")
            remaining_tempo /= 2.0
        while remaining_tempo < 0.5:
            filter_chains.append("atempo=0.5")
            remaining_tempo /= 0.5
        filter_chains.append(f"atempo={remaining_tempo:.4f}")

    filter_str = ",".join(filter_chains)

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-threads", "0",
        "-f", "wav",
        "-i", "pipe:0",
        "-af", filter_str,
        "-f", "wav",
        "-ac", "1",
        "-ar", str(sample_rate),
        "pipe:1"
    ]

    try:
        proc = subprocess.run(cmd, input=input_bytes, capture_output=True, check=True)
        return proc.stdout
    except Exception as e:
        logger.warning("FFmpeg audio effect failed, returning original audio: %s", e)
        return input_bytes
