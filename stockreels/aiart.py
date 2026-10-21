"""AI-generated cinematic backgrounds (Pollinations, free and keyless; reachable from GitHub, not from the cloud container).

Every image is asked for without text: image models garble letters, and all the words on screen are ours.
If the service is slow or down the Reel is rendered without it, exactly as before.
"""
import sys
import time
import urllib.parse
from pathlib import Path

import requests

URL = "https://image.pollinations.ai/prompt/{prompt}"
STYLE = ("cinematic photograph, {subject}, dark moody scene, warm golden rim light, deep blacks, "
         "shallow depth of field, ultra detailed, 35mm film look, no text, no letters, no logos, no watermark")


def generate(subject, out, seed=1, width=1080, height=1920, attempts=3, timeout=120):
    """Fetch one image for `subject` into `out`; returns the path, or None if the service didn't deliver."""
    prompt = urllib.parse.quote(STYLE.format(subject=subject))
    params = {"width": width, "height": height, "seed": seed, "model": "flux", "nologo": "true", "enhance": "false"}
    for attempt in range(attempts):
        try:
            r = requests.get(URL.format(prompt=prompt), params=params, timeout=timeout)
            kind = r.headers.get("content-type", "")
            if r.status_code == 200 and kind.startswith("image/") and len(r.content) > 20000:
                Path(out).write_bytes(r.content)
                return out
            print(f"[aiart] {r.status_code} {kind} {len(r.content)}B: {r.text[:120] if 'text' in kind or 'json' in kind else ''}")
        except requests.RequestException as e:
            print(f"[aiart] {e.__class__.__name__}: {e}")
        time.sleep(8 * (attempt + 1))
    return None


PROBE = {
    "bull": "a bronze charging bull statue on a New York street at night",
    "nyse": "the New York Stock Exchange building facade at dawn, flags",
    "chip": "a glowing AI computer chip on a dark motherboard, macro shot",
    "trader": "silhouette of a trader in a dark room facing many screens of stock charts",
    "gold": "stacks of gold coins with a glowing rising candlestick chart behind them",
    "energy": "an oil refinery at dusk with flames and orange sky",
}

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "output/ai")
    out.mkdir(parents=True, exist_ok=True)
    for i, (name, subject) in enumerate(PROBE.items()):
        t = time.time()
        ok = generate(subject, out / f"{name}.jpg", seed=11 + i)
        print(f"[aiart] {name}: {'ok' if ok else 'failed'} in {time.time() - t:.1f}s")
