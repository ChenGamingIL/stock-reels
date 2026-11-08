"""Evergreen 4:5 carousels (1080 x 1350) for the profile: the "start here" post and save-worthy guides.

Carousels reach ~1.7x what Reels do for accounts under 5K followers, and they get saved, which tells
Instagram the post is worth showing to more people. These are meant to be pinned on the profile.

  python -m stockreels.carousel start_here        # render to output/carousel_start_here/
  python -m stockreels.carousel terms --post      # render and publish
"""
import datetime as dt
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

from . import render
from .render import ACCENT, GOLD_DARK, INK, MUTED, WHITE, font, paste_logo, rtl_text, wrap

W, H = 1080, 1350
ROOT = Path(__file__).resolve().parent.parent
BG_TOP, BG_BOTTOM = (20, 17, 11), (4, 4, 3)

CAROUSELS = {
    "start_here": {
        "caption": ("👋 חדשים כאן? התחילו מהפוסט הזה.\n"
                    "StocksisX מסביר את שוק ההון בעברית: פשוט, עם נתונים ומקורות, בלי רעש ובלי הבטחות.\n\n"
                    "💾 שמרו את הפוסט כדי לחזור לסדרות\n"
                    "💬 כתבו בתגובות: מה הכי מעניין אתכם בשוק ההון?\n\n"
                    "אין לראות בתוכן ייעוץ השקעות.\n\n"
                    "#שוקההון #מניות #השקעות #למתחילים #וולסטריט"),
        "slides": [
            {"kind": "cover", "kicker": "התחילו כאן", "title": "שוק ההון בעברית. פשוט, עם מספרים, בלי רעש.",
             "sub": "החליקו לראות מה תמצאו כאן"},
            {"kind": "list", "title": "הסדרות שלנו", "items": [
                ("המניה החמה", "המניה שזזה הכי חזק השבוע, ולמה"),
                ("הידעת?", "רגעים גדולים מהיסטוריית הבורסה"),
                ("שוק ההון מאפס", "שיעורי בסיס, אחד אחרי השני"),
                ("שאלה של היום", "שאלה אחת שכל משקיע שואל"),
                ("לפני הפעמון", "מה קורה לפני הפתיחה בוול סטריט"),
                ("סיכום היום", "איך נסגר היום ומי זזה"),
            ]},
            {"kind": "list", "title": "למי זה מתאים", "items": [
                ("מתחילים", "רוצים להבין מה זה מניה, מדד ו-ETF"),
                ("משקיעים לטווח ארוך", "רוצים סדר, בלי לרדוף אחרי כותרות"),
                ("סקרנים", "אוהבים לדעת למה השוק זז"),
            ]},
            {"kind": "list", "title": "הכללים שלנו", "items": [
                ("כל מספר עם מקור", "ותאריך, על כל שקף"),
                ("מראים גם כישלונות", "כל דפוס לימודי נבדק בפרק הבא"),
                ("בלי מחירי יעד", "לומדים שיטה, לא מקבלים טיפים"),
                ("לא ייעוץ השקעות", "התוכן הוא לימודי בלבד"),
            ]},
            {"kind": "cta", "title": "עקבו כדי לא לפספס פרק",
             "lines": ["שמרו את הפוסט", "שלחו לחבר שמתחיל להשקיע", "כתבו בתגובות מה לפרק הבא"]},
        ],
    },
    "terms": {
        "caption": ("10 מושגים שכל משקיע מתחיל חייב להכיר 📚\n"
                    "החליקו, ושמרו את הפוסט לפעם הבאה שמישהו יגיד \"מכפיל רווח\" ולא תבינו על מה הוא מדבר.\n\n"
                    "💾 שמרו · 📤 שלחו לחבר שמתחיל להשקיע · 💬 איזה מושג להסביר לעומק?\n\n"
                    "אין לראות בתוכן ייעוץ השקעות.\n\n"
                    "#שוקההון #השקעות #למתחילים #מניות #חינוךפיננסי"),
        "slides": [
            {"kind": "cover", "kicker": "שמרו את זה", "title": "10 מושגים שכל משקיע מתחיל חייב להכיר",
             "sub": "החליקו"},
            {"kind": "terms", "items": [
                ("1", "מניה", "חלק קטן בבעלות על חברה. החברה מרוויחה, גם אתם."),
                ("2", "מדד", "סל של מניות שמראה איך חלק מהשוק מתנהג, כמו S&P 500"),
            ]},
            {"kind": "terms", "items": [
                ("3", "קרן סל (ETF)", "קרן שעוקבת אחרי מדד ונסחרת כמו מניה. דרך פשוטה לפזר."),
                ("4", "דיבידנד", "חלק מהרווח שהחברה מחלקת לבעלי המניות."),
            ]},
            {"kind": "terms", "items": [
                ("5", "מכפיל רווח (P/E)", "כמה משלמים על כל שקל רווח של החברה. גבוה = ציפיות גבוהות."),
                ("6", "שוק שורי / דובי", "שורי: השוק עולה לאורך זמן. דובי: ירידה של 20% ומעלה."),
            ]},
            {"kind": "terms", "items": [
                ("7", "ריבית דריבית", "רווח על הרווח. ככה כסף קטן גדל בזמן ארוך."),
                ("8", "פיזור", "לא לשים את כל הכסף על מניה אחת. מקטין את הסיכון."),
            ]},
            {"kind": "terms", "items": [
                ("9", "תנודתיות", "כמה חזק המחיר קופץ למעלה ולמטה. יותר תנודתיות = יותר סיכון."),
                ("10", "סטופ לוס", "פקודה שמוכרת אוטומטית אם המחיר יורד לרמה שקבעתם מראש."),
            ]},
            {"kind": "cta", "title": "איזה מושג להסביר לעומק?",
             "lines": ["כתבו בתגובות", "שמרו לפעם הבאה", "עקבו לשיעורים הבאים"]},
        ],
    },
}


def _ground(n, total):
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        px.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle([24, 24, W - 24, H - 24], 36, outline=GOLD_DARK, width=3)
    paste_logo(img, (W - 150, 60), 90)
    dr.text((80, 105), f"@{render.BRAND.lower()}", font=font(34), fill=ACCENT, anchor="lm")
    if total > 1:  # page dots, so people know there's more to swipe
        x0 = W / 2 - (total - 1) * 14
        for i in range(total):
            c = ACCENT if i == n else (70, 60, 40)
            dr.ellipse([x0 + i * 28 - 7, H - 75, x0 + i * 28 + 7, H - 61], fill=c)
    return img, dr


def _title(dr, text, y, size=78):
    for line in wrap(text, size, W - 180):
        rtl_text(dr, (W - 90, y), line, size, WHITE)
        y += size + 22
    dr.line([(W - 90, y + 6), (W - 290, y + 6)], fill=ACCENT, width=6)
    return y + 60


def slide(sl, n, total):
    img, dr = _ground(n, total)
    k = sl["kind"]
    if k == "cover":
        f = font(44)
        tw = f.getlength(render._visual(sl["kicker"])) + 70
        dr.rounded_rectangle([W - 90 - tw, 300, W - 90, 380], 40, fill=ACCENT)
        rtl_text(dr, (W - 90 - tw / 2, 340), sl["kicker"], 44, INK, anchor="mm")
        y = 450
        for line in wrap(sl["title"], 104, W - 180):
            rtl_text(dr, (W - 90, y), line, 104, WHITE)
            y += 128
        rtl_text(dr, (W - 90, y + 50), sl["sub"], 50, ACCENT)
    elif k == "list":
        y = _title(dr, sl["title"], 240)
        gap = min(230, (H - 170 - y) // len(sl["items"]))
        for head, text in sl["items"]:
            dr.ellipse([W - 114, y + 24, W - 90, y + 48], fill=ACCENT)
            rtl_text(dr, (W - 135, y), head, 60, ACCENT)
            rtl_text(dr, (W - 135, y + 74), text, 44, WHITE)
            y += gap
    elif k == "terms":  # two terms a slide, each in its own half
        for j, (num, term, text) in enumerate(sl["items"]):
            y = 230 + j * 520
            dr.text((90, y - 20), num, font=font(190), fill=(80, 66, 40), anchor="la")
            rtl_text(dr, (W - 90, y), term, 84, ACCENT)
            yy = y + 125
            for line in wrap(text, 56, W - 440):  # clear of the big number on the left
                rtl_text(dr, (W - 90, yy), line, 56, WHITE)
                yy += 74
            if j == 0:
                dr.line([(90, y + 470), (W - 90, y + 470)], fill=(60, 50, 32), width=2)
    elif k == "cta":
        y = _title(dr, sl["title"], 330, 84)
        for line in sl["lines"]:  # no emoji on the slides: the font has none
            dr.ellipse([W - 112, y + 50, W - 88, y + 74], fill=ACCENT)
            rtl_text(dr, (W - 135, y + 30), line, 58, WHITE)
            y += 120
    return img


def build(key, out_dir=None):
    spec = CAROUSELS[key]
    out = Path(out_dir or ROOT / "output" / f"carousel_{key}")
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, sl in enumerate(spec["slides"]):
        p = out / f"{i:02d}.jpg"
        slide(sl, i, len(spec["slides"])).save(p, quality=93)
        paths.append(p)
    (out / "caption.txt").write_text(spec["caption"])
    return paths, spec["caption"]


def main():
    key = sys.argv[1]
    paths, caption = build(key)
    print(f"[carousel] {key}: {len(paths)} slides in {paths[0].parent}")
    if "--probe" in sys.argv:  # debugging: which hosted URL Instagram can fetch (nothing gets published)
        import os, requests
        from . import instagram
        tag = f"probe-{key}-{dt.datetime.now():%Y%m%d-%H%M%S}"
        slide = str(paths[0])

        # (1) how it used to be: a release asset, handed over as its github.com download link
        rid = instagram._create_release(tag)
        release_url = instagram._upload_asset(rid, slide, "probe.jpg", "image/jpeg")
        # (2) the same asset, but with the flaky github.com redirector resolved by us
        signed = None
        for _ in range(8):
            r = requests.get(release_url, allow_redirects=False, timeout=30)
            if r.is_redirect:
                signed = r.headers["Location"]
                break
            print(f"[probe] releases/download answered {r.status_code}, retrying")
            time.sleep(5)
        # (3) the fix: committed to the media branch, served by raw.githubusercontent.com
        raw_url = instagram.host_image(slide, f"probe/{tag}/slide_0.jpg")

        base = f"https://{instagram.HOST}/{instagram.VERSION}/{os.environ['IG_USER_ID']}/media"
        tok = os.environ["IG_ACCESS_TOKEN"]
        for name, url in [("release-download", release_url), ("release-signed", signed), ("raw", raw_url)]:
            if not url:
                print(f"[probe] {name}: could not be resolved")
                continue
            ours = requests.get(url, timeout=30)
            print(f"[probe] {name}: we get {ours.status_code} {ours.headers.get('Content-Type')} -> {url[:110]}")
            r = requests.post(base, data={"image_url": url, "is_carousel_item": "true",
                                          "media_type": "IMAGE", "access_token": tok}, timeout=60)
            print(f"[probe] {name}: Instagram {r.status_code} {r.text[:240]}")
        return

    if "--post" in sys.argv:
        from . import instagram
        mid = instagram.publish_carousel(paths, caption, f"carousel-{key}-{dt.datetime.now():%Y%m%d-%H%M}")
        print(f"[carousel] published {mid}")


if __name__ == "__main__":
    main()
