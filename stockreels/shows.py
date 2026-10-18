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


TRACK_NARR = {"worked": "הגיע ליעד, פי 2 מהסיכון", "failed": "נכשל ונעצר בשפל שהוגדר מראש",
              "open": "הופעל ועדיין פתוח", "waiting": "עוד לא הופעל", "expired": "לא הופעל ונסגר"}


def premarket_script(m, episode=1, kicker=None):
    s = m.get("setup")
    slides = [{
        "kind": "intro", "title": "לקראת הפתיחה בוול סטריט", "head": {"kicker": kicker} if kicker else {},
        "lines": [m["date"], "חוזים, מניות זזות" + (" ודפוס לימודי" if s else " ודוחות")],
        "narration": "סקירה לקראת פתיחת המסחר בוול סטריט. מה קורה בחוזים, מי זזה בפרה-מרקט"
                     + (", ודפוס מסחר לימודי." if s else ", ומי מדווחת השבוע."),
    }]
    t = m.get("track")
    if t:
        e, tl = t["latest"], t["tally"]
        closed = tl["worked"] + tl["failed"]
        slides.append({"kind": "track", "title": "מה קרה לדפוס הקודם", "track": t, "head": {"not_advice": True},
                       "narration": f"קודם כל, מעקב. הדפוס הקודם על {e['ticker']} {TRACK_NARR[e['status']]}. "
                                    + (f"עד היום {tl['worked']} דפוסים עבדו ו-{tl['failed']} נכשלו. " if closed else "")
                                    + "אנחנו מראים גם את הכישלונות."})
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
    if s:
        txt = SETUP_TEXT[s["kind"]]
        fmt = {"t": s["ticker"], "rsi": f"{s['rsi']:.0f}", "vr": f"{s['vol_ratio']:.1f}"}
        head = {"ticker": s["ticker"], "price": s["price"], "not_advice": True}
        slides += [
            {"kind": "setup", "title": f"דפוס לימודי: {txt['name']}", "setup": s, "head": head,
             "narration": txt["narr"].format(**fmt) + " חשוב: זו דוגמה לימודית, לא ייעוץ פיננסי."},
            {"kind": "bullets", "title": "למה זה דפוס", "bullets": [b.format(**fmt) for b in txt["why"]], "head": head,
             "narration": "שלושה תנאים: מגמה עולה, " + ("חזרה לממוצע" if s["kind"] == "pullback" else "פריצה של השיא")
                          + ", ו" + ("מומנטום שהתקרר." if s["kind"] == "pullback" else "ווליום גבוה.")},
            # the method in general terms only: no entry, stop or target prices (Investment Advice Law)
            {"kind": "bullets", "title": "איך סוחרים בונים תוכנית", "head": head,
             "bullets": ["מחכים שהמחיר יאשר את הדפוס", "מגדירים מראש איפה הרעיון מתבטל", "יעד של פי 2 לפחות מהסיכון"],
             "narration": "ככה סוחרי סווינג עובדים עם דפוס כזה: מחכים לאישור של המחיר, מגדירים מראש איפה הרעיון מתבטל, "
                          "בדרך כלל מתחת לשפל האחרון, ומחפשים יעד של לפחות פי 2 מהסיכון. "
                          "זו דוגמה לימודית לשיטה. זה לא ייעוץ פיננסי ולא המלצה לקנות או למכור."},
        ]
    if s:
        outro = ("מחר: מה קרה לדפוס של היום", "מחר נבדוק מה קרה לדפוס של היום, גם אם הוא נכשל.")
    else:  # no textbook pattern today: say so rather than force one
        outro = ("היום אין דפוס שעומד בתנאים", "היום אף מניה לא עמדה בכל התנאים, ולכן אין דפוס. גם זה חלק מהשיטה.")
    slides.append({"kind": "outro", "title": outro[0],
                   "narration": f"{outro[1]} זה היה פרק {episode} של לפני הפעמון. עקבו, ושלחו לחבר שסוחר. זה לא ייעוץ השקעות."})
    caption = ("לפני הפעמון · פרק " + str(episode) + "\n"
               + "סקירה לקראת הפתיחה בוול סטריט: חוזים, מניות זזות" + (", דוחות השבוע" if m["earnings"] else "")
               + (f" ודפוס מסחר לימודי על {s['ticker']}" if s else "") + ".\n"
               + ("כל דפוס נבדק למחרת בשקיפות מלאה, גם כשהוא נכשל.\n" if s else "")
               + ("הדפוס הוא דוגמה לימודית לשיטת מסחר, לא ייעוץ פיננסי. " if s else "") + DISCLAIMER + "\n\n" + "#שוקההון #מניות #וולסטריט #פרהמרקט #סווינג")
    return {"slides": slides, "caption": caption}


def lesson_script(day=None):
    n, title, points = lesson_for(day)
    nxt = LESSONS[n % len(LESSONS)][0]
    slides = [{"kind": "intro", "title": title, "lines": [f"שיעור {n} בסדרת הבסיס", "שוק ההון בדקה"],
               "head": {"kicker": f"שוק ההון מאפס · שיעור {n}"},
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
