"""Weather sim: JMA forecast parsing + failure fallback, offline.

Run: python3 sim/simulate_weather.py
"""

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from weather import fetch_today, parse_forecast  # noqa: E402

SAMPLE = [{
    "timeSeries": [
        {"timeDefines": ["2026-11-24T05:00:00+09:00"],
         "areas": [{"area": {"name": "東京地方", "code": "130000"},
                    "weathers": ["晴れ　時々　くもり"]}]},
        {"timeDefines": ["2026-11-24T00:00:00+09:00"],
         "areas": [{"area": {"name": "東京地方", "code": "130000"},
                    "pops": ["0", "10", "20", "10"]}]},
    ],
}]
RAINY = [{
    "timeSeries": [
        {"areas": [{"area": {"name": "東京地方", "code": "130000"},
                    "weathers": ["雨　時々　くもり"]}]},
        {"areas": [{"area": {"name": "東京地方", "code": "130000"}, "pops": ["80"]}]},
    ],
}]


class FakeRes(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def opener_for(payload):
    return lambda req: FakeRes(json.dumps(payload).encode())


def main() -> None:
    w = parse_forecast(SAMPLE)
    assert w == {"area": "東京地方", "raw": "晴れ 時々 くもり", "rainy": False, "pop": "20"}, w
    w2 = fetch_today("130000", opener=opener_for(RAINY))
    assert w2["rainy"] is True and w2["pop"] == "80", w2
    assert fetch_today("130000", opener=lambda req: 1 / 0) is None
    assert parse_forecast([{"timeSeries": []}]) is None
    print("weather sim OK: parse, rainy classification, pop max, failure -> None")


if __name__ == "__main__":
    main()
