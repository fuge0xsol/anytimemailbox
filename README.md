# 美国住宅地址虚拟邮箱查询站(residential-mailbox)

按 tools.upthos.com/address/ 的思路复刻并升级:**实时抓取 Anytime Mailbox 全部在营地点 → 自动解析地址与最低月费 → 住宅/商业(RDI)判定 → 生成单文件静态查询站**。

当前数据(2026-10-19 抓取):**2067 个美国地点、49 州+DC、最低 $4.99/月、81 个疑似住宅**(原站 2026-08-10 数据:2316 点筛出 98 个住宅)。

## 原理(原站怎么做的,我们怎么做的)

| 环节 | upthos 原站 | 本项目 |
|---|---|---|
| 地点清单 | 抓 Anytime Mailbox 官网 | 1 个请求拿全:`location.anytimemailbox.com/location/GetMapDetails?path=usa` |
| 地址+价格 | 抓每个地点详情页 | `anytimemailbox.com/s/{slug}` 服务端渲染,直接解析 HTML |
| 住宅判定 | USPS RDI(商业数据源) | UPS/FedEx 免费地址校验 API(返回 RESIDENTIAL/COMMERCIAL)+ 关键词启发式兜底 |
| 前端 | 静态 HTML + 原生 JS 筛选 | 同款交互(州/价格/判定/搜索/排序),原创样式 |
| 变现 | referralrock 返佣链接 | 预留 `AFFILIATE_URL` 配置位 |

**关键坑:Cloudflare。** 对 `www.anytimemailbox.com` 连续 curl 会被软拦截(返回假的 /locations 页,HTTP 200 但没有地址块)。所以详情页抓取走 **真实浏览器页内 fetch**(过 CF、带 cookie),解析也在页面里完成,只回传小体积结果。`scripts/scrape_details.py` 仅作为备用(慢速小批量时可用)。

## 目录

```
scripts/
  01_fetch_sites.py     # 拉全部地点 slug(1 请求)→ data/us_sites.json
  scrape_details.py     # 备用:直连爬虫(带缓存断点续爬;会被 CF 软拦,慢速小批量才用)
  03_rdi_check.py       # 住宅/商业判定:--provider heuristic|ups|fedex → data/locations_rdi.jsonl
  04_build_site.py      # 生成 dist/index.html(单文件站)
  browser_fetch.js      # 说明见下:页内 fetch 抓取逻辑(在 ZCode 浏览器里执行)
data/                   # us_sites.json / locations.jsonl / locations_rdi.jsonl
cache/pages/            # 详情页 HTML 缓存(断点续爬)
dist/index.html         # 成品站
```

## 全流程重跑(更新数据)

1. `python scripts/01_fetch_sites.py`
2. 详情页抓取:二选一
   - **浏览器方案(推荐)**:在 ZCode 里打开任意 `/s/{slug}` 页面,执行 browser_fetch 的注入+启动逻辑(见 scripts/browser_fetch.js 顶部注释),跑完把 records 存回 `data/locations.jsonl`
   - 备用:`python scripts/scrape_details.py --delay 10`(对齐 robots crawl-delay,约 6.5 小时)
3. `python scripts/03_rdi_check.py --provider heuristic`(零凭据,秒出)
   - 要精确 RDI:`--provider ups`(环境变量 `UPS_CLIENT_ID`/`UPS_CLIENT_SECRET`)或 `--provider fedex`(`FEDEX_API_KEY`/`FEDEX_SECRET_KEY`)
   - UPS: developer.ups.com 免费注册 → My Apps → 创建 App 勾选 Address Validation → 拿 Client ID/Secret
   - FedEx: developer.fedex.com 免费注册 → 创建项目 → 拿 API Key/Secret
   - 结果缓存在 `cache/rdi/{provider}.json`,重跑不重复消耗
4. `python scripts/04_build_site.py` → `dist/index.html`

## 站点配置

`scripts/04_build_site.py` 顶部:
- `AFFILIATE_URL`:换成你自己的 Anytime Mailbox 返佣链接(referralrock)
- `SITE_TITLE` / `SITE_DESC`:SEO 文案
- `VERIFY_URL`:验证跳转页(默认 Smarty 免费单地址查询)

## 部署

`deploy.sh`:GitHub Pages + Cloudflare Pages 双发(先 `gh auth switch` 到对应账号)。

## 免责

地址与价格来自 Anytime Mailbox 公开页面(事实数据);住宅/商业判定为程序自动分析,注册前请用卡片上的"验证地址"到 Smarty 做最终确认。
