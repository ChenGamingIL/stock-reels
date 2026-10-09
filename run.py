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
from pathlib import Path

from stockreels import data, render, script

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ticker")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--check-instagram", action="store_true", help="verify the token and exit")
    args = ap.parse_args()

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
    media_id = instagram.publish_reel(str(video), sc["caption"])
    data.save_to_history(stock["ticker"], today)
    print(f"[upload] published reel {media_id}")


if __name__ == "__main__":
    main()
