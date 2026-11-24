"""Today's weather from the Japan Meteorological Agency's public
forecast JSON — the same source chibi_bot used (its weather was this
API, not RSS; the RSS feeds were the topic source we dropped).

One fetch per day, no key, short timeout. Any failure returns None
and the caller falls back to a neutral line: the morning duty never
blocks on the weather.
"""

import json
import urllib.request

URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/{code}.json"


def _classify(raw: str) -> bool:
    return any(kw in raw for kw in ("雨", "雪", "雷"))


def parse_forecast(data: list, area_name_hint: str = "") -> dict | None:
    """JMA forecast JSON -> {area, raw, rainy, pop}. Index 0 of the
    first timeSeries is today's weather text for the first area."""
    try:
        series = data[0]["timeSeries"]
        area0 = series[0]["areas"][0]
        raw = " ".join(area0["weathers"][0].split()).replace("　", " ")
        pop = ""
        for s in series:
            if "pops" in s.get("areas", [{}])[0]:
                pops = [p for p in s["areas"][0]["pops"] if p != ""]
                if pops:
                    pop = max(pops, key=lambda p: int(p))
                break
        return {
            "area": area0["area"]["name"] or area_name_hint,
            "raw": raw,
            "rainy": _classify(raw),
            "pop": pop,
        }
    except Exception:
        return None


def fetch_today(area_code: str = "130000", opener=None) -> dict | None:
    try:
        req = urllib.request.Request(URL.format(code=area_code),
                                     headers={"User-Agent": "sweet-home/0.1"})
        open_fn = opener or (lambda r: urllib.request.urlopen(r, timeout=10))
        with open_fn(req) as res:
            data = json.loads(res.read().decode("utf-8"))
        return parse_forecast(data)
    except Exception:
        return None
