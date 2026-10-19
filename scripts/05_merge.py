# -*- coding: utf-8 -*-
"""
第 2.5 步:合并两路抓取结果,产出统一的 data/locations.jsonl。
  - cache/pages/*.html(直连爬虫缓存,用修好的解析器重 parse)
  - data/browser_recs.jsonl(浏览器页内 fetch 结果,更新,优先)
同时输出 data/missing_slugs.json(两路都没有的 slug,供补抓)。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from scrape_details import parse_page, US_STATES  # noqa: E402

MERGED = ROOT / "data" / "locations.jsonl"
BROWSER = ROOT / "data" / "browser_recs.jsonl"
MISSING = ROOT / "data" / "missing_slugs.json"


def main():
    sites = json.loads((ROOT / "data" / "us_sites.json").read_text(encoding="utf-8"))["sites"]
    site_by_slug = {s["url"]: s for s in sites}

    merged = {}
    # 1) 直连缓存
    for f in (ROOT / "cache" / "pages").glob("*.html"):
        slug = "/" + f.name.replace("__", "/").replace(".html", "")
        if slug not in site_by_slug:
            continue
        p = parse_page(f.read_text(encoding="utf-8", errors="replace"))
        if p:
            s = site_by_slug[slug]
            merged[slug] = {"slug": slug, "city_hint": s["text"], "lat": s["mapLat"],
                            "lng": s["mapLong"], "top_rated": bool(s.get("trated")), **p}
    n_cache = len(merged)

    # 2) 浏览器结果(覆盖同名);容忍多次写入粘连
    n_browser = 0
    if BROWSER.exists():
        text = BROWSER.read_text(encoding="utf-8")
        dec = json.JSONDecoder()
        pos = 0
        while pos < len(text):
            while pos < len(text) and text[pos] in " \t\r\n":
                pos += 1
            if pos >= len(text):
                break
            obj, end = dec.raw_decode(text, pos)
            r = obj
            slug = r["slug"]
            if slug in site_by_slug:
                s = site_by_slug[slug]
                merged[slug] = {"slug": slug, "city_hint": s["text"], "lat": s["mapLat"],
                                "lng": s["mapLong"], "top_rated": bool(s.get("trated")),
                                "in_us_state": r.get("state") in US_STATES,
                                **{k: v for k, v in r.items() if k != "slug"}}
                n_browser += 1
            pos = end

    MERGED.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in merged.values()),
                      encoding="utf-8")
    missing = [s["url"] for s in sites if s["url"] not in merged]
    MISSING.write_text(json.dumps(missing))
    print(f"cache={n_cache} browser={n_browser} merged={len(merged)} missing={len(missing)}")


if __name__ == "__main__":
    main()
