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


# dates and clock times first; a sign only counts when it isn't a Hebrew prefix hyphen like "ו-200"
NUM_RE = re.compile(r"\d{4}-\d{2}(?:-\d{2})?|\d{1,2}:\d{2}|(?:(?<![\u0590-\u05ff])[-+])?\$?\d[\d,.]*[%BMTx]?")


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
    size = 58
    while font(size).getlength(d["ticker"]) > 230 and size > 24:
        size -= 2
    dr.text((345, 170), d["ticker"], font=font(size), fill=INK, anchor="mm")
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
    draw_candles(img, dr, candles, (70, W - 190, 690, 1230), (1260, 1390))
    ch = d.get("change_6m_pct")
    if ch is not None:
        color = GREEN if ch >= 0 else RED
        dr.text((W // 2, 1440), f"{ch:+.1f}%", font=font(96), fill=color, anchor="ma")
        rtl_text(dr, (W // 2, 1560), "6 חודשים · כל נר = שבוע", 34, MUTED, anchor="ma")
    return img


def draw_candles(img, dr, candles, box, vol=None, lines=(), levels=()):
    """Candlesticks in box=(x0, x1, y0, y1), optional volume band vol=(v0, v1).

    lines: [(series, color)] drawn over the candles (moving averages).
    levels: [(price, label, color)] horizontal dashed levels with a tag on the right axis.
    """
    x0, x1, y0, y1 = box
    prices = [c[1] for c in candles] + [c[2] for c in candles] + [p for p, _, _ in levels]
    lo, hi = min(prices), max(prices)
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    py = lambda p: y1 - (y1 - y0) * (p - lo) / (hi - lo)
    for i in range(5):  # price gridlines + labels
        p = lo + (hi - lo) * i / 4
        dr.line([(x0, py(p)), (x1, py(p))], fill=(48, 40, 24), width=2)
        dr.text((x1 + 20, py(p)), f"{p:,.0f}" if hi > 50 else f"{p:,.2f}", font=font(30), fill=MUTED, anchor="lm")
    step = (x1 - x0) / len(candles)
    body = max(step * 0.62, 4)
    vmax = max(c[4] for c in candles) or 1
    for i, (o, h, l, c, v) in enumerate(candles):
        cx = x0 + step * (i + 0.5)
        color = GREEN if c >= o else RED
        dr.line([(cx, py(h)), (cx, py(l))], fill=color, width=3 if step > 12 else 2)
        top, bot = sorted((py(o), py(c)))
        dr.rectangle([cx - body / 2, top, cx + body / 2, max(bot, top + 3)], fill=color)
        if vol:
            dim = tuple(int(a * 0.45 + b * 0.55) for a, b in zip(color, BG_BOTTOM))
            dr.rectangle([cx - body / 2, vol[1] - (vol[1] - vol[0]) * v / vmax, cx + body / 2, vol[1]], fill=dim)
    if vol:
        dr.text((x0, vol[0] - 8), "VOL", font=font(26), fill=MUTED, anchor="ls")
    for series, color in lines:
        pts = [(x0 + step * (i + 0.5), py(v)) for i, v in enumerate(series) if v == v]
        if len(pts) > 1:
            dr.line(pts, fill=color, width=4, joint="curve")
    for price, label, color in levels:
        y = py(price)
        for xx in range(int(x0), int(x1), 28):
            dr.line([(xx, y), (min(xx + 16, x1), y)], fill=color, width=3)
        dr.rounded_rectangle([x1 + 8, y - 24, W - 20, y + 24], 10, fill=color)
        dr.text(((x1 + W - 12) / 2, y), f"{price:,.2f}", font=font(28), fill=INK, anchor="mm")
        rtl_text(dr, (x1 - 10, y - 12), label, 30, color, anchor="rs")
    if not levels:  # last price tag on the axis
        last = candles[-1][3]
        dr.rounded_rectangle([x1 + 8, py(last) - 26, W - 20, py(last) + 26], 10, fill=ACCENT)
        dr.text(((x1 + W - 12) / 2, py(last)), f"{last:,.2f}", font=font(30), fill=INK, anchor="mm")


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


def slide_intro(d, sl):
    img, dr = base(d, sl["title"])
    for i, line in enumerate(sl.get("lines", [])):
        rtl_text(dr, (W - 70, 760 + i * 90), line, 52 if i == 0 else 44, ACCENT if i == 0 else MUTED)
    paste_logo(img, ((W - 380) // 2, 1040), 380)
    return img


def slide_tiles(d, sl):
    """2-column grid of market tiles: label, price, daily change."""
    img, dr = base(d, sl["title"])
    tiles = sl["tiles"][:10]
    cols, gap, top = 2, 24, 640
    tw = (W - 120 - gap) / cols
    th = min(180, (1660 - top - gap * 4) / ((len(tiles) + 1) // 2))
    for i, t in enumerate(tiles):
        col, row = 1 - i % cols, i // cols  # first tile on the right (RTL)
        x, y = 60 + col * (tw + gap), top + row * (th + gap)
        color = GREEN if t["pct"] >= 0 else RED
        dr.rounded_rectangle([x, y, x + tw, y + th], 22, fill=(22, 18, 10), outline=GOLD_DARK, width=2)
        dr.rectangle([x + tw - 10, y + 18, x + tw - 4, y + th - 18], fill=color)
        rtl_text(dr, (x + tw - 30, y + 18), t["label"], 34, MUTED)
        dr.text((x + tw - 30, y + th - 22), f"{t['price']:,.{t['decimals']}f}", font=font(44), fill=WHITE, anchor="rs")
        arrow(dr, x + 26, y + th - 42, t["pct"] >= 0, color, 11)
        dr.text((x + 56, y + th - 22), f"{abs(t['pct']):.2f}%", font=font(38), fill=color, anchor="ls")
    return img


def slide_movers(d, sl):
    img, dr = base(d, sl["title"])
    y = 660
    for label, rows, color in (("עולות", sl["movers"]["gainers"], GREEN), ("יורדות", sl["movers"]["losers"], RED)):
        if not rows:
            continue
        rtl_text(dr, (W - 80, y), label, 42, color)
        y += 80
        for t, p in rows:
            dr.rounded_rectangle([60, y - 16, W - 60, y + 104], 24, fill=(22, 18, 10), outline=GOLD_DARK, width=2)
            dr.text((W - 100, y + 44), t, font=font(58), fill=WHITE, anchor="rm")
            arrow(dr, 100, y + 44, p >= 0, color, 14)
            dr.text((140, y + 44), f"{abs(p):.2f}%", font=font(54), fill=color, anchor="lm")
            y += 140
        y += 40
    return img


def slide_bars(d, sl):
    """Horizontal bars around a zero line, e.g. sector performance."""
    img, dr = base(d, sl["title"])
    bars = sl["bars"][:11]
    top, rowh, mid = 640, min(90, 1000 / max(len(bars), 1)), 330
    span = max(abs(p) for _, p in bars) or 1
    dr.line([(mid, top - 20), (mid, top + rowh * len(bars))], fill=GOLD_DARK, width=3)
    for i, (name, p) in enumerate(bars):
        y = top + i * rowh
        color = GREEN if p >= 0 else RED
        w = 230 * abs(p) / span
        x0, x1 = (mid, mid + w) if p >= 0 else (mid - w, mid)
        dr.rounded_rectangle([x0, y + 12, max(x1, x0 + 4), y + rowh - 12], 8, fill=color)
        dr.text((mid + (w + 14 if p >= 0 else -w - 14), y + rowh / 2), f"{p:+.2f}%", font=font(30), fill=color,
                anchor="lm" if p >= 0 else "rm")
        rtl_text(dr, (W - 80, y + rowh / 2), name, 40, WHITE, anchor="rm")
    return img


def cover(d, title, sub=""):
    """Reel cover: big hook inside the 3:4 area Instagram shows on the profile grid."""
    img, dr = base({**d, "market": d.get("market")}, "")
    lines = wrap(title, 104, W - 140)[:4]
    y = 960 - len(lines) * 62
    for line in lines:
        rtl_text(dr, (W // 2, y), line, 104, WHITE, anchor="ma")
        y += 124
    if sub:
        rtl_text(dr, (W // 2, y + 30), sub, 52, ACCENT, anchor="ma")
    return img


def slide_setup(d, sl):
    img, dr = base(d, sl["title"])
    s = sl["setup"]
    draw_candles(img, dr, s["candles"], (60, W - 190, 640, 1320), (1350, 1460),
                 lines=[(s["sma20_series"], ACCENT), (s["sma50_series"], (120, 160, 230))],
                 levels=[(s["target"], "יעד", GREEN), (s["trigger"], "כניסה", ACCENT), (s["stop"], "סטופ", RED)])
    y = 1530
    dr.line([(80, y), (130, y)], fill=ACCENT, width=6)
    dr.text((145, y), "SMA 20", font=font(30), fill=MUTED, anchor="lm")
    dr.line([(330, y), (380, y)], fill=(120, 160, 230), width=6)
    dr.text((395, y), "SMA 50", font=font(30), fill=MUTED, anchor="lm")
    dr.text((W - 80, y), f"RSI {s['rsi']:.0f}", font=font(34), fill=WHITE, anchor="rm")
    rtl_text(dr, (W - 80, 1590), "נר = יום · 3 חודשים · דוגמה לימודית", 30, MUTED)
    return img


def draw_visual(img, dr, kind, top):
    """Small teaching diagrams for the lesson slides."""
    cx = W // 2
    if kind == "candle":
        for x, (o, c, h, l) in ((cx - 200, (1, 3, 3.6, 0.5)), (cx + 200, (3, 1, 3.6, 0.5))):
            color = GREEN if c > o else RED
            yy = lambda v: top + 520 - v * 130
            dr.line([(x, yy(h)), (x, yy(l))], fill=color, width=6)
            dr.rectangle([x - 60, yy(max(o, c)), x + 60, yy(min(o, c))], fill=color)
            for v, lab in ((h, "גבוה"), (max(o, c), "סגירה" if c > o else "פתיחה"),
                           (min(o, c), "פתיחה" if c > o else "סגירה"), (l, "נמוך")):
                if x < cx:
                    rtl_text(dr, (x - 85, yy(v)), lab, 32, MUTED, anchor="rm")
                else:
                    rtl_text(dr, (x + 85, yy(v)), lab, 32, MUTED, anchor="lm")
    elif kind == "index":
        names = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "JPM", "..."]
        for i, n in enumerate(names):
            col, row = i % 5, i // 5
            x, y = 90 + col * 185, top + row * 120
            dr.rounded_rectangle([x, y, x + 165, y + 90], 16, fill=(22, 18, 10), outline=GOLD_DARK, width=2)
            dr.text((x + 82, y + 45), n, font=font(34), fill=ACCENT, anchor="mm")
        dr.text((cx, top + 320), "= S&P 500", font=font(64), fill=WHITE, anchor="ma")
    elif kind in ("trend", "levels", "volume"):
        import math
        pts = [(80 + i * 23, top + 420 - i * 7 - 70 * math.sin(i / 3.2)) for i in range(40)]
        if kind == "levels":
            for y, lab, color in ((top + 140, "התנגדות", RED), (top + 400, "תמיכה", GREEN)):
                for xx in range(80, W - 80, 30):
                    dr.line([(xx, y), (xx + 18, y)], fill=color, width=4)
                rtl_text(dr, (W - 80, y - 50), lab, 34, color)
            pts = [(80 + i * 23, top + 270 - 125 * math.sin(i / 2.2)) for i in range(40)]
        if kind == "volume":
            for i in range(40):
                h = 40 + 30 * math.sin(i * 1.7) ** 2 + (150 if i in (24, 25) else 0)
                dr.rectangle([75 + i * 23, top + 600 - h, 90 + i * 23, top + 600], fill=GOLD_DARK)
        dr.line(pts, fill=GREEN if kind != "levels" else ACCENT, width=8, joint="curve")
    elif kind == "bond":
        # you lend at the start, get interest each year and the money back at maturity
        y, xs = top + 300, [140 + i * 200 for i in range(5)]
        dr.line([(100, y), (W - 100, y)], fill=GOLD_DARK, width=6)
        dr.rectangle([xs[0] - 50, y, xs[0] + 50, y + 200], fill=RED)
        rtl_text(dr, (xs[0], y + 230), "מלווים", 32, RED, anchor="ma")
        for i, x in enumerate(xs[1:], 1):
            h = 70 if i < 4 else 260
            dr.rectangle([x - 40, y - h, x + 40, y], fill=GREEN if i == 4 else ACCENT)
            dr.text((x, y + 20), f"{i}", font=font(34), fill=MUTED, anchor="ma")
        rtl_text(dr, (xs[2], y - 110), "ריבית", 32, ACCENT, anchor="ma")
        rtl_text(dr, (xs[4], y - 310), "ריבית + קרן", 32, GREEN, anchor="ma")
        rtl_text(dr, (W // 2, y + 80), "שנים", 30, MUTED, anchor="ma")
    elif kind == "pe":
        dr.rounded_rectangle([140, top + 60, 470, top + 260], 26, fill=ACCENT)
        dr.text((305, top + 160), "$100", font=font(72), fill=INK, anchor="mm")
        dr.text((cx, top + 160), "/", font=font(90), fill=MUTED, anchor="mm")
        dr.rounded_rectangle([610, top + 60, 940, top + 260], 26, fill=(22, 18, 10), outline=ACCENT, width=3)
        dr.text((775, top + 160), "$5", font=font(72), fill=WHITE, anchor="mm")
        rtl_text(dr, (305, top + 300), "מחיר מניה", 32, MUTED, anchor="ma")
        rtl_text(dr, (775, top + 300), "רווח למניה", 32, MUTED, anchor="ma")
        dr.text((cx, top + 400), "P/E = 20", font=font(80), fill=GREEN, anchor="ma")


def slide_lesson(d, sl):
    img, dr = base(d, sl["title"])
    lines = wrap(sl["text"], 60, W - 190)
    y = 660
    dr.rounded_rectangle([W - 82, y + 4, W - 70, y + len(lines) * 84 - 12], 6, fill=ACCENT)
    for line in lines:
        rtl_text(dr, (W - 110, y), line, 60)
        y += 84
    if sl.get("visual"):
        draw_visual(img, dr, sl["visual"], max(y + 60, 960))
    else:
        paste_logo(img, ((W - 300) // 2, 1150), 300)
    return img


RENDERERS = {"intro": slide_intro, "tiles": slide_tiles, "movers": slide_movers,
             "setup": slide_setup, "bars": slide_bars, "lesson": slide_lesson,"hook": slide_hook, "chart": slide_chart, "table": slide_table, "earnings": slide_earnings,
             "bullets": slide_bullets, "outro": slide_outro}


def render_video(d, script, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    segments = []
    for i, sl in enumerate(script["slides"]):
        png, mp3, seg = (out_dir / f"slide_{i}.{ext}" for ext in ("png", "mp3", "mp4"))
        RENDERERS[sl["kind"]]({**d, **sl.get("head", {})}, sl).save(png)
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
