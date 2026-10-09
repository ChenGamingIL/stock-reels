"""Render slides to 1080x1920 images and stitch them with narration into an MP4 Reel."""
import os
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

from .script import DISCLAIMER
from .tts import synthesize

W, H = 1080, 1920
BG_TOP, BG_BOTTOM = (10, 14, 30), (20, 32, 64)
WHITE, MUTED = (240, 244, 255), (150, 165, 200)
GREEN, RED, ACCENT = (46, 204, 113), (231, 76, 60), (255, 196, 0)

ROOT = Path(__file__).resolve().parent.parent
FONT_CANDIDATES = [
    os.environ.get("FONT_PATH", ""),
    str(ROOT / "assets" / "fonts" / "Heebo-Bold.ttf"),
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
FONT_FILE = next(p for p in FONT_CANDIDATES if p and os.path.exists(p))
HAS_RAQM = features.check("raqm")


_FONTS = {}


def font(size):
    if size not in _FONTS:
        f = ImageFont.truetype(FONT_FILE, size)
        try:
            f.set_variation_by_name("Bold")  # variable fonts like Heebo[wght]
        except Exception:
            pass
        _FONTS[size] = f
    return _FONTS[size]


NUM_RE = re.compile(r"[-+$]?\d[\d,.]*[%BMTx]?")


def _visual(text):
    # keep signed numbers like +6.4% or -$1.2B in LTR order inside Hebrew lines
    text = NUM_RE.sub(lambda m: "\u2066" + m.group(0) + "\u2069", text)
    if HAS_RAQM:
        return text
    from bidi.algorithm import get_display
    return get_display(text)


def rtl_text(draw, xy, text, size, fill=WHITE, anchor="ra"):
    kw = {"direction": "rtl"} if HAS_RAQM else {}
    draw.text(xy, _visual(text), font=font(size), fill=fill, anchor=anchor, **kw)


def wrap(text, size, max_w):
    f, lines, cur = font(size), [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if f.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def base(d, title):
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    dr = ImageDraw.Draw(img)
    # header: ticker badge + price
    dr.rounded_rectangle([60, 120, 360, 220], 24, fill=ACCENT)
    dr.text((210, 170), d["ticker"], font=font(64), fill=(10, 14, 30), anchor="mm")
    if d.get("price"):
        dr.text((W - 60, 145), f"${d['price']:,.2f}", font=font(56), fill=WHITE, anchor="ra")
        ch = d.get("change_5d_pct")
        if ch is not None:
            rtl_text(dr, (W - 60, 215), f"{ch:+.1f}% השבוע", 36, GREEN if ch >= 0 else RED)
    for i, line in enumerate(wrap(title, 76, W - 140)[:3]):
        rtl_text(dr, (W - 70, 330 + i * 100), line, 76)
    # footer disclaimer, on every slide
    for i, line in enumerate(wrap(DISCLAIMER, 30, W - 120)):
        rtl_text(dr, (W - 60, H - 170 + i * 42), line, 30, MUTED)
    return img, dr


def slide_hook(d, sl):
    img, dr = base(d, sl["title"])
    rtl_text(dr, (W - 70, 760), d["name"], 60, MUTED)
    if d.get("sector"):
        rtl_text(dr, (W - 70, 850), d["sector"], 44, MUTED)
    return img


def slide_chart(d, sl):
    img, dr = base(d, sl["title"])
    pts = d.get("history") or []
    if len(pts) > 1:
        x0, x1, y0, y1 = 80, W - 80, 700, 1500
        lo, hi = min(pts), max(pts)
        span = (hi - lo) or 1
        xy = [(x0 + (x1 - x0) * i / (len(pts) - 1), y1 - (y1 - y0) * (p - lo) / span) for i, p in enumerate(pts)]
        color = GREEN if pts[-1] >= pts[0] else RED
        poly = xy + [(x1, y1), (x0, y1)]
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).polygon(poly, fill=color + (45,))
        img.paste(overlay, (0, 0), overlay)
        dr = ImageDraw.Draw(img)
        dr.line(xy, fill=color, width=8, joint="curve")
        dr.ellipse([xy[-1][0] - 14, xy[-1][1] - 14, xy[-1][0] + 14, xy[-1][1] + 14], fill=color)
        dr.text((x0, y1 + 30), f"low ${lo:,.0f}", font=font(36), fill=MUTED)
        dr.text((x1, y1 + 30), f"high ${hi:,.0f}", font=font(36), fill=MUTED, anchor="ra")
        ch = d.get("change_6m_pct")
        if ch is not None:
            dr.text((W // 2, y1 + 130), f"{ch:+.1f}%", font=font(90), fill=color, anchor="ma")
    return img


def slide_table(d, sl):
    img, dr = base(d, sl["title"])
    y = 700
    if sl.get("header"):
        h = sl["header"]
        rtl_text(dr, (W - 80, y), h[0], 40, MUTED)
        dr.text((520, y), h[1], font=font(40), fill=MUTED, anchor="ra")
        dr.text((120, y), h[2], font=font(40), fill=MUTED)
        y += 90
    for row in sl["rows"]:
        dr.rounded_rectangle([60, y - 20, W - 60, y + 110], 26, outline=(60, 80, 130), width=3)
        rtl_text(dr, (W - 100, y + 18), row[0], 50)
        if len(row) == 2:
            dr.text((100, y + 18), row[1], font=font(56), fill=ACCENT)
        else:
            dr.text((520, y + 18), row[1], font=font(50), fill=ACCENT, anchor="ra")
            dr.text((120, y + 18), row[2], font=font(50), fill=WHITE)
        y += 160
    return img


def slide_bullets(d, sl):
    img, dr = base(d, sl["title"])
    color = RED if sl.get("accent") == "red" else GREEN
    y = 720
    for b in sl["bullets"]:
        dr.ellipse([W - 110, y + 18, W - 80, y + 48], fill=color)
        lines = wrap(b, 58, W - 260)
        for j, line in enumerate(lines):
            rtl_text(dr, (W - 140, y + j * 72), line, 58)
        y += 72 * len(lines) + 70
    return img


def slide_outro(d, sl):
    img, dr = base(d, sl["title"])
    for i, line in enumerate(wrap(DISCLAIMER, 52, W - 160)):
        rtl_text(dr, (W - 80, 800 + i * 74), line, 52, ACCENT)
    return img


RENDERERS = {"hook": slide_hook, "chart": slide_chart, "table": slide_table,
             "bullets": slide_bullets, "outro": slide_outro}


def render_video(d, script, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    segments = []
    for i, sl in enumerate(script["slides"]):
        png, mp3, seg = (out_dir / f"slide_{i}.{ext}" for ext in ("png", "mp3", "mp4"))
        RENDERERS[sl["kind"]](d, sl).save(png)
        dur = synthesize(sl["narration"], str(mp3)) + 0.4
        fade_out = max(dur - 0.25, 0)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png), "-i", str(mp3),
            "-filter_complex",
            f"[0:v]scale={W}:{H},format=yuv420p,fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.2f}:d=0.25[v];"
            f"[1:a]apad,aresample=44100[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-r", "30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "128k", str(seg),
        ], check=True)
        segments.append(seg)
    listing = out_dir / "segments.txt"
    listing.write_text("".join(f"file '{s.name}'\n" for s in segments))
    final = out_dir / "reel.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", "-movflags", "+faststart", str(final)], check=True)
    return final
