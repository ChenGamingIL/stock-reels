"""Motion graphics for Reels and Stories.

Every slide is drawn on the same frame (gradient, grid, header, footer), so the frame stays put
and only the slide's own content moves: it builds in piece by piece from the top (lines rise and
fade in, charts and tables draw in from the left), holds while the narration plays, and fades
out just before the next slide. The index ticker along the top scrolls the whole time.
"""
import math
import re

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

FPS = 30
TAPE_H = 72        # the index ticker strip at the top of every slide
RISE = 46          # px a line travels as it fades in
IN_TIME = 0.5      # seconds each piece takes to arrive
OUT_TIME = 0.28    # content fade before the cut
TAPE_SPEED = 70    # px per second
COUNT_TIME = 1.0   # seconds a headline number takes to count up
OUT_LIFT = 34      # px the content drifts up as it leaves
FIRST_SHIFT = 0.45  # the first slide starts part way into its build-in, so the very first frame already hooks


def ease_out(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


class Pieces:
    """What a slide adds over the shared frame, split into horizontal bands, top to bottom."""

    def __init__(self, full, chrome, gap=14, max_pieces=9, backdrop=None):
        self.backdrop = backdrop  # a picture drifting behind the slide (Backdrop), or None for the plain frame
        self.count = full.info.get("count")  # a headline number that counts up as it arrives
        self.ltr = full.info.get("wipe") == "ltr"  # charts draw in from the left, Hebrew tables from the right
        self.full, self.chrome = full.convert("RGB"), chrome.convert("RGB")
        diff = np.asarray(ImageChops.difference(self.full, self.chrome).convert("L")) > 18
        diff[:TAPE_H + 4] = False
        self.coverage = diff.mean()
        mask = Image.fromarray((diff * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))
        self.mask = mask.filter(ImageFilter.GaussianBlur(1.5))
        # the still frame the animation lands on: exactly what the pieces add up to
        self.still = Image.composite(self.full, self.chrome, self.mask)
        if backdrop is not None:  # the header and footer stay put while the picture moves under them
            fixed = np.asarray(ImageChops.difference(self.chrome, backdrop.still).convert("L")) > 10
            self.chrome_mask = Image.fromarray((fixed * 255).astype(np.uint8)).filter(
                ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1))
        rows = np.flatnonzero(diff.any(1))
        bands = []
        for y in rows:
            if bands and y - bands[-1][1] <= gap:
                bands[-1][1] = y
            else:
                bands.append([y, y])
        while len(bands) > max_pieces:  # join the two closest neighbours
            i = min(range(len(bands) - 1), key=lambda k: bands[k + 1][0] - bands[k][1])
            bands[i] = [bands[i][0], bands[i + 1][1]]
            del bands[i + 1]
        self.bands = []
        for y0, y1 in bands:
            cols = np.flatnonzero(diff[y0:y1 + 1].any(0))
            x0, x1 = max(int(cols[0]) - 8, 0), min(int(cols[-1]) + 9, full.width)
            y0, y1 = max(int(y0) - 8, 0), min(int(y1) + 9, full.height)
            box = (x0, y0, x1, y1)
            self.bands.append({"box": box, "img": self.full.crop(box), "mask": self.mask.crop(box),
                               "wipe": (y1 - y0) > 300 and (x1 - x0) > 700})
        if self.count:
            from .render import font
            f = font(self.count["size"])
            x, y = self.count["xy"]
            l, t, r, b = f.getbbox(self.count["text"], anchor="ma")
            cy = y + (t + b) / 2
            self.count_band = next((i for i, bd in enumerate(self.bands) if bd["box"][1] <= cy <= bd["box"][3]), None)
            self.count_font = f
        n = len(self.bands)
        self.stagger = min(0.13, 0.95 / max(n, 1))

    def built_by(self):
        """Seconds until every piece has arrived."""
        end = 0.1 + self.stagger * max(len(self.bands) - 1, 0) + IN_TIME + 0.3
        if self.count and self.count_band is not None:
            end = max(end, 0.1 + self.stagger * self.count_band + COUNT_TIME + 0.05)
        return end

    def hook_shift(self):
        """Where the opening slide starts: the title already up and the headline number mid-count."""
        if self.count and self.count_band is not None:
            return 0.1 + self.stagger * self.count_band + 0.3 * COUNT_TIME
        return min(FIRST_SHIFT, self.built_by())

    def ground(self, t):
        """The empty frame at `t`: the shared chrome, over the moving picture when there is one."""
        if self.backdrop is None:
            return self.chrome.copy()
        img = self.backdrop.at(t)
        img.paste(self.chrome, (0, 0), self.chrome_mask)
        return img

    def frame(self, t, fade=1.0):
        """The slide at `t` seconds; `fade` < 1 dims the content toward the bare frame."""
        if self.coverage > 0.6:  # not drawn on the shared frame: a plain fade in
            return Image.blend(self.chrome, self.full, ease_out(t / IN_TIME) * fade)
        if t >= self.built_by() and fade >= 1:
            if self.backdrop is None:
                return self.still.copy()
            img = self.ground(t)
            img.paste(self.full, (0, 0), self.mask)
            return img
        img = self.ground(t)
        lift = round(OUT_LIFT * (1 - fade))
        for i, b in enumerate(self.bands):
            start = 0.1 + i * self.stagger
            p = ease_out((t - start) / (IN_TIME * (1.6 if b["wipe"] else 1)))
            if p <= 0:
                continue
            x0, y0, x1, y1 = b["box"]
            if self.count and i == self.count_band and t - start < COUNT_TIME:
                self._draw_count(img, (t - start) / COUNT_TIME, p * fade, round(RISE * (1 - p)) - lift)
                continue
            alpha = min(1.0, (t - start) / 0.25) if b["wipe"] else p
            alpha *= fade
            mask = b["mask"] if alpha >= 0.999 else b["mask"].point(lambda v, a=alpha: int(v * a))
            if b["wipe"]:
                bw, bh = x1 - x0, y1 - y0
                w = max(1, int(bw * p))
                part = (0, 0, w, bh) if self.ltr else (bw - w, 0, bw, bh)
                img.paste(b["img"].crop(part), (x0 + part[0], y0 - lift), mask.crop(part))
            else:
                img.paste(b["img"], (x0, y0 + round(RISE * (1 - p)) - lift), mask)
        return img

    def events(self, shift=0.0):
        """Sound cues for this slide, in seconds from its first frame: [(t, kind, arg)]."""
        out = []
        for i, b in enumerate(self.bands[:7]):
            start = 0.1 + i * self.stagger - shift
            if self.count and i == self.count_band:
                out += [(start, "riser", COUNT_TIME), (start + COUNT_TIME, "ding", None)]
            elif start + IN_TIME * 0.55 > 0:
                out.append((start + IN_TIME * 0.55, "pop", None))
        return out

    def _draw_count(self, img, progress, alpha, dy):
        text = counting(self.count["text"], ease_out(progress))
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        x, y = self.count["xy"]
        ImageDraw.Draw(layer).text((x, y + dy), text, font=self.count_font,
                                   fill=tuple(self.count["color"]) + (int(255 * alpha),), anchor="ma")
        img.paste(layer, (0, 0), layer)


NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def counting(text, p):
    """`text` with its number at fraction p of its value: "+6.4%" at 0.5 is "+3.2%"."""
    m = NUM.search(text)
    if not m:
        return text
    num = m.group(0)
    if re.fullmatch(r"(1[89]|20)\d\d", num) and text == num:  # a year doesn't count up
        return text
    dec = len(num.split(".")[1]) if "." in num else 0
    v = float(num.replace(",", "")) * p
    shown = f"{v:,.{dec}f}" if "," in num else f"{v:.{dec}f}"
    return text[:m.start()] + shown + text[m.end():]


def shine(img, t, y=268, x0=60, x1=1020):
    """A light running along the gold rule under the header as a slide arrives."""
    p = t / 0.7
    if not 0 <= p <= 1:
        return
    dr = ImageDraw.Draw(img)
    cx = x1 - (x1 - x0) * ease_out(p)
    for k in range(24):
        a = 1 - k / 24
        c = (int(232 + 23 * a), int(196 + 50 * a), int(120 + 100 * a))
        for sx in (cx + k * 6, cx - k * 6):
            if x0 <= sx <= x1:
                dr.line([(sx, y - 1), (sx + 6, y - 1)], fill=c, width=4)


class Backdrop:
    """A picture behind a slide, slowly pushing in and drifting up, like a camera move."""

    def __init__(self, img, zoom_per_s=0.014, max_zoom=0.14):
        self.still = img.convert("RGB")
        self.zoom_per_s, self.max_zoom = zoom_per_s, max_zoom

    def at(self, t):
        z = 1 + min(self.zoom_per_s * max(t, 0), self.max_zoom)
        w, h = self.still.width / z, self.still.height / z
        x0 = (self.still.width - w) / 2
        y0 = (self.still.height - h) * 0.42  # a touch above centre, so the move reads as rising
        return self.still.resize(self.still.size, Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))


class Tape:
    """The ticker strip, drawn twice side by side so it can scroll without a seam."""

    def __init__(self, strip, loop):
        self.strip, self.loop = strip, loop

    def paste(self, img, seconds):
        if self.strip is None or self.loop <= 0:
            return
        off = int(seconds * TAPE_SPEED) % self.loop
        img.paste(self.strip.crop((off, 0, off + img.width, TAPE_H)), (0, 0))


class Glow:
    """A soft gold light drifting slowly behind everything, so the frame never sits dead still."""

    def __init__(self, size=1300, strength=0.075, color=(232, 196, 120)):
        r = np.hypot(*np.meshgrid(np.linspace(-1, 1, size), np.linspace(-1, 1, size)))
        alpha = (np.clip(1 - r, 0, 1) ** 2.2 * 255 * strength).astype(np.uint8)
        self.mask = Image.fromarray(alpha)
        self.fill = Image.new("RGB", (size, size), color)
        self.size = size

    def paste(self, img, seconds):
        cx = img.width / 2 + 330 * math.sin(2 * math.pi * seconds / 17 + 1.3)
        cy = img.height * 0.52 + 380 * math.sin(2 * math.pi * seconds / 23)
        img.paste(self.fill, (int(cx - self.size / 2), int(cy - self.size / 2)), self.mask)


GLOW = None


def frames(pieces, dur, tape=None, t0=0.0, fade_out=True, shift=0.0):
    """Yield every frame of one slide as raw RGB bytes. `shift` starts the build-in part way through."""
    global GLOW
    GLOW = GLOW or Glow()
    n = max(1, math.ceil(dur * FPS))
    for k in range(n):
        t = k / FPS
        fade = 1.0
        if fade_out and t > dur - OUT_TIME:
            fade = max(0.0, (dur - t) / OUT_TIME)
        img = pieces.frame(t + shift, fade)
        GLOW.paste(img, t0 + t)
        shine(img, t + shift)
        if tape:
            tape.paste(img, t0 + t)
        yield img.tobytes()
