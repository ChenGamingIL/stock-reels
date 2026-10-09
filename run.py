"""Daily pipeline: data -> script -> narration + video -> Instagram Reel + Story slides.

Three shows a day (Israel time): 08:00 hot stock, 15:30 pre-market review with a swing
setup, 20:00 basics lesson.

  python run.py --show premarket # pick the show: hot (default), premarket, lesson

  python run.py                  # full run, uploads to Instagram
  python run.py --dry-run        # build the video only
  python run.py --ticker NVDA    # force a ticker
  python run.py --check-instagram   # verify the Instagram token, post nothing
  python run.py --sample         # offline preview from sample_data.json (no market data, no upload)
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path

from stockreels import data, render, script

ROOT = Path(__file__).resolve().parent


CTA = "💾 שמרו את הפוסט · 📤 שלחו לחבר שמשקיע · 🔔 עקבו לעדכון יומי"


def polish_caption(caption, max_tags=5):
    """Call to action before the hashtags, and only a handful of hashtags (what Instagram recommends now)."""
    body, tags = [], []
    for line in caption.splitlines():
        words = line.split()
        if words and all(w.startswith("#") for w in words):
            tags += words
        else:
            body.append(line)
    text = "\n".join(body).strip()
    if CTA not in text:
        text += "\n\n" + CTA
    tags = list(dict.fromkeys(tags))[:max_tags]
    return text + ("\n\n" + " ".join(tags) if tags else "")


# Instagram cuts reach for accounts posting more than ~4-5 Stories a day, so each show
# posts only its strongest slide(s): 1 + 2 + 1 + 1 = 5 a day (the lesson lives in the feed).
STORY_KINDS = {"hot": ["cover"], "premarket": ["tiles", "setup"], "open": ["tiles"],
               "close": ["bars", "tiles"], "lesson": []}


def pick_story_slides(show, sc, out_dir):
    if os.environ.get("STORY_SLIDES") == "all":
        return sorted(out_dir.glob("slide_*.png"), key=lambda p: int(p.stem.split("_")[1]))
    kinds = [sl["kind"] for sl in sc["slides"]]
    picked = []
    for k in STORY_KINDS[show]:
        if k == "cover" and (out_dir / "cover.png").exists():
            picked.append(out_dir / "cover.png")
        elif k in kinds:
            picked.append(out_dir / f"slide_{kinds.index(k)}.png")
        if show == "close" and picked:
            break  # sectors if we have them, otherwise the index tiles
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", choices=["hot", "premarket", "open", "lesson", "close", "shabbat"], default="hot")
    ap.add_argument("--ticker")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--story-only", action="store_true", help="post only the Story slides, no Reel")
    ap.add_argument("--fetch-logo", action="store_true", help="save the Instagram profile picture to assets/logo.jpg")
    ap.add_argument("--highlights", help="post Highlight Story sets: 'all', keys like bonds,basics, or basics@4 for one slide")
    ap.add_argument("--check-instagram", action="store_true", help="verify the token and exit")
    args = ap.parse_args()

    if args.fetch_logo:
        from stockreels import instagram
        instagram.fetch_profile_picture(str(ROOT / "assets" / "logo.jpg"))
        print("[instagram] saved assets/logo.jpg")
        return

    posting = not (args.dry_run or args.sample or args.check_instagram or args.fetch_logo)
    if posting:
        from stockreels import shabbat
        if shabbat.is_quiet():
            print("[shabbat] Shabbat or Yom Tov now, not posting until havdalah")
            return

    if args.show == "shabbat":
        from stockreels import shabbat
        info = None if args.sample else shabbat.candle_lighting()
        candles, havdalah, parasha = info if info else (None, None, None)
        print(f"[shabbat] candles {candles} havdalah {havdalah} {parasha}")
        out_dir = ROOT / "output" / f"{dt.date.today().isoformat()}_SHABBAT"
        out_dir.mkdir(parents=True, exist_ok=True)
        card = out_dir / "shabbat.png"
        render.shabbat_card(parasha, candles, havdalah).save(card)
        if posting:
            from stockreels import instagram
            print(f"[upload] published shabbat story {instagram.publish_story_slides([card], f'shabbat-{dt.datetime.now():%Y%m%d-%H%M}')}")
        return

    if args.highlights:
        from stockreels import highlights
        keys = [h[0] for h in highlights.HIGHLIGHTS] if args.highlights == "all" else args.highlights.split(",")
        for key in keys:  # "basics@4" re-posts only slide 4 of a set
            key, _, only = key.partition("@")
            out_dir = ROOT / "output" / f"highlight_{key}"
            out_dir.mkdir(parents=True, exist_ok=True)
            slides = highlights.render_set(key, out_dir)
            if only:
                slides = [slides[int(i)] for i in only.split("+")]
            highlights.cover(key, out_dir / "cover.png")
            if args.dry_run:
                print(f"[highlights] rendered {key}: {len(slides)} slides")
                continue
            from stockreels import instagram
            ids = instagram.publish_story_slides(slides, f"highlight-{key}-{dt.datetime.now():%Y%m%d-%H%M}")
            print(f"[highlights] posted {key}: {ids}")
        return

    if args.check_instagram:
        from stockreels import instagram
        print(f"[instagram] connected: {instagram.check_connection()}")
        return

    today = dt.date.today().isoformat()
    if args.show == "hot":
        if args.sample:
            stock = json.loads((ROOT / "sample_data.json").read_text())
        else:
            ticker = args.ticker or data.pick_hot_ticker()
            print(f"[data] today's pick: {ticker}")
            stock = data.fetch_stock(ticker)
        sc, name = script.build_script(stock), stock["ticker"]
    else:
        from stockreels import shows
        market = (json.loads((ROOT / "sample_data.json").read_text())["market"] if args.sample
                  else data.fetch_market())
        if args.show == "premarket":
            if args.sample:
                m = json.loads((ROOT / "sample_premarket.json").read_text())
            else:
                from stockreels import market as mk
                m = mk.fetch_premarket()
                print(f"[data] setup: {(m['setup'] or {}).get('ticker')} {(m['setup'] or {}).get('kind')}")
            sc, name = shows.premarket_script(m), "PRE"
            stock = {"ticker": "PRE-MARKET", "market": market}
        elif args.show in ("open", "close"):
            if args.sample:
                p = json.loads((ROOT / "sample_premarket.json").read_text())
                m = {"kind": args.show, "date": p["date"], "tiles": p["overview"][:6], "movers": p["movers"],
                     "sectors": [["טכנולוגיה", 1.2], ["אנרגיה", 0.6], ["פיננסים", -0.3], ["נדל\"ן", -0.9]]}
            else:
                from stockreels import market as mk
                m = mk.fetch_session(args.show)
            if not m:
                print("[data] US market didn't trade today, nothing to post")
                return
            sc, name = shows.session_script(m), args.show.upper()
            stock = {"ticker": "LIVE" if args.show == "open" else "CLOSE", "market": market}
            args.story_only = True  # quick Story snapshots, no Reel
        else:
            sc = shows.lesson_script()
            name = f"LESSON{sc['number']}"
            stock = {"ticker": f"#{sc['number']}", "market": market}

    out_dir = ROOT / "output" / f"{today}_{name}"
    if args.show in ("open", "close"):
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, sl in enumerate(sc["slides"]):
            render.RENDERERS[sl["kind"]]({**stock, **sl.get("head", {})}, sl).save(out_dir / f"slide_{i}.png")
        video = None
    else:
        video = render.render_video(stock, sc, out_dir)
        first = sc["slides"][0]
        sub = {"hot": f"{stock.get('ticker')} · מניה חמה", "premarket": f"{today} · לפני הפתיחה",
               "lesson": f"שיעור {sc.get('number')} · שוק ההון בדקה"}[args.show]
        render.cover(stock, first["title"], sub).save(out_dir / "cover.png")
        sc["caption"] = polish_caption(sc["caption"])
    (out_dir / "caption.txt").write_text(sc["caption"])
    (out_dir / "script.json").write_text(json.dumps(sc, ensure_ascii=False, indent=2))
    print(f"[render] {video}")

    if args.dry_run or args.sample:
        print("[upload] skipped")
        return
    from stockreels import instagram
    tag = f"{args.show}-{dt.datetime.now():%Y%m%d-%H%M}-{name}"
    slides = pick_story_slides(args.show, sc, out_dir)

    if not args.story_only:
        media_id, video_url = instagram.publish_reel(str(video), sc["caption"], tag=tag,
                                                     cover_path=str(out_dir / "cover.png"))
        if args.show == "hot":
            data.save_to_history(stock["ticker"], today)
        print(f"[upload] published reel {media_id}")

    # STORY_MODE: "slides" (each slide as a Story image, default), "video", "both" or "none"
    mode = os.environ.get("STORY_MODE") or "slides"
    try:  # a failed story shouldn't fail the day's run, the reel is already up
        if mode in ("slides", "both"):
            print(f"[upload] published story slides {instagram.publish_story_slides(slides, tag + '-story')}")
        if mode in ("video", "both") and not args.story_only and video_url:
            print(f"[upload] published story video {instagram.publish_story(video_url=video_url)}")
    except Exception as e:
        print(f"[upload] story failed: {e}")


if __name__ == "__main__":
    main()
