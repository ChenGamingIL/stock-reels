"""Render slides to 1080x1920 images and stitch them with narration into an MP4 Reel."""
import os
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

from .script import DISCLAIMER
from .tts import synthesize

W, H = 1080, 1920
# Palette taken from the StocksisX logo: black, warm gold, green/red candles.
BG_TOP, BG_BOTTOM = (6, 6, 6), (28, 22, 12)
WHITE, MUTED = (246, 240, 226), (176, 158, 118)
GREEN, RED = (52, 199, 106), (224, 72, 58)
ACCENT, GOLD_DARK, INK = (232, 196, 120), (120, 94, 48), (12, 10, 6)

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
LOGO_FILE = ROOT / "assets" / "logo.jpg"
BRAND = os.environ.get("BRAND_NAME", "STOCKSISX")


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


NUM_RE = re.compile(r"\d{4}-\d{2}|[-+$]?\d[\d,.]*[%BMTx]?")


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


def logo(size):
    """The logo cropped to a circle, or None if assets/logo.jpg is missing."""
    if not LOGO_FILE.exists():
        return None
    im = Image.open(LOGO_FILE).convert("RGB").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
    return im, mask.resize((size, size), Image.LANCZOS)


def paste_logo(img, xy, size, ring=True):
    lg = logo(size)
    if not lg:
        return
    im, mask = lg
    img.paste(im, xy, mask)
    if ring:
        ImageDraw.Draw(img).ellipse([xy[0] - 3, xy[1] - 3, xy[0] + size + 3, xy[1] + size + 3],
                                    outline=ACCENT, width=4)


def base(d, title):
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    dr = ImageDraw.Draw(img)
    # faint trading-terminal grid
    for gx in range(0, W, 90):
        dr.line([(gx, 90), (gx, H - 260)], fill=(30, 25, 16), width=1)
    for gy in range(90, H - 260, 90):
        dr.line([(0, gy), (W, gy)], fill=(30, 25, 16), width=1)
    ticker_tape(dr, d)
    # header: logo + ticker badge + price, gold rule underneath
    paste_logo(img, (60, 105), 130)
    dr.rounded_rectangle([215, 125, 475, 215], 22, fill=ACCENT)
    dr.text((345, 170), d["ticker"], font=font(58), fill=INK, anchor="mm")
    dr.line([(60, 268), (W - 60, 268)], fill=GOLD_DARK, width=3)
    if d.get("price"):
        dr.text((W - 60, 145), f"${d['price']:,.2f}", font=font(56), fill=WHITE, anchor="ra")
        ch = d.get("change_5d_pct")
        if ch is not None:
            rtl_text(dr, (W - 60, 215), f"{ch:+.1f}% השבוע", 36, GREEN if ch >= 0 else RED)
    for i, line in enumerate(wrap(title, 76, W - 140)[:3]):
        rtl_text(dr, (W - 70, 330 + i * 100), line, 76)
    # footer: brand + disclaimer, on every slide
    dr.line([(60, H - 205), (W - 60, H - 205)], fill=GOLD_DARK, width=2)
    dr.text((60, H - 250), f"@{BRAND.lower()}", font=font(32), fill=ACCENT)
    for i, line in enumerate(wrap(DISCLAIMER, 30, W - 120)):
        rtl_text(dr, (W - 60, H - 170 + i * 42), line, 30, MUTED)
    return img, dr


def arrow(dr, x, y, up, color, s=12):
    """Small filled triangle, up or down, with its left edge at x and centred on y."""
    pts = [(x, y + s * 0.6), (x + s * 2, y + s * 0.6), (x + s, y - s * 0.8)] if up else \
          [(x, y - s * 0.6), (x + s * 2, y - s * 0.6), (x + s, y + s * 0.8)]
    dr.polygon(pts, fill=color)


def ticker_tape(dr, d):
    """Market strip across the top: the main indices' daily change."""
    items = d.get("market") or []
    dr.rectangle([0, 0, W, 72], fill=(14, 12, 8))
    dr.line([(0, 72), (W, 72)], fill=GOLD_DARK, width=2)
    if not items:
        return
    f, x = font(28), 30
    for name, _, pct in items:
        color = GREEN if pct >= 0 else RED
        dr.text((x, 36), name, font=f, fill=MUTED, anchor="lm")
        x += f.getlength(name) + 12
        arrow(dr, x, 36, pct >= 0, color, 9)
        x += 26
        txt = f"{abs(pct):.2f}%"
        dr.text((x, 36), txt, font=f, fill=color, anchor="lm")
        x += f.getlength(txt) + 34
        if x > W - 60:
            break


def slide_hook(d, sl):
    img, dr = base(d, sl["title"])
    rtl_text(dr, (W - 70, 760), d["name"], 60, MUTED)
    if d.get("sector"):
        rtl_text(dr, (W - 70, 850), d["sector"], 44, MUTED)
    return img


def slide_chart(d, sl):
    img, dr = base(d, sl["title"])
    candles = d.get("candles") or []
    if len(candles) < 2:
        return slide_line_chart(d, sl, img, dr)
    x0, x1, y0, y1 = 70, W - 190, 690, 1230     # price area, axis labels on the right
    v0, v1 = 1260, 1390                          # volume bars
    lo, hi = min(c[2] for c in candles), max(c[1] for c in candles)
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    py = lambda p: y1 - (y1 - y0) * (p - lo) / (hi - lo)
    for i in range(5):  # price gridlines + labels
        p = lo + (hi - lo) * i / 4
        dr.line([(x0, py(p)), (x1, py(p))], fill=(48, 40, 24), width=2)
        dr.text((x1 + 20, py(p)), f"{p:,.0f}", font=font(30), fill=MUTED, anchor="lm")
    step = (x1 - x0) / len(candles)
    body = max(step * 0.62, 4)
    vmax = max(c[4] for c in candles) or 1
    for i, (o, h, l, c, v) in enumerate(candles):
        cx = x0 + step * (i + 0.5)
        color = GREEN if c >= o else RED
        dr.line([(cx, py(h)), (cx, py(l))], fill=color, width=3)
        top, bot = sorted((py(o), py(c)))
        dr.rectangle([cx - body / 2, top, cx + body / 2, max(bot, top + 3)], fill=color)
        dim = tuple(int(a * 0.45 + b * 0.55) for a, b in zip(color, BG_BOTTOM))
        dr.rectangle([cx - body / 2, v1 - (v1 - v0) * v / vmax, cx + body / 2, v1], fill=dim)
    dr.text((x0, v0 - 8), "VOL", font=font(26), fill=MUTED, anchor="ls")
    last = candles[-1][3]  # last price tag on the axis
    dr.rounded_rectangle([x1 + 8, py(last) - 26, W - 20, py(last) + 26], 10, fill=ACCENT)
    dr.text(((x1 + W - 12) / 2, py(last)), f"{last:,.2f}", font=font(30), fill=INK, anchor="mm")
    ch = d.get("change_6m_pct")
    if ch is not None:
        color = GREEN if ch >= 0 else RED
        dr.text((W // 2, 1440), f"{ch:+.1f}%", font=font(96), fill=color, anchor="ma")
        rtl_text(dr, (W // 2, 1560), "6 חודשים · כל נר = שבוע", 34, MUTED, anchor="ma")
    return img


def slide_line_chart(d, sl, img, dr):
    pts = d.get("history") or []
    if len(pts) > 1:
        x0, x1, y0, y1 = 80, W - 80, 700, 1400
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
            dr.text((W // 2, y1 + 110), f"{ch:+.1f}%", font=font(90), fill=color, anchor="ma")
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
        dr.rounded_rectangle([60, y - 20, W - 60, y + 110], 26, fill=(22, 18, 10), outline=GOLD_DARK, width=3)
        rtl_text(dr, (W - 100, y + 18), row[0], 50)
        if len(row) == 2:
            dr.text((100, y + 18), row[1], font=font(56), fill=ACCENT)
        else:
            dr.text((520, y + 18), row[1], font=font(50), fill=ACCENT, anchor="ra")
            dr.text((120, y + 18), row[2], font=font(50), fill=WHITE)
        y += 160
    return img


def fmt_big(v):
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(v) >= div:
            return f"${v / div:.1f}{suf}"
    return f"${v:,.0f}"


def slide_earnings(d, sl):
    """Quarterly report card: last EPS vs estimate, then revenue bars per quarter."""
    img, dr = base(d, sl["title"])
    y = 660
    le = d.get("last_earnings") or {}
    if le.get("eps_reported") is not None and le.get("eps_estimate") is not None:
        beat = le["eps_reported"] >= le["eps_estimate"]
        color = GREEN if beat else RED
        dr.rounded_rectangle([60, y, W - 60, y + 250], 28, fill=(22, 18, 10), outline=GOLD_DARK, width=3)
        rtl_text(dr, (W - 100, y + 30), "דוח אחרון", 40, MUTED)
        if le.get("date"):
            dr.text((100, y + 30), le["date"], font=font(36), fill=MUTED)
        dr.text((W - 100, y + 110), f"EPS {le['eps_reported']:.2f}", font=font(64), fill=WHITE, anchor="ra")
        rtl_text(dr, (W - 100, y + 190), f"צפי {le['eps_estimate']:.2f}", 38, MUTED)
        dr.rounded_rectangle([100, y + 110, 430, y + 200], 20, fill=color)
        label = "הכה את הצפי" if beat else "פספס את הצפי"
        rtl_text(dr, (265, y + 155), label, 40, INK, anchor="mm")
        if le.get("surprise_pct") is not None:
            dr.text((265, y + 220), f"{le['surprise_pct']:+.1f}%", font=font(34), fill=color, anchor="mm")
        y += 300
    qs = [e for e in d.get("earnings") or [] if e.get("revenue")][-4:]
    if qs:
        rtl_text(dr, (W - 80, y), "הכנסות לפי רבעון", 40, MUTED)
        top, base_y = y + 120, 1490 if y < 900 else 1530
        rmax = max(e["revenue"] for e in qs)
        slot = (W - 160) / len(qs)
        bw = slot * 0.56
        for i, e in enumerate(qs):
            cx = 80 + slot * (i + 0.5)
            bh = (base_y - top - 60) * e["revenue"] / rmax
            prev = qs[i - 1]["revenue"] if i else None
            color = ACCENT if prev is None else (GREEN if e["revenue"] >= prev else RED)
            dr.rounded_rectangle([cx - bw / 2, base_y - bh, cx + bw / 2, base_y], 12, fill=color)
            dr.text((cx, base_y - bh - 14), fmt_big(e["revenue"]), font=font(34), fill=WHITE, anchor="ms")
            dr.text((cx, base_y + 16), e["quarter"], font=font(30), fill=MUTED, anchor="ma")
            if e.get("eps") is not None:
                dr.text((cx, base_y + 56), f"EPS {e['eps']:.2f}", font=font(28), fill=ACCENT, anchor="ma")
        dr.line([(70, base_y), (W - 70, base_y)], fill=GOLD_DARK, width=3)
    elif sl.get("rows"):
        return slide_table(d, sl)
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
    paste_logo(img, ((W - 460) // 2, 600), 460)
    dr = ImageDraw.Draw(img)
    dr.text((W // 2, 1110), f"@{BRAND.lower()}", font=font(64), fill=ACCENT, anchor="ma")
    for i, line in enumerate(wrap(DISCLAIMER, 44, W - 200)):
        rtl_text(dr, (W - 100, 1240 + i * 62), line, 44, MUTED)
    return img


RENDERERS = {"hook": slide_hook, "chart": slide_chart, "table": slide_table, "earnings": slide_earnings,
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
