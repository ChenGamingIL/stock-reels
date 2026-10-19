"""Voice samples: the same Hebrew lines in every candidate voice, so Chen can pick by ear.

Run on GitHub (the cloud container can't reach the speech service):
    python -m stockreels.voices out_dir
Each file is the raw voice and a "mastered" copy through the same audio chain the Reels use.
"""
import asyncio
import sys
from pathlib import Path

from .tts import master

SAMPLE = ("המניה החמה של היום: אנבידיה. היא עלתה ב-12 אחוז השבוע, אחרי דוח שהפתיע את וול סטריט. "
          "אבל רגע, לפני שמתלהבים, בואו נראה מה המספרים באמת אומרים.")

# Microsoft's two Hebrew voices, and its multilingual voices, which read Hebrew in a more conversational style
CANDIDATES = [
    ("avri", "he-IL-AvriNeural", "+8%"), ("avri-slower", "he-IL-AvriNeural", "+0%"),
    ("hila", "he-IL-HilaNeural", "+4%"),
    ("andrew", "en-US-AndrewMultilingualNeural", "+0%"), ("brian", "en-US-BrianMultilingualNeural", "+0%"),
    ("ava", "en-US-AvaMultilingualNeural", "+0%"), ("emma", "en-US-EmmaMultilingualNeural", "+0%"),
    ("remy", "fr-FR-RemyMultilingualNeural", "+0%"), ("florian", "de-DE-FlorianMultilingualNeural", "+0%"),
    ("giuseppe", "it-IT-GiuseppeMultilingualNeural", "+0%"),
]


async def _say(text, voice, rate, path):
    import edge_tts

    await edge_tts.Communicate(text, voice, rate=rate).save(str(path))


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for name, voice, rate in CANDIDATES:
        raw = out / f"{name}-raw.mp3"
        try:
            asyncio.run(_say(SAMPLE, voice, rate, raw))
            if raw.stat().st_size < 2000:
                raise RuntimeError("no audio")
        except Exception as e:
            print(f"[voices] {name} ({voice}): no Hebrew ({e.__class__.__name__})")
            raw.unlink(missing_ok=True)
            continue
        master(str(raw), str(out / f"{name}.mp3"))
        made.append(name)
        print(f"[voices] {name} ({voice} {rate}) ok")
    return made


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "output/voices")
