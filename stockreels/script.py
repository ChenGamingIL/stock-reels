"""Turn stock data into a Hebrew video script (slides + narration + caption).

Numbers shown on screen are always formatted from the data here, never from the
model, so the model can't invent a ratio. The model only writes the narration,
the "why it's interesting" / "risks" bullets and the Instagram caption.
"""
import json
import os

DISCLAIMER = "אין לראות בתוכן זה ייעוץ השקעות או המלצה לקנות או למכור ניירות ערך."
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")


def fmt_pct(v, already_pct=False):
    if v is None:
        return "—"
    return f"{v if already_pct else v * 100:+.1f}%".replace("+-", "-")


def fmt_x(v):
    return "—" if v is None else f"{v:.1f}"


def fmt_big(v):
    if v is None:
        return "—"
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(v) >= div:
            return f"${v / div:.1f}{suf}"
    return f"${v:,.0f}"


def ratio_rows(d):
    r = d["ratios"]
    rows = [
        ("מכפיל רווח (P/E)", fmt_x(r["pe"])),
        ("מכפיל רווח עתידי", fmt_x(r["forward_pe"])),
        ("מכפיל מכירות (P/S)", fmt_x(r["ps"])),
        ("PEG", fmt_x(r["peg"])),
        ("שולי רווח נקי", fmt_pct(r["profit_margin"]).lstrip("+")),
        ("צמיחה בהכנסות", fmt_pct(r["revenue_growth"])),
    ]
    return [row for row in rows if row[1] != "—"][:5]


def earnings_rows(d):
    rows = [(e["quarter"], fmt_big(e["revenue"]), "—" if e["eps"] is None else f"{e['eps']:.2f}")
            for e in d["earnings"]]
    return rows[-4:]


PROMPT = """אתה כותב תסריט לסרטון רילס קצר (45-60 שניות) בעברית, לערוץ אינסטגרם שמסביר על מניות חמות.
הנה הנתונים על המניה של היום (JSON):
{data}

כתוב JSON בלבד, בלי טקסט נוסף, במבנה הזה:
{{
  "hook": "משפט פתיחה קצר ומושך על המניה (עד 12 מילים)",
  "narration": {{
    "hook": "קריינות לשקף הפתיחה, 1-2 משפטים",
    "chart": "קריינות על תנועת המחיר לאחרונה, 1-2 משפטים",
    "ratios": "קריינות שמסבירה בפשטות מה המכפילים אומרים, 2 משפטים",
    "earnings": "קריינות על הדוח האחרון וההכנסות, 2 משפטים",
    "why": "קריינות על למה המניה מעניינת, 2 משפטים",
    "risks": "קריינות על הסיכונים, 1-2 משפטים",
    "outro": "סיום קצר שמזמין לעקוב, ומציין שזה לא ייעוץ השקעות"
  }},
  "why": ["3 נקודות קצרות (עד 6 מילים כל אחת) למה היא מעניינת"],
  "risks": ["2 נקודות קצרות (עד 6 מילים כל אחת) על סיכונים"],
  "caption": "כיתוב לפוסט באינסטגרם, 2-4 שורות, כולל משפט שזה לא ייעוץ השקעות",
  "hashtags": ["8 האשטגים רלוונטיים, בלי #"]
}}

כללים:
- השתמש רק במספרים שמופיעים בנתונים. אל תמציא מספרים.
- עברית פשוטה ומדוברת, משפטים קצרים שנוחים להקראה.
- כתוב מספרים בספרות. שמות חברות וסימולים באנגלית.
- מאוזן: לא להבטיח רווחים ולא להמליץ לקנות.
"""


def _llm_script(d):
    import anthropic

    slim = {k: v for k, v in d.items() if k != "history"}
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": PROMPT.format(data=json.dumps(slim, ensure_ascii=False))}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = text[text.find("{"): text.rfind("}") + 1]
    return json.loads(text)


def _template_script(d):
    """Used when no ANTHROPIC_API_KEY is set, so the pipeline still runs end to end."""
    name, r = d["name"], d["ratios"]
    move = d.get("change_5d_pct") or 0
    direction = "עלתה" if move >= 0 else "ירדה"
    le = d.get("last_earnings") or {}
    beat = le.get("surprise_pct")
    earn_line = (f"בדוח האחרון החברה {'עקפה' if beat >= 0 else 'פספסה'} את התחזיות ב-{abs(beat):.1f} אחוז."
                 if beat is not None else "בואו נראה איך נראו ההכנסות ברבעונים האחרונים.")
    return {
        "hook": f"{name} {direction} {abs(move):.1f}% השבוע. מה קורה?",
        "narration": {
            "hook": f"{name} {direction} {abs(move):.1f} אחוז בשבוע האחרון. בואו נבין למה כולם מדברים עליה.",
            "chart": f"ככה נראה המחיר בחצי השנה האחרונה: שינוי של {fmt_pct(d.get('change_6m_pct'), True)}.",
            "ratios": f"מכפיל הרווח עומד על {fmt_x(r['pe'])}, ומכפיל הרווח העתידי על {fmt_x(r['forward_pe'])}. "
                      "מכפיל נמוך יותר אומר שמשלמים פחות על כל דולר רווח.",
            "earnings": earn_line,
            "why": "יש כאן צמיחה, רווחיות ועניין גדול מצד המשקיעים.",
            "risks": "מצד שני, התמחור והתנודתיות הם סיכון שצריך לקחת בחשבון.",
            "outro": "",
        },
        "why": [f"צמיחה בהכנסות {fmt_pct(r['revenue_growth'])}", f"שולי רווח {fmt_pct(r['profit_margin']).lstrip('+')}",
                "עניין גבוה של משקיעים"],
        "risks": ["תמחור גבוה", "תנודתיות חדה"],
        "caption": f"{name} ({d['ticker']}) במרכז תשומת הלב השבוע. מכפילים, דוחות ולמה כולם מדברים עליה.\n{DISCLAIMER}",
        "hashtags": ["מניות", "שוקההון", "השקעות", "בורסה", "stocks", "investing", d["ticker"].lower(), "וולסטריט"],
    }


REC_HE = {"strong_buy": "קנייה חזקה", "buy": "קנייה", "hold": "החזקה", "underperform": "תשואת חסר",
          "sell": "מכירה", "strong_sell": "מכירה חזקה"}


def speak(text):
    """On-screen numbers to something the Hebrew voice reads well."""
    return (text.replace("P/E", "מכפיל רווח").replace("+", "").replace("%", " אחוז")
            .replace("$", "").replace("  ", " "))


def upside(d):
    a, price = d.get("analysts") or {}, d.get("price")
    return (a["target_mean"] / price - 1) * 100 if a.get("target_mean") and price else None


def pros_cons(d):
    """Bottom line from the numbers only, so every point can be checked on the earlier slides."""
    r, le = d["ratios"], d.get("last_earnings") or {}
    up, ch6, ch5 = upside(d), d.get("change_6m_pct"), d.get("change_5d_pct")
    pros, cons = [], []
    g, m, pe, de, sp = r.get("revenue_growth"), r.get("profit_margin"), r.get("pe"), r.get("debt_to_equity"), le.get("surprise_pct")
    if g is not None:
        (pros if g >= 0.08 else cons if g < 0 else []).append(f"{'צמיחה' if g >= 0 else 'ירידה'} בהכנסות {fmt_pct(g)}")
    if m is not None:
        if m >= 0.15:
            pros.append(f"שולי רווח נקי {fmt_pct(m).lstrip('+')}")
        elif m < 0:
            cons.append("החברה עדיין מפסידה")
    if sp is not None:
        (pros if sp >= 0 else cons).append(f"{'הכתה' if sp >= 0 else 'פספוס'} של צפי הרווח: {sp:+.1f}%")
    if up is not None:
        (pros if up >= 10 else cons if up < 0 else []).append(f"יעד האנליסטים {up:+.0f}% מהמחיר")
    if pe is not None and pe >= 40:
        cons.append(f"תמחור גבוה: מכפיל רווח {pe:.0f}")
    if de is not None and de > 150:
        cons.append(f"חוב גבוה: פי {de / 100:.1f} מההון")
    if ch5 is not None and abs(ch5) >= 8:
        cons.append(f"תנודתיות: {ch5:+.1f}% בשבוע")
    if ch6 is not None and ch6 <= -15:
        cons.append(f"מגמה יורדת: {ch6:+.0f}% בחצי שנה")
    if not cons:
        cons.append("סיכון שוק: זזה עם המדדים")
    return pros[:3], cons[:3]


def build_script(d, episode=1, kicker=None):
    s = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            s = _llm_script(d)
        except Exception as e:  # fall back rather than skip the day's post
            print(f"[script] Claude failed, using template: {e}")
    s = s or _template_script(d)
    n = s["narration"]
    name = d["name"]
    slides = [
        {"kind": "hook", "title": s["hook"], "narration": n["hook"], "head": {"kicker": kicker} if kicker else {}},
        {"kind": "chart", "title": "6 חודשים אחרונים", "narration": speak(n["chart"])},
    ]
    news = d.get("news") or []
    if news:
        pubs = list(dict.fromkeys(x["publisher"] for x in news))
        slides.append({"kind": "news", "title": "מה מזיז את המניה", "news": news,
                       "narration": (f"מה מזיז את המניה? לפי {news[0]['publisher']}: {news[0]['title_he'].rstrip('.')}. "
                                     "ועל המסך עוד כותרות, כל אחת עם המקור והתאריך."
                                     if news[0].get("title_he") else
                                     f"מה מזיז את המניה? אלה הכותרות האחרונות, מ-{' ו-'.join(pubs[:2])}. "
                                     "שימו לב לתאריך של כל כותרת.")})
    slides += [
        {"kind": "earnings", "title": "דוחות אחרונים", "header": ("רבעון", "הכנסות", "EPS"),
         "rows": earnings_rows(d), "narration": n["earnings"]},
        {"kind": "table", "title": "יחסים פיננסיים", "rows": ratio_rows(d), "narration": n["ratios"]},
    ]
    a, up = d.get("analysts") or {}, upside(d)
    if a.get("count") and up is not None:
        slides.append({"kind": "analysts", "title": "מה אומרת וול סטריט", "analysts": a,
                       "narration": f"{a['count']} אנליסטים מכסים את {name}"
                                    + (f", והקונצנזוס הוא {REC_HE[a['key']]}" if a.get("key") in REC_HE else "")
                                    + f". מחיר היעד הממוצע {a['target_mean']:.0f} דולר, {abs(up):.0f} אחוז "
                                    + ("מעל ל" if up >= 0 else "מתחת ל") + "מחיר הנוכחי. וזכרו, גם אנליסטים טועים."})
    pros, cons = pros_cons(d)
    slides.append({"kind": "proscons", "title": "בשורה התחתונה", "pros": pros, "cons": cons,
                   "narration": speak(("בשורה התחתונה. בעד: " + ", ".join(pros) + ". " if pros else "בשורה התחתונה. ")
                                      + "נגד: " + ", ".join(cons) + ".")})
    slides.append({"kind": "outro", "title": f"מחר 08:00 · פרק {episode + 1}",
                   "narration": f"זה היה פרק {episode} של המניה החמה. מחר בשמונה, פרק {episode + 1}. "
                                "שלחו לחבר שמשקיע, ועקבו כדי לא לפספס. זה לא ייעוץ השקעות."})
    slides = [sl for sl in slides if sl["kind"] not in ("table", "earnings") or sl["rows"]]
    move = d.get("change_5d_pct") or 0
    caption = (f"{name} ({d['ticker']}) {'עלתה' if move >= 0 else 'ירדה'} {abs(move):.1f}% השבוע. "
               "מה מזיז את המניה, הדוחות, המכפילים" + (f", מה אומרים {a['count']} אנליסטים" if a.get("count") else "")
               + " ובעד ונגד במספרים.\n"
               + f"המניה החמה · פרק {episode} · כל בוקר ב-08:00\n"
               + f"הנתונים: Yahoo Finance, נכון ל-{d.get('asof', '')}. {DISCLAIMER}\n\n"
               + f"#{d['ticker']} #מניות #שוקההון #וולסטריט #השקעות")
    return {"slides": slides, "caption": caption}
