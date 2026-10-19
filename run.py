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

from stockreels import data, render, script, series

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
               "close": ["bars", "tiles"], "lesson": [], "didyouknow": []}


def pick_story_slides(show, sc, out_dir):
    """[(png, slide)] for the Stories; slide is None for the Reel cover."""
    if os.environ.get("STORY_SLIDES") == "all":
        return [(out_dir / f"slide_{i}.png", sl) for i, sl in enumerate(sc["slides"])]
    kinds = [sl["kind"] for sl in sc["slides"]]
    picked = []
    for k in STORY_KINDS[show]:
        if k == "cover" and (out_dir / "cover.png").exists():
            picked.append((out_dir / "cover.png", None))
        elif k in kinds:
            i = kinds.index(k)
            picked.append((out_dir / f"slide_{i}.png", sc["slides"][i]))
        if show == "close" and picked:
            break  # sectors if we have them, otherwise the index tiles
    return picked


def story_clips(stock, picked, out_dir):
    """Each Story as a short animated clip: the slide builds in, the cover slowly pushes in."""
    from PIL import Image

    clips = []
    for i, (png, sl) in enumerate(picked):
        out = out_dir / f"story_{i}.mp4"
        if sl is None:
            render.still_clip(Image.open(png).convert("RGB"), out)
        else:
            render.story_clip(stock, sl, out)
        clips.append(out)
    return clips


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", choices=["hot", "premarket", "open", "lesson", "didyouknow", "close", "shabbat"], default="hot")
    ap.add_argument("--ticker")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--story-only", action="store_true", help="post only the Story slides, no Reel")
    ap.add_argument("--fetch-logo", action="store_true", help="save the Instagram profile picture to assets/logo.jpg")
    ap.add_argument("--highlights", help="post Highlight Story sets: 'all', keys like bonds,basics, or basics@4 for one slide")
    ap.add_argument("--when-due", action="store_true", help="shabbat: post only if it's ~30 min before candle lighting")
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

    if args.show == "shabbat" and args.dry_run:
        from stockreels import shabbat
        print(f"[shabbat] quiet now: {shabbat.is_quiet()}, times: {shabbat.candle_lighting()}")
        return

    if args.show == "shabbat":
        from stockreels import shabbat
        chag = False
        if args.when_due:  # the 10-minute schedule: post only ~30 min before candle lighting, once
            due = shabbat.story_due()
            posted = ROOT / "posted.json"
            done = json.loads(posted.read_text()) if posted.exists() else {}
            key = (due[0] if due and due[0] else dt.datetime.now()).date().isoformat()
            if not due or done.get("shabbat") == key:
                print(f"[shabbat] not due now ({'already posted' if due else 'outside the window'})")
                return
            candles, havdalah, parasha, chag = due
        else:
            info = None if args.sample else shabbat.candle_lighting()
            candles, havdalah, parasha = info if info else (None, None, None)
        print(f"[shabbat] candles {candles} havdalah {havdalah} {parasha}")
        out_dir = ROOT / "output" / f"{dt.date.today().isoformat()}_SHABBAT"
        out_dir.mkdir(parents=True, exist_ok=True)
        card = out_dir / "shabbat.png"
        render.shabbat_card(parasha, candles, havdalah, chag).save(card)
        if posting:
            from stockreels import instagram
            print(f"[upload] published shabbat story {instagram.publish_story_slides([card], f'shabbat-{dt.datetime.now():%Y%m%d-%H%M}')}")
            posted = ROOT / "posted.json"
            done = json.loads(posted.read_text()) if posted.exists() else {}
            done["shabbat"] = (candles or dt.datetime.now()).date().isoformat()
            posted.write_text(json.dumps(done, indent=2))
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
    ep = series.next_episode(args.show) if args.show in series.SHOWS else None
    if args.show == "hot":
        if args.sample:
            stock = json.loads((ROOT / "sample_data.json").read_text())
        else:
            ticker = args.ticker or data.pick_hot_ticker()
            print(f"[data] today's pick: {ticker}")
            stock = data.fetch_stock(ticker)
        sc, name = script.build_script(stock, ep, series.kicker("hot", ep)), stock["ticker"]
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
            sc, name = shows.premarket_script(m, ep, series.kicker("premarket", ep)), "PRE"
            stock = {"ticker": "PRE-MARKET", "market": market, "asof": data.asof()}
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
            stock = {"ticker": "LIVE" if args.show == "open" else "CLOSE", "market": market, "asof": data.asof()}
            name = args.show.upper()
            if args.show == "open":
                sc = shows.session_script(m)
                args.story_only = True  # a quick Story snapshot, no Reel
            else:  # the evening recap is a Reel: the close, the sectors, and the day's news
                if args.sample:
                    for t in m["tiles"]:  # the sample has futures; the real close has the indices
                        t["symbol"] = {"ES=F": "^GSPC", "NQ=F": "^IXIC", "YM=F": "^DJI"}.get(t["symbol"], t["symbol"])
                    m["why"] = [{"ticker": "NVDA", "pct": 4.1, "news": [
                        {"title": "Nvidia rises after new AI chip orders", "title_he": "אנבידיה עולה אחרי הזמנות חדשות לשבבי AI",
                         "publisher": "Reuters", "date": "19.10"}]}]
                    m["headlines"] = [{"title": "Stocks close higher as tech rallies", "title_he": "המניות נסגרו בעלייה בהובלת הטכנולוגיה",
                                       "publisher": "CNBC", "date": "19.10"}]
                else:
                    mk.session_news(m)
                sc = shows.close_script(m, ep, series.kicker("close", ep))
        elif args.show == "didyouknow":
            from stockreels import didyouknow
            sc = didyouknow.script(ep)
            name = f"DYK{ep}"
            stock = {"ticker": "הידעת?", "market": market}
        else:
            sc = shows.lesson_script(episode=ep)
            name = f"LESSON{sc['number']}"
            stock = {"ticker": f"#{sc['number']}", "market": market}

    out_dir = ROOT / "output" / f"{today}_{name}"
    if args.show == "open":
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, sl in enumerate(sc["slides"]):
            render.RENDERERS[sl["kind"]]({**stock, **sl.get("head", {})}, sl).save(out_dir / f"slide_{i}.png")
        video = None
    else:
        video = render.render_video(stock, sc, out_dir)
        first = sc["slides"][0]
        sub = {"hot": f"{stock.get('ticker')} · המניה החמה · פרק {ep}", "premarket": f"לפני הפעמון · פרק {ep}",
               "lesson": f"שיעור {sc.get('number')} · שוק ההון בדקה", "didyouknow": f"הידעת? · פרק {ep}",
               "close": f"סיכום היום · פרק {ep}"}[args.show]
        render.cover(stock, first["title"], sub).save(out_dir / "cover.png")
        sc["caption"] = polish_caption(sc["caption"])
    (out_dir / "caption.txt").write_text(sc["caption"])
    (out_dir / "script.json").write_text(json.dumps(sc, ensure_ascii=False, indent=2))
    print(f"[render] {video}")
    for sl in sc["slides"]:
        print(f"[script] {sl['kind']}: {sl['title']} | {sl.get('narration', '')[:160]}")
    print("[caption] " + sc["caption"].replace("\n", " / "))

    if args.dry_run or args.sample:
        picked = pick_story_slides(args.show, sc, out_dir)
        clips = story_clips(stock, picked, out_dir) if picked else []
        print(f"[story] {len(clips)} clip(s) rendered")
        if os.environ.get("PREVIEW") == "1" and not args.sample:  # attach to a release so it can be watched
            from stockreels import instagram
            rid = instagram._create_release(f"preview-{args.show}-{dt.datetime.now():%Y%m%d-%H%M}")
            for f in ([video] if video else []) + clips:
                print(f"[preview] {instagram._upload_asset(rid, str(f), Path(f).name, 'video/mp4')}")
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
        if ep:
            series.mark_posted(args.show, ep)
        if args.show == "premarket" and m.get("setup"):
            from stockreels import market as mk
            mk.log_setup(m["setup"], today)  # tomorrow's show reports how it played out
        print(f"[upload] published reel {media_id}")

    # STORY_MODE: "clips" (each Story slide as a short animated clip, default), "slides" (still
    # images), "video" (the whole Reel), "both" (slides and Reel) or "none"
    mode = os.environ.get("STORY_MODE") or "clips"
    try:  # a failed story shouldn't fail the day's run, the reel is already up
        if mode == "clips" and slides:
            try:
                clips = story_clips(stock, slides, out_dir)
            except Exception as e:  # still post the Story, as images
                print(f"[upload] story clips failed to render ({e}), posting images")
                mode = "slides"
            else:
                print(f"[upload] published story clips {instagram.publish_story_clips(clips, tag + '-story')}")
        if mode in ("slides", "both"):
            print(f"[upload] published story slides {instagram.publish_story_slides([p for p, _ in slides], tag + '-story')}")
        if mode in ("video", "both") and not args.story_only and video_url:
            print(f"[upload] published story video {instagram.publish_story(video_url=video_url)}")
    except Exception as e:
        print(f"[upload] story failed: {e}")


if __name__ == "__main__":
    main()
