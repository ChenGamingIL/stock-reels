"""Hebrew narration via edge-tts (free Microsoft neural voices)."""
import asyncio
import json
import os
import subprocess

VOICE = os.environ.get("TTS_VOICE", "he-IL-AvriNeural")  # or he-IL-HilaNeural
RATE = os.environ.get("TTS_RATE", "+8%")


def audio_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def _silence(path, seconds):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", f"{seconds:.2f}", "-c:a", "libmp3lame", path], check=True)


def synthesize(text, path):
    """Write narration to `path` (mp3) and return its duration in seconds.

    Falls back to silence sized to the text if TTS is unreachable, so a
    preview can still be rendered offline. Set TTS_REQUIRED=1 to fail instead.
    """
    try:
        import edge_tts

        asyncio.run(edge_tts.Communicate(text, VOICE, rate=RATE).save(path))
        if os.path.getsize(path) > 0:
            return audio_duration(path)
        raise RuntimeError("empty audio")
    except Exception as e:
        if os.environ.get("TTS_REQUIRED") == "1":
            raise
        print(f"[tts] falling back to silence: {e.__class__.__name__}")
        _silence(path, max(2.5, len(text.split()) * 0.38))
        return audio_duration(path)
