# -*- coding: utf-8 -*-
"""
爬取 Anytime Mailbox 全部美国地点详情页,解析出:
  街道地址 / 城市 / 州 / 邮编 / 全部套餐月费(取最低) / 坐标 / top-rated
结果追加写入 data/locations.jsonl,已处理的 slug 自动跳过(断点续爬)。

用法:
  python scripts/scrape_details.py                # 默认限速 3s + 抖动
  python scripts/scrape_details.py --delay 10     # 对齐 robots.txt crawl-delay
"""
import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent
SITES_JSON = ROOT / "data" / "us_sites.json"
OUT_JSONL = ROOT / "data" / "locations.jsonl"
CACHE_DIR = ROOT / "cache" / "pages"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 50 州 + DC 的两位代码,RDI/住宅地址场景只看这些(排除 PR/GU/VI 等)
US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}

ADDR_START = "<div class='t-addr'>"
ADDR_END = "<div class='t-feat'>"
PLACEHOLDER_RE = re.compile(r"<span class='t-placeholder'>[^<]*</span>")
LINE_DIV_RE = re.compile(r"<div[^>]*>([^<]+)</div>")
MONTH_PRICE_RE = re.compile(r"US\$\s*([\d,]+\.\d{2})\s*/\s*month")
CITYLINE_RE = re.compile(r"^(.+?),\s*([A-Z]{2})\s+(\d{5})(?:-\d{4})?$")
TAG_RE = re.compile(r"<[^>]+>")


def fetch(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def clean_line(s: str) -> str:
    s = TAG_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_page(html: str) -> dict | None:
    i, j = html.find(ADDR_START), html.find(ADDR_END)
    if i < 0:
        return None
    block = html[i: j if j > i else i + 4000]
    block = PLACEHOLDER_RE.sub("", block)  # 去掉 YOUR NAME / MAILBOX 占位
    lines = [clean_line(x) for x in LINE_DIV_RE.findall(block)]
    lines = [x for x in lines if x]
    street = None
    cityline = None
    for ln in lines:
        if ln in ("Your Real Street Address", "United States"):
            continue
        if CITYLINE_RE.match(ln):
            cityline = ln
        elif street is None:
            street = ln
    if not street or not cityline:
        return None
    cm = CITYLINE_RE.match(cityline)
    city, state, zc = cm.group(1).strip(), cm.group(2), cm.group(3)

    prices = [float(p.replace(",", "")) for p in MONTH_PRICE_RE.findall(html)]
    return {
        "street": street,
        "city": city,
        "state": state,
        "zip": zc,
        "min_month": min(prices) if prices else None,
        "n_plans": len(prices),
        "in_us_state": state in US_STATES,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=3.0, help="两次请求间隔秒数(robots.txt 建议 10)")
    ap.add_argument("--jitter", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=0, help="只爬前 N 个(调试用)")
    args = ap.parse_args()

    sites = json.loads(SITES_JSON.read_text(encoding="utf-8"))["sites"]
    if args.limit:
        sites = sites[: args.limit]

    done = set()
    if OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["slug"])
            except Exception:
                pass

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

    todo = [s for s in sites if s["url"] not in done]
    print(f"total {len(sites)}, done {len(done)}, todo {len(todo)}", flush=True)

    ok = fail = 0
    with OUT_JSONL.open("a", encoding="utf-8") as out:
        for i, site in enumerate(todo):
            slug = site["url"]                      # /s/alameda-1311-park-street
            url = "https://www.anytimemailbox.com" + slug
            cache = CACHE_DIR / (slug.strip("/").replace("/", "__") + ".html")
            rec = None
            try:
                if cache.exists() and cache.stat().st_size > 10000:
                    html = cache.read_text(encoding="utf-8", errors="replace")
                else:
                    html = fetch(url)
                    cache.write_text(html, encoding="utf-8", errors="replace")
                parsed = parse_page(html)
                if parsed:
                    rec = {"slug": slug, "city_hint": site["text"],
                           "lat": site["mapLat"], "lng": site["mapLong"],
                           "top_rated": bool(site.get("trated")), **parsed}
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                    ok += 1
                else:
                    fail += 1
                    print(f"[{i+1}/{len(todo)}] PARSE-FAIL {slug}", flush=True)
            except (HTTPError, URLError, TimeoutError, OSError) as e:
                fail += 1
                print(f"[{i+1}/{len(todo)}] FETCH-FAIL {slug}: {e}", flush=True)
                time.sleep(10)  # 失败后多歇一会
            if (i + 1) % 25 == 0:
                print(f"[{i+1}/{len(todo)}] ok={ok} fail={fail}", flush=True)
            time.sleep(args.delay + random.random() * args.jitter)

    print(f"DONE ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
