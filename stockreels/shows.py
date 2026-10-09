"""Scripts for the pre-market show and the evening lesson (the morning hot stock is in script.py).

All numbers come from the data; narration is built from templates so nothing is invented.
"""
from .lessons import LESSONS, lesson_for
from .script import DISCLAIMER

HASHTAGS = "#שוקההון #מניות #וולסטריט #בורסה #השקעות #מסחר #stocks #trading"


def _pct_words(p):
    return f"{'עולה' if p >= 0 else 'יורד'} {abs(p):.1f} אחוז"


def _money(v):
    return f"${v:,.2f}"


SETUP_TEXT = {
    "pullback": {
        "name": "פולבק לממוצע 20",
        "why": ["מגמה עולה: מעל ממוצע 50 ו-200", "המחיר חזר לממוצע 20 העולה", "RSI התקרר בלי לשבור מגמה"],
        "narr": "{t} במגמה עולה, מעל ממוצע 50 וממוצע 200. המחיר חזר לממוצע 20 וה-RSI ירד ל-{rsi}. "
                "סוחרי סווינג מחפשים כאן המשך של המגמה אחרי מנוחה.",
    },
    "breakout": {
        "name": "פריצת שיא 20 יום",
        "why": ["מגמה עולה: מעל ממוצע 50 ו-200", "סגירה מעל השיא של 20 יום", "ווליום פי {vr} מהממוצע"],
        "narr": "{t} סגרה מעל השיא של 20 הימים האחרונים, עם ווליום פי {vr} מהממוצע. "
                "פריצה עם ווליום מראה שהקונים חזקים.",
    },
}


def premarket_script(m):
    slides = [{
        "kind": "intro", "title": "לקראת הפתיחה בוול סטריט",
        "lines": [m["date"], "חוזים, סחורות, מניות זזות וסטאפ סווינג"],
        "narration": "סקירה לקראת פתיחת המסחר בוול סטריט. מה קורה בחוזים, מי זזה בפרה-מרקט, וסטאפ סווינג לימודי.",
    }]
    ov = {o["symbol"]: o for o in m["overview"]}
    if ov:
        parts = [f"{o['label'].replace('חוזה ', 'החוזה על ')} {_pct_words(o['pct'])}"
                 for s in ("ES=F", "NQ=F") if (o := ov.get(s))]
        if "^VIX" in ov:
            parts.append(f"מדד הפחד VIX עומד על {ov['^VIX']['price']:.1f}")
        if "BTC-USD" in ov:
            parts.append(f"והביטקוין {_pct_words(ov['BTC-USD']['pct'])}")
        slides.append({"kind": "tiles", "title": "מצב השווקים", "tiles": m["overview"],
                       "narration": ". ".join(parts) + "."})
    mv = m["movers"]
    if mv["gainers"] or mv["losers"]:
        when = "בפרה-מרקט" if m["movers_premarket"] else "אתמול"
        top = (mv["gainers"] or mv["losers"])[0]
        slides.append({"kind": "movers", "title": f"מי זזה {when}", "movers": mv,
                       "narration": f"המניות שבולטות {when}: {top[0]} {_pct_words(top[1])}"
                                    + (f", ו-{mv['losers'][0][0]} {_pct_words(mv['losers'][0][1])}" if mv["losers"] and top not in mv["losers"] else "")
                                    + "."})
    if m["earnings"]:
        slides.append({"kind": "bullets", "title": "דוחות השבוע", "bullets": [f"{t} · {d}" for t, d in m["earnings"]],
                       "narration": "החברות הגדולות שמפרסמות דוחות השבוע: " + ", ".join(t for t, _ in m["earnings"]) + "."})
    s = m.get("setup")
    if s:
        txt = SETUP_TEXT[s["kind"]]
        fmt = {"t": s["ticker"], "rsi": f"{s['rsi']:.0f}", "vr": f"{s['vol_ratio']:.1f}"}
        slides += [
            {"kind": "setup", "title": f"סטאפ סווינג: {txt['name']}", "setup": s, "head": {"ticker": s["ticker"], "price": s["price"]},
             "narration": txt["narr"].format(**fmt)},
            {"kind": "bullets", "title": "למה זה סטאפ", "bullets": [b.format(**fmt) for b in txt["why"]],
             "head": {"ticker": s["ticker"], "price": s["price"]},
             "narration": "שלושה תנאים: מגמה עולה, " + ("חזרה לממוצע" if s["kind"] == "pullback" else "פריצה של השיא")
                          + ", ו" + ("מומנטום שהתקרר." if s["kind"] == "pullback" else "ווליום גבוה.")},
            {"kind": "table", "title": "התוכנית (דוגמה לימודית)", "head": {"ticker": s["ticker"], "price": s["price"]},
             "rows": [("טריגר כניסה מעל", _money(s["trigger"])), ("סטופ", _money(s["stop"])),
                      ("יעד (פי 2 מהסיכון)", _money(s["target"])), ("סיכון עד הסטופ", f"{s['risk_pct']:.1f}%"),
                      ("יחס סיכוי/סיכון", "1:2")],
             "narration": f"ככה סוחר סווינג היה בונה תוכנית: כניסה רק אם המחיר עובר את {s['trigger']:.2f}, "
                          f"סטופ ב-{s['stop']:.2f}, ויעד ב-{s['target']:.2f}, פי שניים מהסיכון. "
                          "זו דוגמה לימודית לשיטה, לא המלצה."},
        ]
    slides.append({"kind": "outro", "title": "עקבו לסקירה כל יום לפני הפתיחה",
                   "narration": "עקבו לסקירה כל יום לפני הפתיחה, ושיעור בסיס כל ערב. זה לא ייעוץ השקעות."})
    caption = ("סקירה לקראת הפתיחה בוול סטריט: חוזים, מניות זזות" + (", דוחות השבוע" if m["earnings"] else "")
               + (f" וסטאפ סווינג לימודי על {s['ticker']}" if s else "") + ".\n"
               + "הסטאפ הוא דוגמה לימודית לשיטת מסחר. " + DISCLAIMER + "\n\n" + HASHTAGS + " #פרהמרקט #סווינג")
    return {"slides": slides, "caption": caption}


def lesson_script(day=None):
    n, title, points = lesson_for(day)
    nxt = LESSONS[n % len(LESSONS)][0]
    slides = [{"kind": "intro", "title": title, "lines": [f"שיעור {n} בסדרת הבסיס", "שוק ההון בדקה"],
               "narration": f"שיעור {n} בסדרת הבסיס: {title}"}]
    for p in points:
        heading, text = p[0], p[1]
        slides.append({"kind": "lesson", "title": heading, "text": text, "visual": p[2] if len(p) > 2 else None,
                       "narration": f"{heading}. {text}"})
    slides.append({"kind": "outro", "title": f"מחר: {nxt}",
                   "narration": f"מחר בערב: {nxt}. עקבו כדי לא לפספס."})
    caption = (f"שיעור {n}: {title}\n"
               + "בשיעור: " + ", ".join(p[0] for p in points) + ". הכל בדקה אחת.\n"
               + "שמרו את הפוסט ועקבו לשיעור חדש כל ערב.\n" + DISCLAIMER + "\n\n" + HASHTAGS + " #לימודשוקההון")
    return {"slides": slides, "caption": caption, "number": n}


def session_script(m):
    """Market-open snapshot or end-of-day wrap, posted as Story slides only."""
    spx = next((t for t in m["tiles"] if t["symbol"] == "^GSPC"), None)
    is_open = m["kind"] == "open"
    slides = [{"kind": "intro", "title": "הפעמון צלצל בוול סטריט" if is_open else "סיכום יום המסחר",
               "lines": [m["date"], f"S&P 500 {spx['pct']:+.2f}%" if spx else ""],
               "narration": ""}]
    slides.append({"kind": "tiles", "title": "איך נפתח השוק" if is_open else "איך נסגר השוק",
                   "tiles": m["tiles"], "narration": ""})
    if m.get("sectors"):
        slides.append({"kind": "bars", "title": "סקטורים היום", "bars": m["sectors"], "narration": ""})
    if m["movers"]["gainers"] or m["movers"]["losers"]:
        slides.append({"kind": "movers", "title": "מי זזה בפתיחה" if is_open else "הבולטות של היום",
                       "movers": m["movers"], "narration": ""})
    slides.append({"kind": "outro", "title": "נתראה בסיכום הערב" if is_open else "מחר 08:00: המניה החמה הבאה",
                   "narration": ""})
    return {"slides": slides, "caption": ""}
