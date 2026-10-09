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
            "outro": "עקבו לעוד מניה חמה כל יום. וזכרו, זה לא ייעוץ השקעות.",
        },
        "why": [f"צמיחה בהכנסות {fmt_pct(r['revenue_growth'])}", f"שולי רווח {fmt_pct(r['profit_margin']).lstrip('+')}",
                "עניין גבוה של משקיעים"],
        "risks": ["תמחור גבוה", "תנודתיות חדה"],
        "caption": f"{name} ({d['ticker']}) במרכז תשומת הלב השבוע. מכפילים, דוחות ולמה כולם מדברים עליה.\n{DISCLAIMER}",
        "hashtags": ["מניות", "שוקההון", "השקעות", "בורסה", "stocks", "investing", d["ticker"].lower(), "וולסטריט"],
    }


def build_script(d):
    s = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            s = _llm_script(d)
        except Exception as e:  # fall back rather than skip the day's post
            print(f"[script] Claude failed, using template: {e}")
    s = s or _template_script(d)
    n = s["narration"]
    slides = [
        {"kind": "hook", "title": s["hook"], "narration": n["hook"]},
        {"kind": "chart", "title": "6 חודשים אחרונים", "narration": n["chart"]},
        {"kind": "table", "title": "יחסים פיננסיים", "rows": ratio_rows(d), "narration": n["ratios"]},
        {"kind": "table", "title": "דוחות אחרונים", "header": ("רבעון", "הכנסות", "EPS"),
         "rows": earnings_rows(d), "narration": n["earnings"]},
        {"kind": "bullets", "title": "למה היא מעניינת", "bullets": s["why"], "narration": n["why"]},
        {"kind": "bullets", "title": "סיכונים", "bullets": s["risks"], "narration": n["risks"], "accent": "red"},
        {"kind": "outro", "title": "עקבו למניה חמה כל יום", "narration": n["outro"]},
    ]
    slides = [sl for sl in slides if sl["kind"] != "table" or sl["rows"]]
    caption = s["caption"].strip()
    if "ייעוץ" not in caption:
        caption += "\n" + DISCLAIMER
    caption += "\n\n" + " ".join("#" + h.lstrip("#").replace(" ", "") for h in s["hashtags"])
    return {"slides": slides, "caption": caption}
