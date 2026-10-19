# -*- coding: utf-8 -*-
"""第 1 步:拉取 Anytime Mailbox 全部美国地点的 slug/坐标(1 个请求)。"""
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "us_sites.json"
URL = "https://location.anytimemailbox.com/location/GetMapDetails?path=usa"


def main():
    req = Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    sites = data.get("sites", [])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"saved {len(sites)} sites -> {OUT}")


if __name__ == "__main__":
    main()
