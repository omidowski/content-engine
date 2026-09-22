import re
import shutil
import subprocess
from pathlib import Path

from app.config import Settings


def ffmpeg_available(settings: Settings) -> bool:
    return shutil.which(settings.ffmpeg_binary) is not None


def _timestamp(seconds: float) -> str:
    millis = round((seconds - int(seconds)) * 1000)
    whole = int(seconds)
    return f"{whole // 3600:02}:{whole % 3600 // 60:02}:{whole % 60:02},{millis:03}"


def _subtitle_chunks(text: str, max_words: int = 7) -> list[str]:
    words = re.sub(r"\s+", " ", text).strip().split()
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)] or [""]


def write_srt(script: str, duration: float, path: Path) -> None:
    chunks = _subtitle_chunks(script)
    slot = duration / len(chunks)
    blocks = []
    for index, chunk in enumerate(chunks, 1):
        blocks.append(f"{index}\n{_timestamp((index - 1) * slot)} --> {_timestamp(index * slot)}\n{chunk}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def audio_duration(audio_path: Path, settings: Settings) -> float:
    probe = shutil.which("ffprobe") or "ffprobe"
    result = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return max(1.0, float(result.stdout.strip()))


def render(script: str, audio_path: Path, target_dir: Path, settings: Settings) -> Path:
    if not ffmpeg_available(settings):
        raise RuntimeError("FFmpeg was not found. Install it or set FFMPEG_BINARY.")
    target_dir.mkdir(parents=True, exist_ok=True)
    duration = audio_duration(audio_path, settings)
    subtitle_path = target_dir / "captions.srt"
    video_path = target_dir / "short.mp4"
    write_srt(script, duration, subtitle_path)
    escaped_srt = str(subtitle_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    subtitle_filter = (
        f"subtitles='{escaped_srt}':force_style='FontName=Arial,FontSize=20,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=2,"
        "Shadow=0,Alignment=2,MarginV=180'"
    )
    command = [
        settings.ffmpeg_binary,
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x111827:s=1080x1920:r=30:d={duration:.3f}",
        "-i", str(audio_path),
        "-vf", subtitle_filter,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg rendering failed: {result.stderr[-1500:]}")
    return video_path

