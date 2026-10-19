# -*- coding: utf-8 -*-
"""
第 3 步:对 locations.jsonl 里的每个地址做住宅/商业(RDI)判定,输出 data/locations_rdi.jsonl。

判定来源(优先级从高到低,--provider 控制):
  ups     UPS Address Validation API(免费注册 developer.ups.com,返回 RESIDENTIAL/COMMERCIAL)
  fedex   FedEx Address Validation API(免费注册 developer.fedex.com,返回 RESIDENTIAL/BUSINESS)
  heuristic  纯启发式关键词(零凭据,精度有限,结果标 "H")

凭据用环境变量:
  UPS_CLIENT_ID / UPS_CLIENT_SECRET
  FEDEX_API_KEY / FEDEX_SECRET_KEY

结果缓存于 cache/rdi/{provider}.json(键=规范化地址),重跑免费。
"""
import argparse
import base64
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IN_JSONL = ROOT / "data" / "locations.jsonl"
OUT_JSONL = ROOT / "data" / "locations_rdi.jsonl"
CACHE_DIR = ROOT / "cache" / "rdi"

COMMERCIAL_WORDS = [
    "suite", "ste ", "ste.", "ste#", "# ste", "pmb", "floor", " fl ", "fl.",
    "mall", "plaza", "shopping", "shpg", "market", "office", "corporate", "tower",
    "center", "centre", " ctr", "ctr.", "industrial", "warehouse", "complex",
    "building", "bldg", "twp", "village", "vlg", "station", "plz", "sq ",
    "commons", "crossing", "crossroads", "village",
]
COMMERCIAL_ROAD = ["blvd", "hwy", "fwy", "expy", "pkwy", "parkway"]
RESIDENTIAL_ROAD = [" ln", " lane", " ct", " court", " cir", " circle", " cv",
                    " cove", " trl", " trail", " way", " row", " walk", " pl "]


def norm_key(rec) -> str:
    return f"{rec['street']}|{rec['city']}|{rec['state']}|{rec['zip']}".lower()


def heuristic(rec) -> str:
    s = " " + rec["street"].lower() + " "
    if any(w in s for w in ("pmb", "ste ", "ste.", "ste#", "suite", "shpg", " ctr", "plz")):
        return "C"
    if "#" in s:
        return "C"
    if any(w in s for w in COMMERCIAL_WORDS):
        return "C"
    if any(w in s for w in COMMERCIAL_ROAD):
        return "C"
    if any(w in s for w in RESIDENTIAL_ROAD):
        return "R"
    return "?"  # 未知


# ---------------- UPS ----------------

def ups_token(client_id: str, client_secret: str) -> str:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        "https://onlinetools.ups.com/security/v1/oauth/token",
        data=b"grant_type=client_credentials",
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def ups_check(token: str, rec) -> str:
    body = {
        "AddressValidationRequest": {
            "Request": {"TransactionReference": {"CustomerContext": "rdi"}},
            "Address": {
                "AddressLine": [rec["street"]],
                "PoliticalDivision2": rec["city"],
                "PoliticalDivision1": rec["state"],
                "PostcodePrimaryLow": rec["zip"],
                "CountryCode": "US",
            },
        }
    }
    req = urllib.request.Request(
        "https://onlinetools.ups.com/api/addressvalidation/v1/1",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())
    text = json.dumps(resp).upper()
    if "RESIDENTIAL" in text:
        return "R"
    if "COMMERCIAL" in text:
        return "C"
    return "?"


# ---------------- FedEx ----------------

def fedex_token(key: str, secret: str) -> str:
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": key, "client_secret": secret}).encode()
    req = urllib.request.Request(
        "https://apis.fedex.com/oauth/token", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def fedex_check(token: str, rec) -> str:
    body = {
        "addressesToValidate": [{
            "customerMessageId": "rdi",
            "address": {
                "streetLines": [rec["street"]],
                "city": rec["city"],
                "stateOrProvinceCode": rec["state"],
                "postalCode": rec["zip"],
                "countryCode": "US",
            },
        }]
    }
    req = urllib.request.Request(
        "https://apis.fedex.com/address/v1/addresses/resolve",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())
    text = json.dumps(resp).upper()
    if "RESIDENTIAL" in text and "BUSINESS" not in text:
        return "R"
    if "BUSINESS" in text:
        return "C"
    if "RESIDENTIAL" in text:
        return "R"
    return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["heuristic", "ups", "fedex"], default="heuristic")
    ap.add_argument("--qps", type=float, default=2.0, help="API 每秒最多几次")
    args = ap.parse_args()

    records = [json.loads(l) for l in IN_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{args.provider}.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}

    token = None
    if args.provider == "ups":
        token = ups_token(os.environ["UPS_CLIENT_ID"], os.environ["UPS_CLIENT_SECRET"])
    elif args.provider == "fedex":
        token = fedex_token(os.environ["FEDEX_API_KEY"], os.environ["FEDEX_SECRET_KEY"])

    gap = 1.0 / args.qps
    n_api = 0
    for rec in records:
        k = norm_key(rec)
        if args.provider == "heuristic":
            rec["rdi"] = heuristic(rec)
            rec["rdi_src"] = "H"
            continue
        if k in cache:
            rec["rdi"], rec["rdi_src"] = cache[k], args.provider[:1].upper()
            continue
        try:
            verdict = ups_check(token, rec) if args.provider == "ups" else fedex_check(token, rec)
        except Exception as e:
            print("API err:", k, e)
            verdict = "?"
        cache[k] = verdict
        rec["rdi"], rec["rdi_src"] = verdict, args.provider[:1].upper()
        n_api += 1
        if n_api % 50 == 0:
            cache_file.write_text(json.dumps(cache), encoding="utf-8")
            print(f"api={n_api} cached={len(cache)}/{len(records)}", flush=True)
        time.sleep(gap)

    cache_file.write_text(json.dumps(cache), encoding="utf-8")
    OUT_JSONL.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
    summary = {}
    for r in records:
        summary[r.get("rdi", "?")] = summary.get(r.get("rdi", "?"), 0) + 1
    print(f"done. rdi summary: {summary}")


if __name__ == "__main__":
    main()
