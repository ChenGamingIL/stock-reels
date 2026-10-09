"""Evergreen Story sets for the profile Highlights, plus a round cover for each.

Instagram's API can post Stories but can't create Highlights, so the sets are posted
as Stories once and pinned to Highlights in the app; the covers are uploaded there.
Each point is (heading, text) or (heading, text, visual), like lessons.py.
"""
from PIL import Image, ImageDraw

from . import render as R

HIGHLIGHTS = [
    ("basics", "מתחילים", "BASICS", [
        ("שוק ההון", "המקום שבו חברות ומדינות מגייסות כסף מהציבור, ומשקיעים קונים ומוכרים ניירות ערך."),
        ("מניה", "חלק קטן מהבעלות על חברה. קניתם מניה של אפל? אתם שותפים קטנים באפל."),
        ("איך מרוויחים", "מעליית מחיר המניה, ומדיבידנד: חלק מהרווח שהחברה מחלקת לבעלי המניות."),
        ("בורסה", "השוק המסודר שבו המסחר קורה. בארה\"ב NYSE ונאסד\"ק, פתוחות בדרך כלל 16:30 עד 23:00 שעון ישראל."),
    ]),
    ("bonds", "אג\"ח", "BONDS", [
        ("מה זה אג\"ח", "אגרת חוב היא הלוואה שאתם נותנים למדינה או לחברה. מקבלים ריבית, ובסוף את הכסף בחזרה.", "bond"),
        ("ממשלתי או קונצרני", "אג\"ח ממשלתי נחשב בטוח יותר. אג\"ח של חברה משלם יותר, כי הסיכון שלא תחזיר גבוה יותר."),
        ("דירוג", "חברות דירוג בודקות את הסיכוי להחזר. AAA הכי בטוח, ומתחת ל-BBB נחשב אג\"ח זבל."),
        ("ריבית ומחיר", "כשהריבית במשק עולה, מחירי האג\"ח הקיימות יורדים. כשהיא יורדת, הם עולים."),
    ]),
    ("indices", "מדדים", "INDEX", [
        ("מדד", "סל של מניות שמודד איך חלק מהשוק מתנהג. כמו מדחום לשוק.", "index"),
        ("המדדים הגדולים", "S&P 500: 500 הגדולות בארה\"ב. נאסד\"ק 100: טכנולוגיה. ת\"א 35: הגדולות בישראל."),
        ("קרן מחקה", "קונים את כל המדד בפעולה אחת, דרך קרן מחקה או תעודת סל. פיזור רחב ודמי ניהול נמוכים."),
    ]),
    ("technical", "ניתוח טכני", "CHARTS", [
        ("נר יפני", "כל נר הוא יום מסחר. הגוף בין הפתיחה לסגירה, הפתילים הם הגבוה והנמוך.", "candle"),
        ("מגמה", "שיאים ושפלים עולים זו מגמה עולה. שיאים ושפלים יורדים זו מגמה יורדת.", "trend"),
        ("תמיכה והתנגדות", "תמיכה היא רצפה שבה קונים נכנסו בעבר. התנגדות היא תקרה שבה מוכרים עצרו עליות.", "levels"),
        ("ווליום", "כמה מניות החליפו ידיים. תנועה עם ווליום גבוה חזקה יותר.", "volume"),
    ]),
    ("reports", "דוחות", "REPORTS", [
        ("מכפיל רווח P/E", "מחיר המניה חלקי הרווח למניה: כמה משלמים על כל דולר רווח.", "pe"),
        ("EPS ודוחות", "חברות מפרסמות דוח כל רבעון. השוק משווה את הרווח למניה לצפי של האנליסטים."),
        ("דיבידנד", "חלוקת רווח לבעלי המניות. תשואת דיבידנד של 3% היא 3 דולר בשנה על כל 100 דולר."),
    ]),
    ("risk", "סיכונים", "RISK", [
        ("כלל ה-1%", "לא מסכנים בעסקה אחת יותר מ-1% עד 2% מהתיק."),
        ("סטופ", "מחליטים מראש איפה יוצאים בהפסד. בלי סטופ אין תוכנית."),
        ("פיזור", "לא שמים את כל הכסף על מניה אחת או סקטור אחד."),
    ]),
    ("schedule", "הלו\"ז", "DAILY", [
        ("כל יום אצלנו", "08:00 מניה חמה. 15:30 סקירה לפני הפתיחה בוול סטריט וסטאפ סווינג. 20:00 שיעור בסיס."),
    ]),
]


def script(key):
    _, name, badge, points = next(h for h in HIGHLIGHTS if h[0] == key)
    slides = [{"kind": "intro", "title": name, "lines": ["שוק ההון בקטנה", "לחצו להמשך"], "narration": name}]
    for p in points:
        slides.append({"kind": "lesson", "title": p[0], "text": p[1], "visual": p[2] if len(p) > 2 else None,
                       "narration": f"{p[0]}. {p[1]}"})
    return {"badge": badge, "slides": slides}


def render_set(key, out_dir):
    """Render a set's slides to out_dir/slide_i.png (stills only, no narration)."""
    sc = script(key)
    d = {"ticker": sc["badge"], "market": []}
    paths = []
    for i, sl in enumerate(sc["slides"]):
        p = out_dir / f"slide_{i}.png"
        R.RENDERERS[sl["kind"]](d, sl).save(p)
        paths.append(p)
    return paths


def _icon(dr, key, cx, cy):
    g = R.ACCENT
    if key == "basics":
        for i, h in enumerate((90, 150, 210)):
            dr.rectangle([cx - 150 + i * 110, cy + 120 - h, cx - 70 + i * 110, cy + 120], fill=g)
    elif key == "bonds":
        dr.rounded_rectangle([cx - 150, cy - 180, cx + 150, cy + 180], 26, outline=g, width=14)
        dr.text((cx, cy + 10), "%", font=R.font(200), fill=g, anchor="mm")
    elif key == "indices":
        pts = [(cx - 190, cy + 110), (cx - 90, cy + 10), (cx - 10, cy + 60), (cx + 80, cy - 60), (cx + 190, cy - 130)]
        dr.line(pts, fill=g, width=22, joint="curve")
        dr.polygon([(cx + 200, cy - 180), (cx + 230, cy - 90), (cx + 140, cy - 110)], fill=g)
    elif key == "technical":
        for x, (top, bot, wt, wb, up) in zip((cx - 130, cx, cx + 130),
                                              ((40, 150, -10, 200, False), (-60, 80, -120, 130, True), (-150, -20, -200, 30, True))):
            dr.line([(x, cy + wt), (x, cy + wb)], fill=g, width=10)
            dr.rectangle([x - 40, cy + top, x + 40, cy + bot], fill=g if up else (0, 0, 0), outline=g, width=10)
    elif key == "reports":
        dr.rounded_rectangle([cx - 140, cy - 190, cx + 140, cy + 190], 22, outline=g, width=14)
        for i in range(4):
            dr.line([(cx - 90, cy - 100 + i * 70), (cx + (90 if i < 3 else 20), cy - 100 + i * 70)], fill=g, width=14)
    elif key == "risk":
        dr.polygon([(cx, cy - 200), (cx + 170, cy - 130), (cx + 150, cy + 60), (cx, cy + 200),
                    (cx - 150, cy + 60), (cx - 170, cy - 130)], outline=g, width=14)
        dr.line([(cx - 70, cy), (cx - 15, cy + 60), (cx + 85, cy - 60)], fill=g, width=20, joint="curve")
    elif key == "schedule":
        dr.ellipse([cx - 190, cy - 190, cx + 190, cy + 190], outline=g, width=14)
        dr.line([(cx, cy), (cx, cy - 120)], fill=g, width=16)
        dr.line([(cx, cy), (cx + 90, cy + 40)], fill=g, width=16)


def cover(key, path):
    """1080x1920 cover: icon centred, so Instagram's round crop shows it whole."""
    img = Image.new("RGB", (R.W, R.H), (8, 7, 5))
    dr = ImageDraw.Draw(img)
    cx, cy = R.W // 2, R.H // 2
    dr.ellipse([cx - 420, cy - 420, cx + 420, cy + 420], fill=(20, 16, 9), outline=R.GOLD_DARK, width=10)
    _icon(dr, key, cx, cy)
    img.save(path)
