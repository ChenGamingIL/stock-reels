# Stock Reels — סרטון יומי על מניה חמה לאינסטגרם

כל יום ב-08:00 בבוקר האוטומציה:
1. בוחרת מניה חמה (התנועה הכי חדה ב-5 ימים מתוך רשימת מניות גדולות + המניות הכי סחירות ב-Yahoo, בלי חזרות ל-14 יום).
2. מושכת נתונים מ-Yahoo Finance: מחיר, גרף 6 חודשים, מכפילים (P/E, P/E עתידי, P/S, PEG, שולי רווח, צמיחה), 4 רבעונים אחרונים ותוצאות הדוח האחרון.
3. כותבת תסריט בעברית עם Claude (המספרים על המסך נלקחים ישירות מהנתונים, לא מהמודל).
4. מקריאה בעברית (edge-tts, קול he-IL-AvriNeural, חינמי).
5. מרנדרת רילס אנכי 1080x1920 עם 7 שקפים והסתייגות "לא ייעוץ השקעות" בכל שקף.
6. מעלה לאינסטגרם דרך Instagram Graph API.

## הרצה מקומית
```bash
pip install -r requirements.txt   # + ffmpeg מותקן
python run.py --sample            # תצוגה מקדימה עם נתוני דוגמה
python run.py --dry-run           # נתונים אמיתיים, בלי העלאה
python run.py --ticker NVDA       # מניה ספציפית + העלאה
```

## מה צריך להגדיר (Secrets ב-GitHub)
| שם | מה זה |
|---|---|
| `ANTHROPIC_API_KEY` | מפתח API של Claude (console.anthropic.com). בלי זה יש תסריט בסיסי מתבנית. |
| `IG_USER_ID` | המזהה של חשבון האינסטגרם המקצועי |
| `IG_ACCESS_TOKEN` | טוקן ארוך-טווח עם הרשאת `instagram_content_publish` |

### הכנת אינסטגרם
1. להפוך את החשבון לחשבון מקצועי (Business או Creator).
2. ב-developers.facebook.com ליצור אפליקציה ולהוסיף את המוצר "Instagram API with Instagram Login".
3. לחבר את חשבון האינסטגרם, לבקש הרשאות `instagram_business_basic` ו-`instagram_business_content_publish`, ולהפיק טוקן ארוך-טווח (60 יום, ניתן לחידוש).
4. אם משתמשים בדרך הישנה (דף פייסבוק מקושר), מוסיפים ב-Settings > Variables את `GRAPH_HOST=graph.facebook.com`.

## תזמון
`.github/workflows/daily-reel.yml` רץ כל יום ב-08:00 שעון ישראל (מטפל לבד במעבר שעון קיץ/חורף), ואפשר להריץ ידנית מלשונית Actions (עם בחירת מניה או dry run). הסרטון נשמר גם כ-artifact של הריצה.

> התוכן הוא לצורכי מידע בלבד ואינו ייעוץ השקעות.
