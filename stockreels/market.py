"""Data for the pre-market show: market overview, pre-market movers, earnings this week, a swing setup."""
import datetime as dt

from .data import WATCHLIST

# (Hebrew label, Yahoo symbol, decimals)
OVERVIEW = [
    ("חוזה S&P 500", "ES=F", 0), ("חוזה נאסד\"ק", "NQ=F", 0), ("חוזה דאו", "YM=F", 0),
    ("VIX פחד", "^VIX", 2), ("נפט", "CL=F", 2), ("זהב", "GC=F", 0),
    ("ביטקוין", "BTC-USD", 0), ("תשואה 10 שנים", "^TNX", 2), ("דולר/שקל", "ILS=X", 3),
    ("ת\"א 35", "TA35.TA", 0),
]


def overview():
    """Last price and change vs the previous daily close for futures, VIX, commodities, FX."""
    import yfinance as yf

    closes = yf.download([s for _, s, _ in OVERVIEW], period="7d", interval="1d",
                         progress=False, auto_adjust=True)["Close"]
    out = []
    for label, sym, dec in OVERVIEW:
        try:
            c = closes[sym].dropna()
            if len(c) >= 2:
                out.append({"label": label, "symbol": sym, "price": round(float(c.iloc[-1]), dec),
                            "decimals": dec, "pct": round(float((c.iloc[-1] / c.iloc[-2] - 1) * 100), 2)})
        except Exception:
            pass
    return out


def premarket_movers(n=3):
    """Biggest pre-market moves in the watchlist vs yesterday's close.

    Falls back to yesterday's regular-session moves when there is no pre-market data.
    Returns (movers, is_premarket).
    """
    import yfinance as yf

    intraday = yf.download(WATCHLIST, period="5d", interval="15m", prepost=True,
                           progress=False, auto_adjust=True)["Close"]
    daily = yf.download(WATCHLIST, period="7d", interval="1d", progress=False, auto_adjust=True)["Close"]
    today = intraday.index[-1].date()
    moves, pre = {}, False
    for t in WATCHLIST:
        try:
            d = daily[t].dropna()
            prev = d[d.index.date < today].iloc[-1]
            last = intraday[t].dropna()
            last_today = last[last.index.date == today]
            if len(last_today):
                moves[t] = (float(last_today.iloc[-1]) / float(prev) - 1) * 100
                pre = True
            else:
                moves[t] = (float(d.iloc[-1]) / float(d.iloc[-2]) - 1) * 100
        except Exception:
            pass
    ranked = sorted(moves.items(), key=lambda kv: kv[1])
    losers = [(t, round(p, 2)) for t, p in ranked[:n] if p < 0]
    gainers = [(t, round(p, 2)) for t, p in ranked[::-1][:n] if p > 0]
    return {"gainers": gainers, "losers": losers}, pre


def earnings_this_week():
    """Watchlist companies reporting in the next 7 days, as [(ticker, 'YYYY-MM-DD')]."""
    import yfinance as yf

    today, out = dt.date.today(), []
    for t in WATCHLIST:
        try:
            cal = yf.Ticker(t).calendar or {}
            dates = cal.get("Earnings Date") or []
            for d in dates[:1]:
                if today <= d <= today + dt.timedelta(days=7):
                    out.append((t, d.isoformat()))
        except Exception:
            pass
    return sorted(out, key=lambda x: x[1])[:5]


def _rsi(close, n=14):
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / down)


def _atr(df, n=14):
    import pandas as pd

    prev = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def swing_setup(exclude=()):
    """Scan the watchlist for one textbook swing setup and compute its levels.

    Two patterns, both only in an uptrend (close > SMA50 > SMA200):
      pullback: price back near the rising SMA20 with RSI cooled to 40-55
      breakout: close above the prior 20-day high on above-average volume
    Levels: trigger above the last high, stop 1.5 ATR below (or under the recent low),
    target at 2x the risk. Educational example only.
    """
    import yfinance as yf

    best = None
    for t in WATCHLIST:
        if t in exclude:
            continue
        try:
            df = yf.Ticker(t).history(period="1y", interval="1d").dropna()
            if len(df) < 210:
                continue
            c = df["Close"]
            sma20, sma50, sma200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
            rsi, atr = _rsi(c), _atr(df)
            last, s20, s50, s200, r, a = (float(x.iloc[-1]) for x in (c, sma20, sma50, sma200, rsi, atr))
            if not (last > s50 > s200 and sma20.iloc[-1] > sma20.iloc[-6]):
                continue
            prior_high = float(df["High"].iloc[-21:-1].max())
            vol_ratio = float(df["Volume"].iloc[-1] / df["Volume"].iloc[-21:-1].mean())
            kind, score = None, 0
            if last > prior_high and vol_ratio > 1.3:
                kind, score = "breakout", vol_ratio
            elif abs(last / s20 - 1) < 0.025 and 40 <= r <= 55:
                kind, score = "pullback", 1 / (abs(last / s20 - 1) + 0.005)
            if kind and (best is None or score > best["score"]):
                trigger = round(float(df["High"].iloc[-1]) * 1.002, 2)
                stop = round(min(trigger - 1.5 * a, float(df["Low"].iloc[-5:].min())), 2)
                target = round(trigger + 2 * (trigger - stop), 2)
                tail = df.iloc[-60:]
                best = {
                    "ticker": t, "kind": kind, "score": score, "price": round(last, 2),
                    "rsi": round(r, 1), "sma20": round(s20, 2), "sma50": round(s50, 2),
                    "vol_ratio": round(vol_ratio, 2), "breakout_level": round(prior_high, 2),
                    "trigger": trigger, "stop": stop, "target": target,
                    "risk_pct": round((trigger - stop) / trigger * 100, 1),
                    "candles": [[round(float(x.Open), 2), round(float(x.High), 2), round(float(x.Low), 2),
                                 round(float(x.Close), 2), float(x.Volume)] for x in tail.itertuples()],
                    "sma20_series": [round(float(x), 2) for x in sma20.iloc[-60:]],
                    "sma50_series": [round(float(x), 2) for x in sma50.iloc[-60:]],
                }
        except Exception as e:
            print(f"[swing] {t}: {e.__class__.__name__}")
    return best


def fetch_premarket(exclude=()):
    movers, is_pre = premarket_movers()
    return {
        "date": dt.date.today().isoformat(),
        "overview": overview(),
        "movers": movers,
        "movers_premarket": is_pre,
        "earnings": earnings_this_week(),
        "setup": swing_setup(exclude),
    }


# --- live session: market-open snapshot (16:45 Israel) and end-of-day wrap (23:15 Israel) ---

INDICES_LIVE = [("S&P 500", "^GSPC", 0), ("נאסד\"ק", "^IXIC", 0), ("דאו ג'ונס", "^DJI", 0),
                ("ראסל 2000", "^RUT", 0), ("VIX פחד", "^VIX", 2), ("תשואה 10 שנים", "^TNX", 2)]
SECTORS = [("טכנולוגיה", "XLK"), ("פיננסים", "XLF"), ("אנרגיה", "XLE"), ("בריאות", "XLV"),
           ("צריכה מחזורית", "XLY"), ("תעשייה", "XLI"), ("תקשורת", "XLC"), ("צריכה בסיסית", "XLP"),
           ("תשתיות", "XLU"), ("נדל\"ן", "XLRE"), ("חומרים", "XLB")]


def _session_changes(symbols):
    """{symbol: (last, pct vs previous close)} for today's US session, or {} if the market didn't trade today."""
    import yfinance as yf
    from zoneinfo import ZoneInfo

    intraday = yf.download(symbols, period="5d", interval="5m", progress=False, auto_adjust=True)["Close"]
    daily = yf.download(symbols, period="10d", interval="1d", progress=False, auto_adjust=True)["Close"]
    ny_today = dt.datetime.now(ZoneInfo("America/New_York")).date()
    idx = intraday.index.tz_convert("America/New_York")
    out = {}
    for s in symbols:
        try:
            col = intraday[s]
            today = col[idx.date == ny_today].dropna()
            if not len(today):
                continue
            d = daily[s].dropna()
            prev = d[d.index.date < ny_today].iloc[-1]
            out[s] = (float(today.iloc[-1]), (float(today.iloc[-1]) / float(prev) - 1) * 100)
        except Exception:
            pass
    return out


def fetch_session(kind):
    """Data for the 'open' snapshot or the 'close' wrap. Returns None when the US market is closed today."""
    syms = [s for _, s, _ in INDICES_LIVE] + list(WATCHLIST) + ([s for _, s in SECTORS] if kind == "close" else [])
    ch = _session_changes(syms)
    if "^GSPC" not in ch:
        return None
    tiles = [{"label": l, "symbol": s, "price": round(ch[s][0], d), "decimals": d, "pct": round(ch[s][1], 2)}
             for l, s, d in INDICES_LIVE if s in ch]
    moves = sorted(((t, round(ch[t][1], 2)) for t in WATCHLIST if t in ch), key=lambda kv: kv[1])
    data = {"kind": kind, "date": dt.date.today().isoformat(), "tiles": tiles,
            "movers": {"gainers": [m for m in moves[::-1][:3] if m[1] > 0],
                       "losers": [m for m in moves[:3] if m[1] < 0]}}
    if kind == "close":
        data["sectors"] = sorted(([n, round(ch[s][1], 2)] for n, s in SECTORS if s in ch),
                                 key=lambda x: -x[1])
    return data
