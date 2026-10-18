"""Hebrew narration via edge-tts (free Microsoft neural voices)."""
import asyncio
import json
import os
import subprocess
import time

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


async def _stream(text, path):
    """Save the audio and return the spoken words as [(word, start_s, end_s)]."""
    import edge_tts

    words = []
    com = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    with open(path, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7  # 100ns ticks
                words.append((chunk["text"], start, start + chunk["duration"] / 1e7))
    return words


def even_words(text, duration):
    """Spread the words over the clip by length, when the voice gave no word timings."""
    ws = text.split()
    total = sum(len(w) + 1 for w in ws) or 1
    out, t = [], 0.0
    for w in ws:
        d = duration * (len(w) + 1) / total
        out.append((w, t, t + d))
        t += d
    return out


def synthesize(text, path, attempts=int(os.environ.get("TTS_ATTEMPTS", 4))):
    """Write narration to `path` (mp3) and return (duration in seconds, word timings).

    The speech endpoint sometimes answers 403 for a minute (it failed two pre-market
    shows), so it is retried with a growing pause. Falls back to silence sized to the
    text if it stays unreachable, so a preview can still be rendered offline.
    Set TTS_REQUIRED=1 to fail instead.
    """
    err = None
    for i in range(attempts):
        try:
            words = asyncio.run(_stream(text, path))
            if os.path.getsize(path) > 0:
                dur = audio_duration(path)
                return dur, words or even_words(text, dur)
            raise RuntimeError("empty audio")
        except Exception as e:
            err = e
            print(f"[tts] attempt {i + 1} failed: {e.__class__.__name__}: {str(e)[:120]}")
            if i < attempts - 1:
                time.sleep(5 * 3 ** i)  # 5s, 15s, 45s
    if os.environ.get("TTS_REQUIRED") == "1":
        raise err
    print("[tts] falling back to silence")
    _silence(path, max(2.5, len(text.split()) * 0.38))
    dur = audio_duration(path)
    return dur, even_words(text, dur)
