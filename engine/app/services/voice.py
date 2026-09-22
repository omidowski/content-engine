import math
import struct
import wave
from pathlib import Path

import httpx

from app.config import Settings


def _write_silent_wav(path: Path, seconds: float) -> None:
    sample_rate = 16_000
    frames = min(int(seconds * sample_rate), sample_rate * 60)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        chunk = struct.pack("<h", 0) * min(frames, sample_rate)
        for _ in range(math.ceil(frames / sample_rate)):
            remaining = frames - audio.getnframes()
            audio.writeframes(chunk[: min(remaining, sample_rate) * 2])


def synthesize(text: str, target_dir: Path, settings: Settings) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
        if not settings.allow_demo_fallback:
            raise RuntimeError("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are required")
        path = target_dir / "voiceover-demo.wav"
        _write_silent_wav(path, max(5, len(text.split()) / 2.5))
        return path

    path = target_dir / "voiceover.mp3"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}"
    with httpx.Client(timeout=120) as client:
        response = client.post(
            url,
            headers={"xi-api-key": settings.elevenlabs_api_key, "Accept": "audio/mpeg"},
            json={"text": text, "model_id": settings.elevenlabs_model_id},
        )
        response.raise_for_status()
        path.write_bytes(response.content)
    return path

