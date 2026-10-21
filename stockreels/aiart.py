"""AI-generated cinematic backgrounds behind the opening and closing slides and the Reel cover.

With a FAL_KEY secret the picture comes from FLUX on fal.ai (sharp, about $0.03 each); without one
from Pollinations (free and keyless, softer, one picture per 45 seconds). Neither is reachable from
the cloud container, only from GitHub. Every image is asked for without text: image models garble
letters, and all the words on screen are ours. If the service is slow or down the Reel is rendered
without a picture, exactly as before.
"""
import os
import sys
import time
import urllib.parse
from pathlib import Path

import requests
from PIL import Image, ImageEnhance, ImageFilter

URL = "https://image.pollinations.ai/prompt/{prompt}"
STYLE = ("cinematic photograph, {subject}, dark moody scene, warm golden rim light, deep blacks, "
         "shallow depth of field, ultra detailed, 35mm film look, no text, no letters, no logos, no watermark")


def _fal(prompt, out, seed, timeout=120):
    key = os.environ.get("FAL_KEY")
    model = os.environ.get("FAL_IMAGE_MODEL", "fal-ai/flux/dev")
    r = requests.post(f"https://fal.run/{model}", headers={"Authorization": f"Key {key}"}, timeout=timeout,
                      json={"prompt": prompt, "image_size": {"width": 1080, "height": 1920}, "seed": seed,
                            "num_images": 1, "enable_safety_checker": True})
    r.raise_for_status()
    url = r.json()["images"][0]["url"]
    Path(out).write_bytes(requests.get(url, timeout=timeout).content)
    return out


def generate(subject, out, seed=1, width=1080, height=1920, attempts=3, timeout=120):
    """Fetch one image for `subject` into `out`; returns the path, or None if the service didn't deliver."""
    if os.environ.get("FAL_KEY"):
        try:
            return _fal(STYLE.format(subject=subject), out, seed)
        except Exception as e:  # fall back to the free service
            print(f"[aiart] fal.ai failed ({e.__class__.__name__}: {str(e)[:160]})")
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
            if r.status_code in (402, 429):  # the free tier allows one picture per 45 seconds
                time.sleep(47)
                continue
        except requests.RequestException as e:
            print(f"[aiart] {e.__class__.__name__}: {e}")
        time.sleep(8 * (attempt + 1))
    return None


# what the picture shows: by industry keyword first, then by sector, then by show
INDUSTRY = [
    ("semiconductor", "a silicon wafer with glowing gold circuits, macro"),
    ("software", "lines of glowing code reflected on dark glass"),
    ("auto", "a sleek electric car in a dark studio"),
    ("biotech", "a glowing DNA helix in a dark laboratory"),
    ("drug", "a glowing DNA helix in a dark laboratory"),
    ("aerospace", "a rocket on a launch pad at night with floodlights"),
    ("airline", "an airliner wing above the clouds at sunset"),
    ("bank", "a heavy bank vault door half open with gold bars inside"),
    ("insurance", "a quiet city skyline under a storm, lit windows"),
    ("gold", "gold bars stacked in a dark vault"),
    ("oil", "an oil refinery at dusk with orange sky"),
    ("solar", "solar panels at golden hour"),
    ("retail", "a luxury shopping street at night with glowing shop windows"),
    ("internet", "a dark data center with rows of glowing server racks"),
    ("entertainment", "an empty cinema hall lit by the screen"),
    ("restaurant", "a dim restaurant kitchen with flames on the grill"),
    ("capital markets", "rows of glowing server racks in a dark data center"),
]
SECTOR = {
    "Technology": "a glowing computer chip on a dark circuit board, macro",
    "Communication Services": "glowing fiber optic cables in the dark",
    "Consumer Cyclical": "a luxury shopping street at night with glowing shop windows",
    "Consumer Defensive": "a warmly lit supermarket aisle at night",
    "Healthcare": "a modern laboratory with glowing glass vials",
    "Financial Services": "a heavy bank vault door half open with gold bars inside",
    "Energy": "an oil refinery at dusk with orange sky",
    "Industrials": "robotic arms welding in a dark factory with sparks",
    "Basic Materials": "molten gold pouring in a foundry",
    "Real Estate": "glass skyscrapers seen from below at night",
    "Utilities": "power line towers against a sunset",
}
SHOW = {
    "premarket": ["the New York Stock Exchange facade at dawn with American flags",
                  "Manhattan skyline at sunrise seen from the river",
                  "a bronze charging bull statue on a New York street at dawn"],
    "close": ["Wall Street at night with lit skyscrapers",
              "the New York Stock Exchange facade at night",
              "Manhattan skyline at night with lights reflecting in the river"],
    "lesson": ["an open notebook and a pen on a dark desk next to a laptop showing a chart",
               "a chess board with a golden king piece, dramatic light",
               "an antique brass compass on a dark map"],
    "didyouknow": ["an old library with tall shelves and a globe",
                   "an antique ticker tape machine in a dark room",
                   "old banknotes and gold coins on dark wood"],
    "hot": ["a bronze charging bull statue on a New York street at night"],
}


def subject(show, stock, episode=0):
    if show == "hot":
        ind = (stock.get("industry") or "").lower()
        hit = next((s for k, s in INDUSTRY if k in ind), None) or SECTOR.get(stock.get("sector") or "")
        if hit:
            return hit
    options = SHOW.get(show, SHOW["hot"])
    return options[episode % len(options)]


def grade(path):
    """The picture in the account's colours: mostly black and warm gold, darker where the words go."""
    img = Image.open(path).convert("RGB")
    img = img.crop((0, 0, img.width, int(img.height * 0.95)))  # the free service stamps its name in the corner
    s = max(1080 / img.width, 1920 / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x, y = (img.width - 1080) // 2, (img.height - 1920) // 2
    img = img.crop((x, y, x + 1080, y + 1920))
    img = ImageEnhance.Color(img).enhance(0.55)
    gold = Image.new("RGB", img.size, (232, 196, 120))
    img = Image.blend(img, Image.composite(gold, img, img.convert("L")), 0.18)  # warm the highlights
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    # scrim: dark behind the header and title, lighter through the middle, dark again behind the footer
    shade = Image.new("L", (1, 1920))
    for yy in range(1920):
        t = yy / 1919
        a = 0.86 - 0.42 * min(t / 0.45, 1) if t < 0.62 else 0.44 + 0.5 * (t - 0.62) / 0.38
        shade.putpixel((0, yy), int(255 * a))
    black = Image.new("RGB", img.size, (6, 6, 6))
    return Image.composite(black, img, shade.resize(img.size))


def backdrop(show, stock, out_dir, episode=0, seed=None):
    """Generate today's picture for this show; None when switched off or the service didn't answer."""
    local = os.environ.get("AI_BG")  # a ready picture, for rendering offline
    if local:
        return local
    if os.environ.get("AI_ART", "1") == "0":
        return None
    what = subject(show, stock, episode)
    print(f"[aiart] {show}: {what}")
    return generate(what, Path(out_dir) / "bg.jpg", seed=seed or 1)


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
