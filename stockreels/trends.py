"""רז, the team's X scout: what traders on X talk about this week, read with Grok's x_search (xAI API).

  python -m stockreels.trends            -> trends.json and trends.md, and the summary in the job log
  python -m stockreels.trends --release  -> the same, attached to a trends-<date> release
  python -m stockreels.trends --selftest -> parses a canned answer, calls nothing (the workflow's push check)

The content bot runs it (trends.yml) before choosing a topic. It needs the XAI_API_KEY secret, from Chen's
own xAI account, which is paid by use: $5 per 1,000 posts the search reads, plus tokens (docs.x.ai pricing,
October 2026). Without the key the run says so and spends nothing. Each run is one request over a short
window, and the prompt asks for a few searches only, so a run costs cents.
"""
import datetime as dt
import json
import os
import re
import sys

import requests

URL = "https://api.x.ai/v1/responses"
MODEL = os.environ.get("XAI_MODEL") or "grok-4.7"
DAYS = 4

PROMPT = """You are a research scout for @stocksisx, a Hebrew Instagram account that explains the US stock market \
to Israeli beginners and long-term investors. It is educational only and never gives advice.
Search X for what retail investors and finance accounts discussed most from {since} to {until}: US stocks, \
indexes, ETFs and market themes. Also look at what Hebrew-speaking (Israeli) finance accounts on X talk about. \
Use at most 3 searches.
Return ONLY a JSON object, no prose and no code fence, in this shape:
{{"window": "{since}..{until}",
  "topics": [{{"topic": "short English name", "tickers": ["NVDA"],
              "why": "one sentence: what happened and why people care",
              "mood": "bullish|bearish|mixed",
              "evidence": ["links to posts you actually read"],
              "angle_he": "one Hebrew sentence: an evergreen, educational angle for beginners, no advice"}}],
  "hebrew_x": "one or two Hebrew sentences on what Israeli finance X talks about, or an empty string",
  "avoid": ["rumors, pumps or claims you could not verify, so the account stays away from them"]}}
5 to 8 topics, the most discussed first. Only include what you saw in posts: no invented tickers, numbers or links."""


def scout(key, today=None):
    today = today or dt.date.today()
    since = today - dt.timedelta(days=DAYS)
    body = {"model": MODEL,
            "input": [{"role": "user", "content": PROMPT.format(since=since, until=today)}],
            "tools": [{"type": "x_search", "from_date": since.isoformat(), "to_date": today.isoformat()}],
            "max_turns": 2}  # caps the assistant turns, and with them the searches and the posts they read
    r = requests.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=300)
    if not r.ok:
        sys.exit(f"[trends] xAI answered {r.status_code}: {r.text[:400]}")
    return r.json()


def text_of(resp):
    """The answer's text, from a Responses-style body: output_text, or the message items in output."""
    if isinstance(resp.get("output_text"), str) and resp["output_text"].strip():
        return resp["output_text"]
    parts = []
    for item in resp.get("output") or []:
        content = item.get("content") if isinstance(item, dict) else None
        for c in content if isinstance(content, list) else []:
            if isinstance(c, dict) and c.get("type") in ("output_text", "text") and c.get("text"):
                parts.append(c["text"])
    return "\n".join(parts)


def parse(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON in Grok's answer: {text[:300]!r}")
    data = json.loads(m.group(0))
    data["topics"] = [t for t in data.get("topics") or [] if isinstance(t, dict) and t.get("topic")]
    return data


def summary(data):
    lines = [f"# רז · מה מדברים עליו ב-X ({data.get('window', '')})"]
    for i, t in enumerate(data["topics"], 1):
        tickers = " ".join("$" + x for x in t.get("tickers") or [])
        lines.append(f"{i}. {t['topic']} {tickers} [{t.get('mood', '')}]: {t.get('why', '')}")
        if t.get("angle_he"):
            lines.append(f"   זווית: {t['angle_he']}")
    if data.get("hebrew_x"):
        lines.append(f"X בעברית: {data['hebrew_x']}")
    if data.get("avoid"):
        lines.append("להתרחק: " + "; ".join(map(str, data["avoid"])))
    return "\n".join(lines)


SAMPLE = {"output": [
    {"type": "x_search_call", "status": "completed"},
    {"type": "message", "content": [{"type": "output_text", "text": "Here you go:\n" + json.dumps({
        "window": "2026-11-12..2026-11-16",
        "topics": [{"topic": "Nvidia earnings week", "tickers": ["NVDA"], "why": "Results are due and options price a big move.",
                    "mood": "mixed", "evidence": ["https://x.com/i/status/1"],
                    "angle_he": "מה זה דוח רבעוני ולמה המניה זזה גם כשהתוצאות טובות"},
                   {"tickers": ["XYZ"]}],
        "hebrew_x": "בטוויטר הישראלי מדברים על מס רווחי הון",
        "avoid": ["a rumored buyout nobody sourced"]}, ensure_ascii=False)}]}]}


def selftest():
    data = parse(text_of(SAMPLE))
    assert [t["topic"] for t in data["topics"]] == ["Nvidia earnings week"], data["topics"]
    md = summary(data)
    for want in ("$NVDA", "[mixed]", "זווית:", "X בעברית:", "להתרחק:"):
        assert want in md, (want, md)
    assert text_of({"output_text": "{}"}) == "{}"
    print(md)
    print("[trends] self-test passed. No xAI call was made.")


def main():
    if "--selftest" in sys.argv:
        return selftest()
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        print("[trends] no XAI_API_KEY secret yet: רז waits for Chen's xAI key. Nothing was spent.")
        return
    resp = scout(key)
    usage = resp.get("usage") or {}
    tools = usage.get("server_side_tool_usage_details") or {}
    print(f"[trends] x_search calls {tools.get('x_search_calls')}, posts read {tools.get('x_posts_fetched')}, "
          f"tokens {usage.get('input_tokens')}+{usage.get('output_tokens')}, cost ticks {usage.get('cost_in_usd_ticks')}")
    data = parse(text_of(resp))
    data.update(generated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), model=MODEL)
    with open("trends.json", "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    md = summary(data)
    with open("trends.md", "w") as f:
        f.write(md + "\n")
    print(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(md + "\n")
    if "--release" in sys.argv:
        from . import instagram
        rid = instagram._create_release(f"trends-{dt.datetime.now():%Y%m%d-%H%M}")
        for name, kind in [("trends.json", "application/json"), ("trends.md", "text/markdown")]:
            print("[trends]", instagram._upload_asset(rid, name, name, kind))


if __name__ == "__main__":
    main()
