"""Render slides to 1080x1920 images and stitch them with narration into an MP4 Reel."""
import os
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

from .script import DISCLAIMER
from . import motion, sound
from .tts import LOUDNESS, synthesize

W, H = 1080, 1920
# burned-in captions sit in this band on Reels, so slide content ends above it
CAP_Y, CAP_H = 1530, 150
CONTENT_BOTTOM = CAP_Y - 20
# the captions themselves sit higher, inside Instagram's safe area: from about y=1540 down, the account
# name, the post text and the buttons cover the picture, and the side buttons take the right edge
CAP_TOP = int(os.environ.get("CAP_TOP", 1385))
CAP_MAX_W = 820
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


# dates and clock times first; a sign only counts when it isn't a Hebrew prefix hyphen like "ו-200";
# "#12" and "$5" keep their mark on the left of the number
NUM_RE = re.compile(r"\d{4}-\d{2}(?:-\d{2})?|\d{1,2}:\d{2}|(?:(?<![\u0590-\u05ff])[-+])?[$#]?\d[\d,.]*[%BMTx]?")

LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9&./'-]*(?: [A-Za-z0-9&./'-]+)+")


def _visual(text):
    # keep multi-word English names ("S&P 500", "Palo Alto Networks") and signed numbers like +6.4%
    # or -$1.2B in LTR order inside Hebrew lines
    text = LATIN_RUN.sub(lambda m: "\u2066" + m.group(0) + "\u2069", text)
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


def base(d, title, brand_y=H - 250):
    if d.get("bg") is not None:  # an AI picture (aiart.grade) instead of the terminal gradient and grid
        img = d["bg"].copy()
        dr = ImageDraw.Draw(img)
    else:
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
    if d.get("not_advice"):  # pattern slides say it outright, above the caption band
        msg = "דוגמה לימודית · לא ייעוץ פיננסי"
        tw = font(36).getlength(_visual(msg)) + 60
        dr.rounded_rectangle([(W - tw) / 2, CONTENT_BOTTOM - 66, (W + tw) / 2, CONTENT_BOTTOM - 6], 30,
                             fill=(40, 14, 10), outline=RED, width=3)
        rtl_text(dr, (W / 2, CONTENT_BOTTOM - 36), msg, 36, WHITE, anchor="mm")
    ty = 330
    if d.get("kicker"):  # series name and episode, on the first slide
        f = font(36)
        tw = f.getlength(_visual(d["kicker"])) + 48
        dr.rounded_rectangle([W - 70 - tw, 292, W - 70, 352], 30, outline=ACCENT, width=3)
        rtl_text(dr, (W - 94, 304), d["kicker"], 36, ACCENT)
        ty = 384
    for i, line in enumerate(wrap(title, 76, W - 140)[:3]):
        rtl_text(dr, (W - 70, ty + i * 100), line, 76)
    # footer: brand, where the numbers come from and when, disclaimer, on every slide
    dr.line([(60, H - 205), (W - 60, H - 205)], fill=GOLD_DARK, width=2)
    dr.text((60, brand_y), f"@{BRAND.lower()}", font=font(32), fill=ACCENT)
    if d.get("asof"):
        rtl_text(dr, (W - 60, brand_y + 2), f"נתונים: {d.get('source') or 'Yahoo Finance'} · \u2066{d['asof']}\u2069", 28, MUTED)
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


def tape_strip(d):
    """The ticker items in one long strip, repeated so a window of any offset is filled: (strip, loop length)."""
    items = d.get("market") or []
    if not items:
        return None, 0
    f = font(28)
    def item_w(name, pct):
        return f.getlength(name) + 12 + 26 + f.getlength(f"{abs(pct):.2f}%") + 60
    loop = int(sum(item_w(n, p) for n, _, p in items))
    reps = -(-(W + loop) // loop) + 1
    img = Image.new("RGB", (loop * reps, 72), (14, 12, 8))
    dr = ImageDraw.Draw(img)
    x = 30
    for _ in range(reps):
        for name, _, pct in items:
            color = GREEN if pct >= 0 else RED
            dr.text((x, 36), name, font=f, fill=MUTED, anchor="lm")
            x += f.getlength(name) + 12
            arrow(dr, x, 36, pct >= 0, color, 9)
            x += 26
            txt = f"{abs(pct):.2f}%"
            dr.text((x, 36), txt, font=f, fill=color, anchor="lm")
            x += f.getlength(txt) + 60
    return img, loop


def chrome(d):
    """The frame every slide shares: background, header, footer, no title or content."""
    return base({**d, "kicker": None}, "")[0]


def slide_hook(d, sl):
    """First frame carries the number: the week's move, big, with a sparkline under it."""
    img, dr = base(d, sl["title"])
    ch = d.get("change_5d_pct")
    y = 700
    if ch is not None:
        color = GREEN if ch >= 0 else RED
        dr.text((W // 2, y), f"{ch:+.1f}%", font=font(220), fill=color, anchor="ma")
        img.info["count"] = {"xy": (W // 2, y), "text": f"{ch:+.1f}%", "size": 220, "color": color}
        rtl_text(dr, (W // 2, y + 260), "בשבוע האחרון", 48, MUTED, anchor="ma")
        y += 360
    pts = (d.get("history") or [])[-30:]
    if len(pts) > 1:
        lo, hi = min(pts), max(pts)
        span = (hi - lo) or 1
        x0, x1, y0, y1 = 140, W - 140, y + 20, y + 240
        xy = [(x0 + (x1 - x0) * i / (len(pts) - 1), y1 - (y1 - y0) * (v - lo) / span) for i, v in enumerate(pts)]
        dr.line(xy, fill=ACCENT, width=7, joint="curve")
        dr.ellipse([xy[-1][0] - 13, xy[-1][1] - 13, xy[-1][0] + 13, xy[-1][1] + 13], fill=ACCENT)
        y = y1 + 50
    rtl_text(dr, (W // 2, y), " · ".join(x for x in (d.get("name"), d.get("sector")) if x), 40, MUTED, anchor="ma")
    return img


def slide_fact(d, sl):
    """'Did you know' opener: one huge number with what it measures."""
    img, dr = base(d, sl["title"])
    big = sl["big"]
    color = RED if big.startswith("-") else GREEN if big.startswith(("+", "x")) else ACCENT
    size = 300
    while font(size).getlength(big) > W - 160 and size > 120:
        size -= 10
    dr.text((W // 2, 760), big, font=font(size), fill=color, anchor="ma")
    img.info["count"] = {"xy": (W // 2, 760), "text": big, "size": size, "color": color}
    y = 760 + size + 60
    for line in wrap(sl["label"], 48, W - 200)[:2]:
        rtl_text(dr, (W // 2, y), line, 48, MUTED, anchor="ma")
        y += 66
    paste_logo(img, ((W - 160) // 2, min(y + 60, CONTENT_BOTTOM - 170)), 160)
    return img


def slide_news(d, sl):
    """Real headlines with publisher and date: the 'why is it moving' evidence."""
    img, dr = base(d, sl["title"])
    y = 640
    for n in sl["news"][:3]:
        he = n.get("title_he")
        lines = wrap(he or n["title"], 44, W - 200)[:3]
        orig = wrap(n["title"], 26, W - 200)[:2] if he else []
        h = 90 + len(lines) * 58 + len(orig) * 34 + (10 if orig else 0)
        if y + h > CONTENT_BOTTOM:
            break
        dr.rounded_rectangle([60, y, W - 60, y + h], 24, fill=(22, 18, 10), outline=GOLD_DARK, width=2)
        dr.rectangle([W - 70, y + 20, W - 64, y + h - 20], fill=ACCENT)
        dr.text((100, y + 26), n["publisher"], font=font(32), fill=ACCENT)
        dr.text((W - 100, y + 26), n["date"], font=font(32), fill=MUTED, anchor="ra")
        yy = y + 84
        for line in lines:
            if he:  # Hebrew translation large, the original headline under it as the source
                rtl_text(dr, (W - 100, yy), line, 44, WHITE)
            else:
                dr.text((100, yy), line, font=font(44), fill=WHITE)
            yy += 58
        for line in orig:
            dr.text((100, yy + 6), line, font=font(26), fill=MUTED)
            yy += 34
        y += h + 30
    return img


REC_HE = {"strong_buy": "קנייה חזקה", "buy": "קנייה", "hold": "החזקה", "underperform": "תשואת חסר",
          "sell": "מכירה", "strong_sell": "מכירה חזקה", "none": "אין"}


def slide_analysts(d, sl):
    """Wall Street consensus (third-party data): rating scale and the 12-month target range."""
    img, dr = base(d, sl["title"])
    a = sl["analysts"]
    y = 650
    rtl_text(dr, (W - 80, y), f"{a['count']} אנליסטים · קונצנזוס: {REC_HE.get(a.get('key') or 'none', a.get('key'))}", 46)
    if a.get("mean"):
        y += 110
        x0, x1 = 100, W - 100
        segs = [(GREEN, "קנייה חזקה"), ((120, 200, 110), "קנייה"), (ACCENT, "החזקה"), ((230, 140, 80), "מכירה"), (RED, "מכירה חזקה")]
        sw = (x1 - x0) / 5
        for i, (c, lab) in enumerate(segs):  # right to left: strong buy on the right
            xa = x1 - sw * (i + 1)
            dr.rounded_rectangle([xa + 4, y, xa + sw - 4, y + 34], 10, fill=c)
            rtl_text(dr, (xa + sw / 2, y + 50), lab, 26, MUTED, anchor="ma")
        mx = x1 - (x1 - x0) * (a["mean"] - 1) / 4
        dr.polygon([(mx - 20, y - 34), (mx + 20, y - 34), (mx, y - 4)], fill=WHITE)
        dr.text((mx, y - 44), f"{a['mean']:.1f}", font=font(34), fill=WHITE, anchor="ms")
        y += 150
    lo, mean, hi, price = a.get("target_low"), a.get("target_mean"), a.get("target_high"), d.get("price")
    if lo and hi and mean and price:
        rtl_text(dr, (W - 80, y), "מחיר יעד ל-12 חודשים", 40, MUTED)
        y += 150
        vmin, vmax = min(lo, price), max(hi, price)
        x0, x1 = 120, W - 120
        px = lambda v: x0 + (x1 - x0) * (v - vmin) / ((vmax - vmin) or 1)
        dr.line([(px(lo), y), (px(hi), y)], fill=GOLD_DARK, width=14)
        for v, lab, c, up in ((lo, "נמוך", MUTED, False), (hi, "גבוה", MUTED, False), (mean, "ממוצע", ACCENT, True)):
            dr.ellipse([px(v) - 14, y - 14, px(v) + 14, y + 14], fill=c)
            dr.text((px(v), y + 34), f"${v:,.0f}", font=font(32), fill=c, anchor="ma")
            rtl_text(dr, (px(v), y + 76), lab, 28, MUTED, anchor="ma")
        dr.line([(px(price), y - 60), (px(price), y + 20)], fill=WHITE, width=5)
        rtl_text(dr, (px(price), y - 70), f"עכשיו ${price:,.0f}", 32, WHITE, anchor="ms")
        up = (mean / price - 1) * 100
        y += 190
        rtl_text(dr, (W // 2, y), f"{up:+.1f}% עד היעד הממוצע", 54, GREEN if up >= 0 else RED, anchor="ma")
    return img


def slide_proscons(d, sl):
    """Bottom line in numbers: green points for, red points against."""
    img, dr = base(d, sl["title"])
    y = 650
    for items, color, label in ((sl["pros"], GREEN, "בעד"), (sl["cons"], RED, "נגד")):
        if not items:
            continue
        rtl_text(dr, (W - 80, y), label, 42, color)
        y += 72
        for b in items:
            dr.rounded_rectangle([60, y - 8, W - 60, y + 92], 22, fill=(22, 18, 10), outline=GOLD_DARK, width=2)
            dr.rectangle([W - 70, y + 12, W - 64, y + 72], fill=color)
            rtl_text(dr, (W - 100, y + 42), b, 46, WHITE, anchor="rm")
            y += 112
        y += 30
    return img


STATUS_HE = {"worked": ("הדפוס עבד", GREEN), "failed": ("הדפוס נכשל", RED), "open": ("עדיין פתוח", ACCENT),
             "waiting": ("עוד לא הופעל", MUTED), "expired": ("לא הופעל, נסגר", MUTED)}


def slide_track(d, sl):
    """Honest follow-up on the previous pattern, and the running tally including the failures."""
    img, dr = base(d, sl["title"])
    t = sl["track"]
    e = t["latest"]
    label, color = STATUS_HE[e["status"]]
    y = 650
    dr.rounded_rectangle([60, y, W - 60, y + 330], 28, fill=(22, 18, 10), outline=GOLD_DARK, width=3)
    dr.text((W - 100, y + 40), e["ticker"], font=font(72), fill=WHITE, anchor="ra")
    day = f"{e['date'][8:10]}.{e['date'][5:7]}"
    rtl_text(dr, (W - 100, y + 140), f"הדפוס מ-{day} · {'פריצה' if e['kind'] == 'breakout' else 'פולבק'}", 38, MUTED)
    dr.rounded_rectangle([100, y + 40, 470, y + 130], 22, fill=color)
    rtl_text(dr, (285, y + 85), label, 42, INK, anchor="mm")
    if e["status"] != "waiting":
        dr.text((285, y + 200), f"{e['move']:+.1f}%", font=font(80), fill=GREEN if e["move"] >= 0 else RED, anchor="mm")
    rtl_text(dr, (W - 100, y + 230), "מנקודת ההפעלה", 34, MUTED)
    y += 400
    tl = t["tally"]
    closed = tl["worked"] + tl["failed"]
    rtl_text(dr, (W - 80, y), "כל הדפוסים שפרסמנו עד היום", 40, MUTED)
    y += 80
    for i, (k, lab, c) in enumerate((("worked", "עבדו", GREEN), ("failed", "נכשלו", RED), ("expired", "לא הופעלו", MUTED))):
        x = W - 60 - (i + 1) * 320 + 20
        dr.rounded_rectangle([x, y, x + 300, y + 190], 24, fill=(22, 18, 10), outline=c, width=3)
        dr.text((x + 150, y + 30), str(tl[k]), font=font(84), fill=c, anchor="ma")
        rtl_text(dr, (x + 150, y + 136), lab, 34, MUTED, anchor="ma")
    if closed:
        rtl_text(dr, (W // 2, y + 240), f"אחוז הצלחה: {tl['worked'] / closed * 100:.0f}% מתוך {closed} שנסגרו", 38, WHITE, anchor="ma")
    return img


def slide_chart(d, sl):
    img, dr = base(d, sl["title"])
    img.info["wipe"] = "ltr"  # time runs left to right, so the chart draws in that way
    candles = d.get("candles") or []
    if len(candles) < 2:
        return slide_line_chart(d, sl, img, dr)
    draw_candles(img, dr, candles, (70, W - 190, 640, 1130), (1160, 1270))
    ch = d.get("change_6m_pct")
    if ch is not None:
        color = GREEN if ch >= 0 else RED
        dr.text((W // 2, 1300), f"{ch:+.1f}%", font=font(96), fill=color, anchor="ma")
        rtl_text(dr, (W // 2, 1420), "6 חודשים · כל נר = שבוע", 34, MUTED, anchor="ma")
    return img


def draw_candles(img, dr, candles, box, vol=None, lines=(), levels=(), tags=True):
    """Candlesticks in box=(x0, x1, y0, y1), optional volume band vol=(v0, v1).

    lines: [(series, color)] drawn over the candles (moving averages).
    levels: [(price, label, color)] horizontal dashed levels, with a price tag on the right axis if tags.
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
        if tags:
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
    img.info["wipe"] = "ltr"  # time runs left to right, so the chart draws in that way
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
        top, base_y = y + 120, 1400
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
    th = min(170, (CONTENT_BOTTOM - top - gap * 4) / ((len(tiles) + 1) // 2))
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
        y += 70
        for t, p in rows:
            dr.rounded_rectangle([60, y - 10, W - 60, y + 90], 24, fill=(22, 18, 10), outline=GOLD_DARK, width=2)
            dr.text((W - 100, y + 40), t, font=font(54), fill=WHITE, anchor="rm")
            arrow(dr, 100, y + 40, p >= 0, color, 14)
            dr.text((140, y + 40), f"{abs(p):.2f}%", font=font(50), fill=color, anchor="lm")
            y += 116
        y += 24
    return img


def slide_bars(d, sl):
    """Horizontal bars around a zero line, e.g. sector performance."""
    img, dr = base(d, sl["title"])
    bars = sl["bars"][:11]
    top, rowh, mid = 640, min(90, (CONTENT_BOTTOM - 660) / max(len(bars), 1)), 330
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


def _fit(text, size, max_w, low=40):
    while font(size).getlength(_visual(text)) > max_w and size > low:
        size -= 6
    return size


def _glow_text(img, xy, text, size, color, blur=28):
    """Text with a soft halo of its own colour behind it."""
    from PIL import ImageFilter
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=font(size), fill=tuple(color) + (200,), anchor="mm")
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    img.paste(layer, (0, 0), layer)
    ImageDraw.Draw(img).text(xy, text, font=font(size), fill=color, anchor="mm")


def _vignette(img, strength=0.75):
    from PIL import ImageFilter
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse([-260, -60, W + 260, H + 60], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(160))
    return Image.composite(img, Image.blend(img, Image.new("RGB", (W, H)), strength), mask)


def cover(d, title, sub="", big=None, color=None, badge=None, line=None, ask=None):
    """Reel cover, "big number" style (Chen's pick, 2026-10-21): the headline number huge and coloured,
    a gold badge above it and the hook under it, all inside the 3:4 area the profile grid shows
    (y 240 to 1680), over the day's AI picture when there is one."""
    bg = d.get("bg")
    # the handle and the data line go under the disclaimer, clear of the grid's crop
    img, dr = base({**d, "bg": _vignette(bg) if bg is not None else None, "kicker": None}, "", brand_y=H - 78)
    if not big:  # nothing to put big: the headline itself, large
        lines = wrap(line or title, 112, W - 140)[:4]
        y = 930 - len(lines) * 66
        for ln in lines:
            rtl_text(dr, (W // 2, y), ln, 112, WHITE, anchor="ma")
            y += 132
        if sub:
            rtl_text(dr, (W // 2, y + 30), sub, 52, ACCENT, anchor="ma")
        return img
    if badge:
        size = _fit(badge, 78, 700)
        tw = font(size).getlength(_visual(badge)) + 80
        dr.rounded_rectangle([(W - tw) / 2, 330, (W + tw) / 2, 450], 60, fill=ACCENT)
        rtl_text(dr, (W // 2, 390), badge, size, INK, anchor="mm")
    _glow_text(img, (W // 2, 790), big, _fit(big, 330, W - 100), tuple(color or ACCENT))
    dr = ImageDraw.Draw(img)
    y, size = 1030, 92
    while len(wrap(line or title, size, W - 140)) > 2 and size > 66:  # a long company name still fits in two lines
        size -= 4
    for ln in wrap(line or title, size, W - 140)[:2]:
        rtl_text(dr, (W // 2, y), ln, size, WHITE, anchor="ma")
        y += size + 20
    if ask:
        rtl_text(dr, (W // 2, y + 6), ask, 92, ACCENT, anchor="ma")
    if sub:
        rtl_text(dr, (W // 2, 1560), sub, 46, ACCENT, anchor="ma")
    return img


def slide_setup(d, sl):
    """The pattern on the chart, for teaching: structure levels only, no entry, stop or target prices."""
    img, dr = base(d, sl["title"])
    img.info["wipe"] = "ltr"  # time runs left to right, so the chart draws in that way
    s = sl["setup"]
    levels = [(s["recent_low"], "השפל האחרון", RED)] if s.get("recent_low") else []
    if s["kind"] == "breakout":
        levels.insert(0, (s["breakout_level"], "השיא של 20 יום", ACCENT))
    draw_candles(img, dr, s["candles"], (60, W - 190, 640, 1210), (1240, 1330),
                 lines=[(s["sma20_series"], ACCENT), (s["sma50_series"], (120, 160, 230))],
                 levels=levels, tags=False)
    y = 1390
    dr.line([(80, y), (130, y)], fill=ACCENT, width=6)
    dr.text((145, y), "SMA 20", font=font(30), fill=MUTED, anchor="lm")
    dr.line([(330, y), (380, y)], fill=(120, 160, 230), width=6)
    dr.text((395, y), "SMA 50", font=font(30), fill=MUTED, anchor="lm")
    dr.text((W - 80, y), f"RSI {s['rsi']:.0f}", font=font(34), fill=WHITE, anchor="rm")
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
    elif max(1150, y + 60) + 300 <= CONTENT_BOTTOM:  # the logo only where the text leaves room
        paste_logo(img, ((W - 300) // 2, max(1150, y + 60)), 300)
    return img


def slide_question(d, sl):
    """The question of the day: a big glowing question mark (or the topic's word) over the question."""
    img, dr = base(d, "")
    big = sl.get("big") or "?"
    _glow_text(img, (W // 2, 600), big, _fit(big, 300, W - 160), ACCENT)
    dr = ImageDraw.Draw(img)
    size = 84
    while len(wrap(sl["title"], size, W - 140)) > 3 and size > 64:
        size -= 4
    y = 860
    for ln in wrap(sl["title"], size, W - 140)[:3]:
        rtl_text(dr, (W // 2, y), ln, size, WHITE, anchor="ma")
        y += size + 22
    rtl_text(dr, (W // 2, y + 36), "התשובה בפחות מדקה", 46, MUTED, anchor="ma")
    return img


def shabbat_card(parasha=None, candles=None, havdalah=None, chag=False):
    """Story before candle lighting: two candles, Shabbat Shalom (or Chag Sameach), the times."""
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for cx in (W // 2 - 130, W // 2 + 130):  # soft warm glow around each flame
        gd.ellipse([cx - 90, 435, cx + 90, 615], fill=(255, 190, 80, 110))
    from PIL import ImageFilter
    glow = glow.filter(ImageFilter.GaussianBlur(55))
    img.paste(glow, (0, 0), glow)
    dr = ImageDraw.Draw(img)
    for cx in (W // 2 - 130, W // 2 + 130):
        dr.rounded_rectangle([cx - 42, 600, cx + 42, 960], 14, fill=(246, 240, 226))
        dr.line([(cx, 600), (cx, 570)], fill=(60, 50, 30), width=5)
        dr.ellipse([cx - 26, 470, cx + 26, 580], fill=(255, 196, 80))
        dr.ellipse([cx - 13, 515, cx + 13, 575], fill=(255, 244, 200))
    dr.rounded_rectangle([W // 2 - 260, 950, W // 2 + 260, 985], 12, fill=ACCENT)
    rtl_text(dr, (W // 2, 1060), "חג שמח" if chag else "שבת שלום", 150, ACCENT, anchor="ma")
    y = 1260
    if parasha:
        rtl_text(dr, (W // 2, y), parasha, 56, WHITE, anchor="ma")
        y += 90
    if candles and havdalah:
        rtl_text(dr, (W // 2, y), f"הדלקת נרות {candles:%H:%M} · צאת {'החג' if chag else 'שבת'} {havdalah:%H:%M}", 40, MUTED, anchor="ma")
        rtl_text(dr, (W // 2, y + 56), "(תל אביב)", 32, MUTED, anchor="ma")
        y += 120
    rtl_text(dr, (W // 2, y + 20), f"נחזור במוצאי {'החג' if chag else 'שבת'} עם כל העדכונים", 44, WHITE, anchor="ma")
    paste_logo(img, ((W - 170) // 2, 1640), 170)
    return img


def week_card():
    """Story after Shabbat ends: green candles climbing, a good and green week to everyone."""
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    from PIL import ImageFilter
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W // 2 - 380, 380, W // 2 + 380, 980], fill=(52, 199, 106, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img.paste(glow, (0, 0), glow)
    dr = ImageDraw.Draw(img)
    # five candles, each closing higher than the last
    lows = [880, 820, 760, 690, 610]
    for i, low in enumerate(lows):
        cx = 250 + i * 145
        top, bottom = low - 190 - i * 18, low
        dr.line([(cx, top - 45), (cx, bottom + 40)], fill=GREEN, width=6)
        dr.rounded_rectangle([cx - 38, top, cx + 38, bottom], 8, fill=GREEN)
    dr.line([(170, 960), (W - 170, 960)], fill=GOLD_DARK, width=3)
    rtl_text(dr, (W // 2, 1040), "שבוע טוב", 150, ACCENT, anchor="ma")
    rtl_text(dr, (W // 2, 1230), "וירוק לכולם!", 110, GREEN, anchor="ma")
    rtl_text(dr, (W // 2, 1420), "נתראה מחר ב-08:00 עם המניה החמה", 46, WHITE, anchor="ma")
    paste_logo(img, ((W - 170) // 2, 1640), 170)
    return img


RENDERERS = {"intro": slide_intro, "tiles": slide_tiles, "movers": slide_movers,
             "setup": slide_setup, "bars": slide_bars, "lesson": slide_lesson,"hook": slide_hook, "chart": slide_chart, "table": slide_table, "earnings": slide_earnings,
             "bullets": slide_bullets, "outro": slide_outro, "news": slide_news, "analysts": slide_analysts,
             "proscons": slide_proscons, "track": slide_track, "fact": slide_fact, "question": slide_question}


HEBREW = re.compile(r"[\u0590-\u05ff]")


def caption_chunks(words, max_words=3, max_chars=20):
    """Group timed words into short caption lines: [([(word, start, end)], start, end)]."""
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or sum(len(x[0]) + 1 for x in cur) + len(w[0]) > max_chars):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


CAP_SIZE = 74
POP = (0.78, 1.1)  # a new caption line pops in over two frames: small, a touch too big, then settles


def caption_png(chunk, active, path, scale=1.0):
    """One caption frame: big bold words with a dark outline, the word being spoken in gold and a size up."""
    img = Image.new("RGBA", (W, CAP_H), (0, 0, 0, 0))
    if chunk:
        size = CAP_SIZE
        f = font(size)
        widths = [f.getlength(_visual(w[0])) for w in chunk]
        gap = f.getlength(" ")
        total = sum(widths) + gap * (len(chunk) - 1)
        if total > CAP_MAX_W:  # a long word: shrink the whole line rather than run under the side buttons
            size = int(size * CAP_MAX_W / total)
            f = font(size)
            widths = [f.getlength(_visual(w[0])) for w in chunk]
            gap = f.getlength(" ")
            total = sum(widths) + gap * (len(chunk) - 1)
        # drawn at 1x on a canvas of its own, then scaled for the pop
        line = Image.new("RGBA", (W, CAP_H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(line)
        cy = CAP_H / 2
        dr.rounded_rectangle([W / 2 - total / 2 - 30, cy - size * 0.78, W / 2 + total / 2 + 30, cy + size * 0.78], 26,
                             fill=(0, 0, 0, 150))
        # right to left, word by word; a run of English words keeps its own left-to-right order
        order, run = [], []
        for i, w in enumerate(chunk):
            if HEBREW.search(w[0]):
                order += run[::-1] + [i]
                run = []
            else:
                run.append(i)
        order += run[::-1]
        kw = {"direction": "rtl"} if HAS_RAQM else {}
        x = W / 2 + total / 2
        for i in order:
            on = i == active
            wf = font(int(size * 1.08)) if on else f
            dx = (widths[i] - wf.getlength(_visual(chunk[i][0]))) / 2  # the bigger word stays centred on its slot
            dr.text((x - dx, cy), _visual(chunk[i][0]), font=wf, fill=ACCENT if on else WHITE, anchor="rm",
                    stroke_width=6, stroke_fill=(0, 0, 0), **kw)
            x -= widths[i] + gap
        if abs(scale - 1) > 0.01:
            sw, sh = int(W * scale), int(CAP_H * scale)
            line = line.resize((sw, sh), Image.LANCZOS)
            box = ((W - sw) // 2, (CAP_H - sh) // 2)
            if scale > 1:
                line = line.crop((-box[0], -box[1], -box[0] + W, -box[1] + CAP_H))
                box = (0, 0)
            img.paste(line, box, line)
        else:
            img = line
    img.save(path)


def caption_track(words, dur, out_dir, prefix):
    """Write caption frames and an ffmpeg concat list that shows each for its spoken time."""
    out_dir = Path(out_dir)
    blank = out_dir / f"{prefix}_cap_blank.png"
    caption_png([], 0, blank)
    entries, t, n = [], 0.0, 0
    for chunk in caption_chunks(words):
        for i, w in enumerate(chunk):
            start = w[1]
            end = chunk[i + 1][1] if i + 1 < len(chunk) else w[2]
            if start > t:  # short pauses keep the last line up, longer ones clear it
                if entries and start - t < 0.5:
                    entries[-1] = (entries[-1][0], entries[-1][1] + start - t)
                else:
                    entries.append((blank, start - t))
                t = start
            if i == 0 and end - t > 0.3:  # the line pops in
                for sc in POP:
                    path = out_dir / f"{prefix}_cap_{n}.png"
                    caption_png(chunk, i, path, sc)
                    n += 1
                    entries.append((path, 1 / motion.FPS))
                    t += 1 / motion.FPS
            path = out_dir / f"{prefix}_cap_{n}.png"
            caption_png(chunk, i, path)
            n += 1
            end = max(end, t + 0.08)
            entries.append((path, end - t))
            t = end
    entries.append((blank, max(dur - t, 0.1)))
    lst = out_dir / f"{prefix}_caps.txt"
    lst.write_text("".join(f"file '{p.name}'\nduration {d:.3f}\n" for p, d in entries) + f"file '{blank.name}'\n")
    return lst


def _encode_slide(pieces, dur, mp3, caps, tape, t0, total, offset, seg, fade_out=True, shift=0.0, camera=None):
    """Stream the slide's frames into ffmpeg with its narration, progress bar and captions."""
    inputs = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", str(motion.FPS), "-i", "-"]
    inputs += ["-i", str(mp3)] if mp3 else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    graph, last = "", "0:v"
    if total:
        inputs += ["-f", "lavfi", "-i", f"color=c=0xE8C478:s={W}x8:r=30"]
        graph += f"[0:v][2:v]overlay=x='-W+W*({offset:.3f}+t)/{total:.3f}':y=70:eval=frame:shortest=1[p];"
        last = "p"
    if caps:
        inputs += ["-f", "concat", "-safe", "0", "-i", str(caps)]
        graph += f"[{last}][3:v]overlay=0:{CAP_TOP}:eof_action=pass[c];"
        last = "c"
    graph += f"[{last}]format=yuv420p[v];[1:a]apad,aresample=44100[a]"
    proc = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph,
        "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-r", str(motion.FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "aac", "-b:a", "160k", str(seg),
    ], stdin=subprocess.PIPE)
    try:
        for raw in motion.frames(pieces, dur, tape, t0, fade_out, shift, camera):
            proc.stdin.write(raw)
    except BrokenPipeError:
        pass
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed on {seg}")


def backdrop_image(path):
    """The graded AI picture for this Reel, or None."""
    if not path:
        return None
    try:
        from .aiart import grade
        return grade(path)
    except Exception as e:  # a broken download never stops the Reel
        print(f"[aiart] can't use {path}: {e.__class__.__name__}: {e}")
        return None


CAMERA = os.environ.get("CAMERA", "1") != "0"
GAP = 0.3  # seconds of air after each slide's narration before the cut


def render_video(d, script, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    captions = os.environ.get("CAPTIONS", "1") != "0"
    # narrate everything first: the progress bar needs the total length
    parts = []
    bg = backdrop_image(script.get("bg"))
    last = len(script["slides"]) - 1
    for i, sl in enumerate(script["slides"]):
        dd = {**d, **sl.get("head", {})}
        drift = None
        if bg is not None and i in (0, last):  # the opening and the sign-off play over the AI picture
            dd["bg"], drift = bg, motion.Backdrop(bg)
        png, mp3 = out_dir / f"slide_{i}.png", out_dir / f"slide_{i}.mp3"
        full = RENDERERS[sl["kind"]](dd, sl)
        full.save(png)
        dur, words = synthesize(sl["narration"], str(mp3))
        parts.append((motion.Pieces(full, chrome(dd), backdrop=drift), mp3, dur + GAP, words))
    total = sum(p[2] for p in parts)
    tape = motion.Tape(*tape_strip(d))
    segments, events, offset = [], [(0.0, "hit", None)], 0.0
    for i, (pieces, mp3, dur, words) in enumerate(parts):
        seg = out_dir / f"slide_{i}.mp4"
        caps = caption_track(words, dur, out_dir, f"s{i}") if captions and words else None
        shift = pieces.hook_shift() if i == 0 else 0.0
        cam = motion.Camera(pieces, dur, shift, hook=i == 0) if CAMERA else None
        _encode_slide(pieces, dur, mp3, caps, tape, offset, total, offset, seg, fade_out=i < len(parts) - 1,
                      shift=shift, camera=cam)
        if i:
            events.append((offset, "whoosh", None))
        events += [(offset + t, kind, arg) for t, kind, arg in pieces.events(shift)]
        segments.append(seg)
        offset += dur
    listing = out_dir / "segments.txt"
    listing.write_text("".join(f"file '{s.name}'\n" for s in segments))
    final = out_dir / "reel.mp4"
    if os.environ.get("MUSIC", "1") == "0":
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-c:v", "copy", "-af", LOUDNESS, "-ar", "44100", "-c:a", "aac", "-b:a", "160k",
                        "-movflags", "+faststart", str(final)], check=True)
        return final
    # the show's music under the voice, ducking whenever someone speaks, plus the effects; one loudness pass
    music_wav, fx_wav = out_dir / "music.wav", out_dir / "fx.wav"
    sound.write_wav(music_wav, sound.music(script.get("music", "hot"), total))
    sound.write_wav(fx_wav, sound.effects(events, total))
    graph = ("[0:a]aformat=channel_layouts=stereo,aresample=44100,asplit=2[vo][key];"
             "[1:a]volume=0.25[mu];[mu][key]sidechaincompress=threshold=0.012:ratio=6:attack=30:release=450[bed];"
             f"[vo][bed][2:a]amix=inputs=3:duration=first:normalize=0,{LOUDNESS}[a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-i", str(music_wav), "-i", str(fx_wav), "-filter_complex", graph,
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-ar", "44100", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(final)], check=True)
    return final


def story_clip(d, sl, out, seconds=7.0):
    """A Story as a short animated clip: the slide builds in over the shared frame and holds."""
    dd = {**d, **sl.get("head", {})}
    full = RENDERERS[sl["kind"]](dd, sl)
    drift = motion.Backdrop(dd["bg"]) if dd.get("bg") is not None else None
    _encode_slide(motion.Pieces(full, chrome(dd), backdrop=drift), seconds, None, None, motion.Tape(*tape_strip(dd)),
                  0.0, 0, 0, out, fade_out=False)
    return out


def still_clip(img, out, seconds=6.0):
    """A finished image (like the Reel cover) as a Story clip: a slow push-in."""
    src = Path(out).with_suffix(".png")
    img.save(src)
    z = f"(1+0.05*t/{seconds:.2f})"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(src),
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-filter_complex",
                    f"[0:v]scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,crop={W}:{H},"
                    f"setsar=1,fade=t=in:st=0:d=0.4,format=yuv420p[v]",
                    "-map", "[v]", "-map", "1:a", "-t", f"{seconds:.2f}", "-r", "30",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "aac", str(out)], check=True)
    return out
