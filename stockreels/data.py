"""Pick a "hot" stock for today and collect the numbers the video talks about."""
import json
import random
from pathlib import Path

# Large, liquid US names. The day's pick is the biggest mover among these
# (plus Yahoo's most-active list when available), skipping recent repeats.
WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX",
    "PLTR", "CRM", "ORCL", "ADBE", "COST", "LLY", "JPM", "V", "MA", "UBER",
    "SHOP", "CRWD", "PANW", "SNOW", "MU", "SMCI", "ARM", "TSM", "ASML", "INTC",
]

HISTORY_FILE = Path(__file__).resolve().parent.parent / "history.json"
NO_REPEAT_DAYS = 14


def _load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []


def save_to_history(ticker, date_str):
    hist = _load_history()
    hist.append({"ticker": ticker, "date": date_str})
    HISTORY_FILE.write_text(json.dumps(hist[-200:], indent=2))


def _candidates():
    import yfinance as yf

    tickers = list(WATCHLIST)
    try:
        res = yf.screen("most_actives", count=25)
        for q in res.get("quotes", []):
            sym = q.get("symbol")
            if sym and q.get("marketCap", 0) > 10e9 and sym not in tickers:
                tickers.append(sym)
    except Exception:
        pass
    return tickers


def pick_hot_ticker():
    """Biggest absolute 5-day move among candidates, not used in the last NO_REPEAT_DAYS picks."""
    import yfinance as yf

    recent = {h["ticker"] for h in _load_history()[-NO_REPEAT_DAYS:]}
    tickers = [t for t in _candidates() if t not in recent]
    data = yf.download(tickers, period="7d", interval="1d", progress=False, auto_adjust=True)["Close"]
    moves = {}
    for t in tickers:
        s = data[t].dropna() if t in data else None
        if s is not None and len(s) >= 2:
            moves[t] = abs(s.iloc[-1] / s.iloc[0] - 1)
    if not moves:
        return random.choice(tickers)
    return max(moves, key=moves.get)


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def fetch_stock(ticker):
    """Return a plain dict with price history, valuation ratios and recent earnings."""
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = t.info
    daily = t.history(period="6mo", interval="1d").dropna(subset=["Close"])
    hist = daily["Close"]
    weekly = daily.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min",
                                          "Close": "last", "Volume": "sum"}).dropna()

    earnings = []
    try:
        q = t.quarterly_income_stmt
        for col in list(q.columns)[:4][::-1]:
            earnings.append({
                "quarter": col.strftime("%Y-%m"),
                "revenue": _num(q.at["Total Revenue", col]) if "Total Revenue" in q.index else None,
                "net_income": _num(q.at["Net Income", col]) if "Net Income" in q.index else None,
                "eps": _num(q.at["Diluted EPS", col]) if "Diluted EPS" in q.index else None,
            })
    except Exception:
        pass

    surprise = None
    try:
        ed = t.get_earnings_dates(limit=8)
        past = ed[ed["Reported EPS"].notna()]
        if len(past):
            row = past.iloc[0]
            surprise = {
                "date": past.index[0].strftime("%Y-%m-%d"),
                "eps_estimate": _num(row.get("EPS Estimate")),
                "eps_reported": _num(row.get("Reported EPS")),
                "surprise_pct": _num(row.get("Surprise(%)")),
            }
    except Exception:
        pass

    return {
        "ticker": ticker,
        "name": short_name(info.get("shortName") or ticker),
        "sector": info.get("sector"),
        "currency": info.get("currency", "USD"),
        "price": _num(info.get("currentPrice") or (hist.iloc[-1] if len(hist) else None)),
        "change_5d_pct": _num((hist.iloc[-1] / hist.iloc[-6] - 1) * 100) if len(hist) > 6 else None,
        "change_6m_pct": _num((hist.iloc[-1] / hist.iloc[0] - 1) * 100) if len(hist) > 1 else None,
        "market_cap": _num(info.get("marketCap")),
        "ratios": {
            "pe": _num(info.get("trailingPE")),
            "forward_pe": _num(info.get("forwardPE")),
            "peg": _num(info.get("trailingPegRatio") or info.get("pegRatio")),
            "ps": _num(info.get("priceToSalesTrailing12Months")),
            "gross_margin": _num(info.get("grossMargins")),
            "profit_margin": _num(info.get("profitMargins")),
            "revenue_growth": _num(info.get("revenueGrowth")),
            "debt_to_equity": _num(info.get("debtToEquity")),
        },
        "analyst_target": _num(info.get("targetMeanPrice")),
        "recommendation": info.get("recommendationKey"),
        "analysts": {
            "count": int(info.get("numberOfAnalystOpinions") or 0),
            "mean": _num(info.get("recommendationMean")),  # 1 strong buy .. 5 sell
            "key": info.get("recommendationKey"),
            "target_mean": _num(info.get("targetMeanPrice")),
            "target_high": _num(info.get("targetHighPrice")),
            "target_low": _num(info.get("targetLowPrice")),
        },
        "news": with_hebrew(fetch_news(t)),
        "asof": asof(),
        "earnings": earnings,
        "last_earnings": surprise,
        "history": [round(float(x), 2) for x in hist.tolist()],
        # weekly candles for the chart: [open, high, low, close, volume]
        "candles": [[round(float(r.Open), 2), round(float(r.High), 2), round(float(r.Low), 2),
                     round(float(r.Close), 2), float(r.Volume)] for r in weekly.itertuples()],
        "market": fetch_market(),
    }


def short_name(name):
    """'Super Micro Computer, Inc.' -> 'Super Micro Computer', for narration and titles."""
    import re

    return re.sub(r"[,\s]+(Inc\.?|Corporation|Corp\.?|Holdings?|Ltd\.?|plc|N\.V\.|S\.A\.|Co\.|Company|Class [A-C])$", "",
                  name.strip(), flags=re.I).strip() or name


def asof():
    """Data timestamp shown on every slide, Israel time."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    return dt.datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d.%m.%y %H:%M")


def fetch_news(t, n=3, max_age_days=10):
    """Latest headlines as [{title, publisher, date}], newest first. Handles both yfinance news shapes."""
    import datetime as dt

    out = []
    try:
        items = t.news or []
    except Exception as e:
        print(f"[data] news unavailable: {e.__class__.__name__}")
        items = []
    print(f"[news] yahoo returned {len(items)} items")
    now = dt.datetime.now(dt.timezone.utc)
    if items:
        c0 = items[0].get("content") or items[0]
        print(f"[news] {len(items)} items, first: {sorted(c0)[:14]} type={c0.get('contentType')} date={c0.get('pubDate')}")
    for it in items:
        c = it.get("content") or it
        title = c.get("title")
        pub = (c.get("provider") or {}).get("displayName") or c.get("publisher")
        when = c.get("pubDate") or c.get("displayTime")
        try:
            when = (dt.datetime.fromisoformat(when.replace("Z", "+00:00")) if isinstance(when, str)
                    else dt.datetime.fromtimestamp(it["providerPublishTime"], dt.timezone.utc))
        except Exception:
            continue
        if not title or not pub or (now - when).days > max_age_days:
            continue
        if (c.get("contentType") or "STORY").upper() not in ("STORY", "ARTICLE"):
            continue
        out.append({"title": title.strip(), "publisher": pub.strip(), "date": when.strftime("%d.%m")})
        if len(out) == n:
            break
    return out or google_news(t.ticker, n, max_age_days)


def translate_he(texts):
    """English headlines to Hebrew with Google Translate's public endpoint; None for any that fail."""
    import requests

    out = []
    for t in texts:
        try:
            r = requests.get("https://translate.googleapis.com/translate_a/single",
                             params={"client": "gtx", "sl": "en", "tl": "iw", "dt": "t", "q": t}, timeout=15)
            r.raise_for_status()
            he = "".join(seg[0] for seg in r.json()[0] if seg and seg[0]).strip()
            out.append(he or None)
        except Exception as e:
            print(f"[news] translate failed: {e.__class__.__name__}")
            out.append(None)
    return out


def with_hebrew(news):
    for item, he in zip(news, translate_he([x["title"] for x in news])):
        if he:
            item["title_he"] = he
    return news


def google_news(ticker, n=3, max_age_days=10, query=None):
    """Fallback headlines from Google News RSS, which names the publisher of every item."""
    import datetime as dt
    import email.utils
    import xml.etree.ElementTree as ET

    import requests

    try:
        r = requests.get("https://news.google.com/rss/search",
                         params={"q": f"{query or ticker + ' stock'} when:{max_age_days}d", "hl": "en-US", "gl": "US", "ceid": "US:en"},
                         timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        items = ET.fromstring(r.content).findall("./channel/item")
    except Exception as e:
        print(f"[news] google unavailable: {e.__class__.__name__}")
        return []
    out = []
    for it in items:
        pub = (it.findtext("source") or "").strip()
        title = (it.findtext("title") or "").strip()
        if pub and title.endswith(" - " + pub):
            title = title[: -len(pub) - 3].strip()
        try:
            when = email.utils.parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:
            continue
        if not pub or not title:
            continue
        out.append({"title": title, "publisher": pub, "date": when.strftime("%d.%m"), "ts": when.timestamp()})
    print(f"[news] google returned {len(items)} items")
    top = sorted(out[:n], key=lambda x: -x["ts"])  # most relevant few, newest first
    return [{k: v for k, v in x.items() if k != "ts"} for x in top]


def market_headlines(n=3):
    """Today's top Wall Street headlines, translated to Hebrew."""
    return with_hebrew(google_news(None, n=n, max_age_days=1, query="Wall Street stocks today"))


INDICES = [("S&P 500", "^GSPC"), ("NASDAQ", "^IXIC"), ("DOW", "^DJI"), ("VIX", "^VIX")]


def fetch_market():
    """Last daily % change of the main indices, for the ticker tape on every slide."""
    import yfinance as yf

    try:
        closes = yf.download([s for _, s in INDICES], period="5d", interval="1d",
                             progress=False, auto_adjust=True)["Close"]
        out = []
        for name, sym in INDICES:
            c = closes[sym].dropna()
            if len(c) >= 2:
                out.append([name, round(float(c.iloc[-1]), 2), round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2)])
        return out
    except Exception as e:
        print(f"[data] market tape unavailable: {e}")
        return []
