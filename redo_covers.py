"""New "big number" covers for the Reels that went up before the cover redesign (2026-10-21).

Instagram's API can't change the cover of a Reel that's already published, so this renders each
cover as a picture to swap in from the app: Reel > ... > Edit > Edit cover > Add from camera roll.
The numbers are the ones each Reel showed when it was posted.

  python redo_covers.py output/redo     # AI pictures from GitHub only; AI_ART=0 renders without them
"""
import os
import sys
import time
from pathlib import Path

from PIL import Image

import run
from stockreels import aiart, didyouknow, render, shows

# newest first, the order the profile grid shows them; lesson 7 went up three times, one cover covers all
POSTS = [
    {"date": "2026-10-21", "show": "didyouknow", "ep": 3},
    {"date": "2026-10-21", "show": "hot", "ep": 4, "ticker": "PANW", "name": "Palo Alto Networks", "pct": -14.3,
     "look": "a glowing digital padlock over a dark network of circuits"},
    {"date": "2026-10-20", "show": "close", "ep": 2, "pct": 0.27},
    {"date": "2026-10-20", "show": "lesson", "ep": 12},
    {"date": "2026-10-20", "show": "premarket", "ep": 2, "pct": -0.25},
    {"date": "2026-10-20", "show": "didyouknow", "ep": 2},
    {"date": "2026-10-20", "show": "hot", "ep": 3, "ticker": "IREN", "name": "IREN", "pct": -20.3,
     "look": "bitcoin mining machines glowing in a dark warehouse"},
    {"date": "2026-10-19", "show": "close", "ep": 1, "pct": 0.42},
    {"date": "2026-10-19", "show": "lesson", "ep": 11},
    {"date": "2026-10-19", "show": "premarket", "ep": 1, "pct": 0.49},
    {"date": "2026-10-19", "show": "didyouknow", "ep": 1},
    {"date": "2026-10-19", "show": "hot", "ep": 2, "ticker": "CRWV", "name": "CoreWeave", "pct": -25.2,
     "look": "rows of glowing GPU servers in a dark AI data center"},
    {"date": "2026-10-18", "show": "lesson", "ep": 10},
    {"date": "2026-10-18", "show": "hot", "ep": 1, "ticker": "SMCI", "name": "Super Micro Computer", "pct": -24.4,
     "look": "a glowing server motherboard with gold circuits, macro"},
    {"date": "2026-10-15", "show": "lesson", "ep": 7},
    {"date": "2026-10-14", "show": "lesson", "ep": 6},
    {"date": "2026-10-09", "show": "hot", "ep": None, "ticker": "BBD", "name": "Banco Bradesco", "pct": 20.9,
     "look": "a heavy bank vault door half open with gold bars inside"},
]


def spec_of(p):
    """(stock, script, sub) the way run.py had them for this post, enough for run.cover_spec."""
    show, ep, m = p["show"], p["ep"], None
    if show == "hot":
        stock = {"ticker": p["ticker"], "name": p["name"], "change_5d_pct": p["pct"]}
        sc = {"slides": [{"title": p["name"]}]}
    elif show == "premarket":
        stock, sc = {"ticker": "PRE-MARKET"}, {"slides": [{"title": "לקראת הפתיחה בוול סטריט"}]}
        m = {"overview": [{"symbol": "ES=F", "pct": p["pct"]}]}
    elif show == "close":
        stock, sc = {"ticker": "CLOSE"}, {"slides": [{"title": "ככה נסגרה וול סטריט היום", "big": f"{p['pct']:+.2f}%"}]}
    elif show == "didyouknow":
        stock, sc = {"ticker": "הידעת?"}, didyouknow.script(ep)
    else:
        sc = shows.lesson_script(episode=ep)
        stock = {"ticker": f"#{sc['number']}"}
    y, mo, d = p["date"].split("-")
    stock["asof"] = f"{d}.{mo}.{y[2:]}"
    sub = {"hot": f"המניה החמה · פרק {ep}" if ep else "המניה החמה", "premarket": f"לפני הפעמון · פרק {ep}",
           "lesson": f"שיעור {sc.get('number')} · שוק ההון בדקה", "didyouknow": f"הידעת? · פרק {ep}",
           "close": f"סיכום היום · פרק {ep}"}[show]
    return stock, sc, sub, run.cover_spec(show, stock, sc, m)


def grid(covers, out):
    """How the profile grid will look: three across, each tile the 3:4 middle of its cover."""
    tw, th, gap = 360, 480, 6
    rows = (len(covers) + 2) // 3
    sheet = Image.new("RGB", (3 * tw + 2 * gap, rows * th + (rows - 1) * gap), (255, 255, 255))
    for i, path in enumerate(covers):
        tile = Image.open(path).convert("RGB").crop((0, 240, 1080, 1680)).resize((tw, th), Image.LANCZOS)
        sheet.paste(tile, ((i % 3) * (tw + gap), (i // 3) * (th + gap)))
    sheet.save(out, quality=90)
    return out


def main(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    covers, last = [], 0.0
    for i, p in enumerate(POSTS, 1):
        stock, sc, sub, spec = spec_of(p)
        bg = None
        if os.environ.get("AI_ART", "1") != "0":
            wait = 46 - (time.time() - last)  # the free service gives one picture per 45 seconds
            if wait > 0 and not os.environ.get("FAL_KEY"):
                time.sleep(wait)
            what = p.get("look") or aiart.subject(p["show"], stock, p["ep"] or 0)
            print(f"[redo] {p['date']} {p['show']}: {what}", flush=True)
            last = time.time()
            bg = aiart.generate(what, out_dir / f"bg_{i:02d}.jpg", seed=int(p["date"].replace("-", "")) + i,
                                attempts=2, timeout=90)
        title = sc["slides"][0]["title"]
        img = render.cover({**stock, "bg": render.backdrop_image(bg)}, title, sub, **spec).convert("RGB")
        path = out_dir / f"{i:02d}_{p['date']}_{p['show']}{'_' + p['ticker'] if p.get('ticker') else ''}.jpg"
        img.save(path, quality=92)
        covers.append(path)
        print(f"[redo] {path.name}: {spec.get('big')} | {spec.get('line')} | {'AI picture' if bg else 'no picture'}",
              flush=True)
    print(f"[redo] grid: {grid(covers, out_dir / '00_grid.jpg')}")
    return covers


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "output/redo")
