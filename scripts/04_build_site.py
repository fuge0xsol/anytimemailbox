# -*- coding: utf-8 -*-
"""
第 4 步:读取 data/locations_rdi.jsonl,生成单文件静态站 dist/index.html。
功能:统计卡片 + 州/价格/判定筛选 + 搜索 + 排序 + 地址卡片 + 验证跳转 + FAQ + 免责声明。
"""
import html
import json
import time
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IN_JSONL = ROOT / "data" / "locations_rdi.jsonl"
OUT = ROOT / "dist" / "index.html"

# ======= 站点配置(按需修改)=======
SITE_TITLE = "美国住宅地址虚拟邮箱查询 | USPS RDI 验证筛选"
SITE_DESC = ("实时抓取 Anytime Mailbox 全部在营地点,自动筛选住宅特征地址,"
             "适用于 LLC 注册、银行开户、信用卡申请、邮件转寄。按州和价格筛选,一键验证。")
AFFILIATE_URL = "https://www.anytimemailbox.com/"   # 换成你的 referralrock 返佣链接
VERIFY_URL = "https://www.smarty.com/products/single-address"

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "Washington D.C.",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

RDI_LABEL = {
    "R": ("疑似住宅", "badge-r"),
    "C": ("商业特征", "badge-c"),
    "?": ("待验证", "badge-u"),
}

FAQ = [
    ("什么是住宅地址(Residential Address)?",
     "USPS 用 RDI(Residential Delivery Indicator)把每个投递点标记为住宅或商业。"
     "住宅地址在银行、券商、支付机构的风控里通常更容易通过,商业地址(如快递门店、写字楼)则容易被拒。"
     "超过八成虚拟邮箱用的是商业地址,所以住宅地址很稀缺。"),
    ("这里的“住宅判定”准确吗?",
     "列表中的“疑似住宅/商业特征”标签由程序自动分析,标注 R 的表示经 UPS/FedEx 地址校验接口判为住宅,"
     "标注 H 的为关键词启发式结果,可能有偏差。注册前建议点击卡片上的“验证地址”,"
     "在 Smarty 免费查询页粘贴确认最终结果。"),
    ("能用来注册 LLC / 银行账户吗?",
     "住宅地址注册 LLC、EIN、银行开户的通过率明显高于商业地址,但任何虚拟邮箱地址都不是物理住所,"
     "部分机构(如某些银行)仍可能要求补充证明。请自行评估合规要求。"),
    ("价格为什么不一样?最低多少钱?",
     "每个地点的运营方独立定价,展示的是该地点最低套餐的月费。部分地点不公开价格,显示“询价”。"
     "年付通常有折扣,注册页可看全部套餐。"),
    ("数据多久更新一次?",
     "地址与价格直接抓取 Anytime Mailbox 官网在营地点,生成日期见页面顶部。"
     "想刷新数据重新运行采集脚本即可,全程自动。"),
    ("Unit # / MAILBOX 是什么?",
     "注册成功后你会获得专属私人邮箱号(PMB),收件地址即“街道地址 + Unit # 你的邮箱号”,"
     "运营方会把信件扫描上传或转寄给你。"),
]


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def load_records():
    recs = []
    for line in IN_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if not r.get("in_us_state"):
            continue
        recs.append(r)
    # 地址去重(同街道同邮编视为同一投递点)
    seen, dedup = set(), []
    for r in recs:
        k = (r["street"].lower().replace(".", "").replace(" ", ""), r["zip"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    dedup.sort(key=lambda r: (r["min_month"] if r["min_month"] is not None else 9999, r["state"], r["city"]))
    return dedup


def build_cards(recs) -> str:
    out = []
    for i, r in enumerate(recs):
        st = r["state"]
        full_addr = f"{r['street']}, {r['city']}, {st} {r['zip']}"
        search = f"{r['city']} {r['street']} {r['zip']}".lower()
        if r["min_month"] is not None:
            price_html = f"<strong>${r['min_month']:.2f}</strong>/月起"
        else:
            price_html = "<strong>询价</strong>"
        label, cls = RDI_LABEL.get(r.get("rdi", "?"), RDI_LABEL["?"])
        out.append(f'''<div class="card" data-st="{st}" data-price="{r['min_month'] if r['min_month'] is not None else 9999}" data-rdi="{r.get('rdi', '?')}" data-search="{esc(search)}">
  <div class="card-badge {cls}">{label}</div>
  <h3 class="card-addr">{esc(r['street'])}</h3>
  <p class="card-city">{esc(r['city'])}, {st} {r['zip']} &middot; <button class="card-verify" onclick="verifyAddr(this)" data-addr="{esc(full_addr)}">验证地址</button></p>
  <div class="card-bottom">
    <div class="card-price">{price_html}</div>
    <a class="card-cta" href="{AFFILIATE_URL}" target="_blank" rel="noopener nofollow sponsored">立即注册 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M13 7l5 5m0 0l-5 5m5-5H6"/></svg></a>
  </div>
</div>''')
    return "\n".join(out)


def build_state_options(recs) -> str:
    cnt = Counter(r["state"] for r in recs)
    rows = sorted(cnt.items(), key=lambda kv: -kv[1])
    return "\n".join(
        f'<option value="{st}">{STATE_NAMES.get(st, st)} ({n})</option>' for st, n in rows)


def build_faq() -> str:
    parts = []
    for q, a in FAQ:
        parts.append(f'''<details class="faq-item"><summary>{esc(q)}</summary><p>{esc(a)}</p></details>''')
    return "\n".join(parts)


def build_faq_jsonld() -> str:
    items = [{
        "@type": "Question", "name": esc(q),
        "acceptedAnswer": {"@type": "Answer", "text": esc(a)}
    } for q, a in FAQ]
    return json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": items},
                      ensure_ascii=False)


TEMPLATE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<meta name="robots" content="index,follow">
<link rel="canonical" href="">
<meta property="og:type" content="website">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<script type="application/ld+json">__FAQJSONLD__</script>
<style>
:root{--bg:#f6f8fa;--card:#fff;--ink:#1a2332;--sub:#5b6b7f;--line:#e3e9f0;--accent:#0a7d4f;--accent2:#e8f5ee;--blue:#2563eb;--warn:#9a6700;}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink);line-height:1.6}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
header{background:linear-gradient(160deg,#0e2a1f 0%,#123a2a 60%,#155238 100%);color:#fff;padding:48px 0 36px}
header h1{font-size:26px;margin-bottom:10px}
header p.sub{color:#cfe7da;max-width:760px;font-size:14.5px}
.pills{margin-top:14px;display:flex;flex-wrap:wrap;gap:8px}
.pill{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.22);border-radius:999px;padding:3px 12px;font-size:12.5px;color:#e6f4ec}
.updated{margin-top:12px;font-size:12.5px;color:#9fc7b0}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:-20px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;box-shadow:0 4px 14px rgba(16,42,31,.06)}
.stat b{font-size:24px;color:var(--accent)}
.stat span{display:block;color:var(--sub);font-size:12.5px;margin-top:2px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:26px 0 6px}
.step{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-size:13.5px;color:var(--sub)}
.step b{color:var(--ink);display:block;margin-bottom:2px}
.toolbar{position:sticky;top:0;z-index:20;background:var(--bg);padding:14px 0 10px;margin-top:18px;border-bottom:1px solid var(--line)}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
select,input[type=search]{padding:9px 12px;border:1px solid var(--line);border-radius:9px;background:#fff;font-size:13.5px;color:var(--ink);outline:none}
select:focus,input:focus{border-color:var(--accent)}
input[type=search]{flex:1;min-width:180px}
.sort-btns{display:flex;gap:6px}
.sort-btns button{border:1px solid var(--line);background:#fff;border-radius:9px;padding:9px 12px;font-size:13px;cursor:pointer;color:var(--sub)}
.sort-btns button.on{border-color:var(--accent);color:var(--accent);background:var(--accent2)}
.count{font-size:13px;color:var(--sub);margin:10px 2px 12px}
.count b{color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:14px;padding-bottom:30px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;display:flex;flex-direction:column;gap:8px;transition:box-shadow .15s}
.card:hover{box-shadow:0 6px 18px rgba(16,42,31,.09)}
.card-badge{align-self:flex-start;font-size:12px;font-weight:600;border-radius:6px;padding:2px 9px}
.badge-r{background:var(--accent2);color:var(--accent)}
.badge-c{background:#f1f3f6;color:#7a8698}
.badge-u{background:#e8effd;color:var(--blue)}
.card-addr{font-size:15.5px;line-height:1.4}
.card-city{font-size:13px;color:var(--sub)}
.card-verify{border:none;background:none;color:var(--blue);cursor:pointer;font-size:13px;padding:0;text-decoration:underline}
.card-bottom{display:flex;justify-content:space-between;align-items:center;margin-top:auto;padding-top:8px;border-top:1px dashed var(--line)}
.card-price{font-size:13px;color:var(--sub)}
.card-price strong{font-size:17px;color:var(--ink)}
.card-cta{display:inline-flex;align-items:center;gap:5px;background:var(--accent);color:#fff;text-decoration:none;border-radius:9px;padding:8px 14px;font-size:13.5px}
.card-cta svg{width:15px;height:15px}
.empty{display:none;text-align:center;color:var(--sub);padding:50px 0}
#toast{position:fixed;left:50%;bottom:34px;transform:translateX(-50%);background:#22303f;color:#fff;padding:10px 20px;border-radius:10px;font-size:13.5px;opacity:0;pointer-events:none;transition:opacity .25s;z-index:99}
#toast.show{opacity:.96}
.faq{margin:10px 0 40px}
.faq h2{font-size:19px;margin-bottom:12px}
.faq-item{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:13px 17px;margin-bottom:9px}
.faq-item summary{cursor:pointer;font-weight:600;font-size:14.5px}
.faq-item p{margin-top:8px;color:var(--sub);font-size:13.5px}
.note{background:#fdf6e3;border:1px solid #f0e0b0;color:var(--warn);border-radius:11px;padding:13px 17px;font-size:13px;margin:8px 0 30px}
footer{border-top:1px solid var(--line);color:var(--sub);font-size:12.5px;padding:22px 0 40px}
@media(max-width:760px){.stats{grid-template-columns:repeat(2,1fr)}.steps{grid-template-columns:1fr}header h1{font-size:21px}}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <h1>美国住宅地址虚拟邮箱查询</h1>
    <p class="sub">自动抓取 Anytime Mailbox 全部在营地点并做住宅/商业特征判定。住宅地址注册 LLC、银行开户、申请信用卡通过率远高于商业地址——而多数虚拟邮箱都是商业地址,这里帮你把它们筛出来。</p>
    <div class="pills"><span class="pill">LLC 注册</span><span class="pill">银行开户</span><span class="pill">信用卡申请</span><span class="pill">邮件转寄</span><span class="pill">隐私保护</span></div>
    <div class="updated">数据生成于 __DATE__ &middot; 来源:Anytime Mailbox 官网在营地点(实时抓取)</div>
  </div>
</header>

<main class="wrap">
  <div class="stats">
    <div class="stat"><b>__NALL__</b><span>在营地点</span></div>
    <div class="stat"><b>__NSTATE__</b><span>覆盖州/特区</span></div>
    <div class="stat"><b>$__MINP__</b><span>最低月费</span></div>
    <div class="stat"><b>__NRES__</b><span>疑似住宅地址</span></div>
  </div>

  <div class="steps">
    <div class="step"><b>1. 筛选地址</b>按州、价格、住宅判定筛选,或直接搜索城市/邮编。</div>
    <div class="step"><b>2. 点“验证地址”</b>自动复制地址并打开 Smarty 免费查询页,确认住宅属性。</div>
    <div class="step"><b>3. 注册开通</b>点击“立即注册”到官网开通,获得街道地址+专属邮箱号。</div>
  </div>

  <div class="toolbar"><div class="bar">
    <select id="stateFilter"><option value="">全部州</option>__STATEOPTS__</select>
    <select id="priceFilter">
      <option value="">不限价格</option>
      <option value="10">$10 以下</option>
      <option value="15">$15 以下</option>
      <option value="20">$20 以下</option>
      <option value="30">$30 以下</option>
      <option value="50">$50 以下</option>
    </select>
    <select id="rdiFilter">
      <option value="">全部判定</option>
      <option value="R">疑似住宅</option>
      <option value="?">待验证</option>
      <option value="C">商业特征</option>
    </select>
    <input type="search" id="searchInput" placeholder="搜索城市 / 街道 / 邮编…">
    <div class="sort-btns">
      <button data-sort="price" class="on">价格 ↑</button>
      <button data-sort="state">州</button>
      <button data-sort="city">城市</button>
    </div>
  </div></div>

  <p class="count">共 <b id="showCount">0</b> 个地址</p>
  <div class="grid" id="grid">
__CARDS__
  </div>
  <div class="empty" id="empty">没有匹配的地址,换个筛选条件试试。</div>

  <div class="note">⚠️ 判定说明:“疑似住宅”来自 UPS/FedEx 地址校验接口或关键词启发式分析,可能存在偏差;“待验证”表示尚未做接口校验。注册前请务必点击卡片上的“验证地址”,在 Smarty 官方查询页做最终确认。</div>

  <div class="faq">
    <h2>常见问题</h2>
__FAQ__
  </div>
</main>

<footer><div class="wrap">
  数据来源:Anytime Mailbox 公开地点页(价格以官网注册页为准)&middot; 住宅/商业数据:USPS RDI(经第三方地址校验接口)&middot;<br>
  本页含联盟推广链接,通过链接注册可能为本站带来返佣,不影响你的价格。
</div></footer>

<div id="toast"></div>
<script>
const toast=document.getElementById("toast");
function verifyAddr(btn){
  const addr=btn.dataset.addr;
  navigator.clipboard.writeText(addr).then(()=>{
    toast.textContent="地址已复制,在打开的页面中粘贴查询";
    toast.classList.add("show");
    setTimeout(()=>toast.classList.remove("show"),3000);
  }).catch(()=>{});
  window.open("__VERIFYURL__","_blank");
}
const grid=document.getElementById("grid"),empty=document.getElementById("empty"),showCount=document.getElementById("showCount");
const cards=Array.from(grid.querySelectorAll(".card"));
const stateFilter=document.getElementById("stateFilter"),priceFilter=document.getElementById("priceFilter"),rdiFilter=document.getElementById("rdiFilter"),searchInput=document.getElementById("searchInput");
const sortBtns=document.querySelectorAll(".sort-btns button");
let currentSort="price",sortDir=1;
function applyFilters(){
  const st=stateFilter.value,maxPrice=priceFilter.value?parseFloat(priceFilter.value):0;
  const rdi=rdiFilter.value,q=searchInput.value.toLowerCase().trim();
  const d=sortDir;
  const sorted=[...cards].sort((a,b)=>{
    if(currentSort==="price")return d*(parseFloat(a.dataset.price)-parseFloat(b.dataset.price));
    if(currentSort==="state")return d*(a.dataset.st.localeCompare(b.dataset.st)||parseFloat(a.dataset.price)-parseFloat(b.dataset.price));
    const ca=a.querySelector(".card-city").textContent,cb=b.querySelector(".card-city").textContent;
    return d*(ca.localeCompare(cb)||parseFloat(a.dataset.price)-parseFloat(b.dataset.price));
  });
  sorted.forEach(c=>grid.appendChild(c));
  let visible=0;
  cards.forEach(c=>{
    let show=true;
    if(st&&c.dataset.st!==st)show=false;
    if(maxPrice&&parseFloat(c.dataset.price)>maxPrice)show=false;
    if(rdi&&c.dataset.rdi!==rdi)show=false;
    if(q&&!c.dataset.search.includes(q))show=false;
    c.style.display=show?"":"none";
    if(show)visible++;
  });
  showCount.textContent=visible;
  empty.style.display=visible===0?"block":"none";
}
stateFilter.addEventListener("change",applyFilters);
priceFilter.addEventListener("change",applyFilters);
rdiFilter.addEventListener("change",applyFilters);
searchInput.addEventListener("input",applyFilters);
sortBtns.forEach(b=>b.addEventListener("click",()=>{
  const s=b.dataset.sort;
  if(currentSort===s){sortDir=-sortDir}else{currentSort=s;sortDir=1}
  sortBtns.forEach(x=>{x.classList.toggle("on",x===b);x.textContent=x.textContent.replace(/[↑↓]/,"")+(x===b?(sortDir===1?" ↑":" ↓"):"")});
  applyFilters();
}));
applyFilters();
</script>
</body>
</html>'''


def main():
    recs = load_records()
    priced = [r for r in recs if r["min_month"] is not None]
    n_res = sum(1 for r in recs if r.get("rdi") == "R")
    html_out = (TEMPLATE
        .replace("__TITLE__", SITE_TITLE)
        .replace("__DESC__", SITE_DESC)
        .replace("__FAQJSONLD__", build_faq_jsonld())
        .replace("__DATE__", date.today().strftime("%Y-%m-%d"))
        .replace("__NALL__", str(len(recs)))
        .replace("__NSTATE__", str(len({r["state"] for r in recs})))
        .replace("__MINP__", f"{min(r['min_month'] for r in priced):.2f}" if priced else "—")
        .replace("__NRES__", str(n_res))
        .replace("__STATEOPTS__", build_state_options(recs))
        .replace("__CARDS__", build_cards(recs))
        .replace("__FAQ__", build_faq())
        .replace("__VERIFYURL__", VERIFY_URL))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html_out, encoding="utf-8")
    print(f"built {OUT} ({len(html_out)//1024} KB): {len(recs)} locations, {n_res} residential-ish")


if __name__ == "__main__":
    main()
