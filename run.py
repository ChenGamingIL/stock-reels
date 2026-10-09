"""Daily pipeline: pick a hot stock -> script -> narration + video -> Instagram.

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ticker")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--story-only", action="store_true", help="post only the Story slides, no Reel")
    ap.add_argument("--fetch-logo", action="store_true", help="save the Instagram profile picture to assets/logo.jpg")
    ap.add_argument("--check-instagram", action="store_true", help="verify the token and exit")
    args = ap.parse_args()

    if args.fetch_logo:
        from stockreels import instagram
        instagram.fetch_profile_picture(str(ROOT / "assets" / "logo.jpg"))
        print("[instagram] saved assets/logo.jpg")
        return

    if args.check_instagram:
        from stockreels import instagram
        print(f"[instagram] connected: {instagram.check_connection()}")
        return

    today = dt.date.today().isoformat()
    if args.sample:
        stock = json.loads((ROOT / "sample_data.json").read_text())
    else:
        ticker = args.ticker or data.pick_hot_ticker()
        print(f"[data] today's pick: {ticker}")
        stock = data.fetch_stock(ticker)

    sc = script.build_script(stock)
    out_dir = ROOT / "output" / f"{today}_{stock['ticker']}"
    video = render.render_video(stock, sc, out_dir)
    (out_dir / "caption.txt").write_text(sc["caption"])
    (out_dir / "script.json").write_text(json.dumps(sc, ensure_ascii=False, indent=2))
    print(f"[render] {video}")

    if args.dry_run or args.sample:
        print("[upload] skipped")
        return
    from stockreels import instagram
    tag = f"reel-{dt.datetime.now():%Y%m%d-%H%M}-{stock['ticker']}"
    slides = sorted(out_dir.glob("slide_*.png"), key=lambda p: int(p.stem.split("_")[1]))

    if not args.story_only:
        media_id, video_url = instagram.publish_reel(str(video), sc["caption"], tag=tag)
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
