// 浏览器内抓取 Anytime Mailbox 详情页(v5 最终版,过 Cloudflare)
// ====================================================================
// 为什么这么绕:直接 curl/python 请求 /s/{slug} 会被 Cloudflare 路径级规则
// 软拦截(HTTP 200 但返回假的 /locations 页);同源 fetch 也会被按 URL 缓存
// 拦截决策。唯一稳定方案是【页面上下文里的隐藏 iframe 文档加载】+ 随机参数
// 绕缓存键。实测 ~16 页/分钟,2000+ 页约 2.5 小时。
//
// 用法:在 ZCode 浏览器(IAB)打开任意真实地点页,如
//   https://www.anytimemailbox.com/s/alameda-1311-park-street
// 然后按【第 1 步】注入队列 →【第 2 步】启动 worker(可启动两个实例并行,
// 共享游标)。每次成功自动存 localStorage("atmb_recs_v1"),页面被站点 JS
// 刷新后可无损恢复。
//
// 注意:
//  - path=usa 的 GetMapDetails 里混着加拿大/墨西哥/波多黎各地点,解析器遇到
//    非 "城市, ST 12345" 格式会标 foreign 快速跳过,不会浪费限速惩罚
//  - 连续 4 次软拦截会自动冷却 90 秒;若被硬拦,先手动等 10-20 分钟再继续

// ---------- 【第 1 步】初始化 + 注入队列(可分多次 push) ----------
(() => {
  window.__q = []; window.__i = 0; window.__errs = [];
  window.__started = false; window.__startedB = false;
  window.__done = false; window.__doneB = false;
  const saved = localStorage.getItem("atmb_recs_v1");
  window.__recs = saved ? JSON.parse(saved) : [];
  // window.__q = window.__q.concat(/* slug 数组 */[]);
})();

// ---------- 【第 2 步】启动 worker(重复调用两次即双实例,第二个传 B) ----------
function startWorker(tag) {   // tag = "" 或 "B"
  const flag = "__started" + tag, doneFlag = "__done" + tag, BK = "__bust" + tag;
  if (window[flag]) return "running";
  window[flag] = true; window[doneFlag] = false;
  window[BK] = 100000 + Math.floor(Math.random() * 900000);
  const cityRe = /^(.+?),\s*([A-Z]{2})\s+(\d{5})(?:-\d{4})?$/;
  function parseDoc(doc){
    if (!doc || doc.title.indexOf("Digital Mailboxes") < 0) return { fail: "block" };
    const block = doc.querySelector(".t-addr");
    if (!block) return { fail: "block" };
    block.querySelectorAll("span.t-placeholder").forEach(s => s.remove());
    const ttext = block.querySelector(".t-text");
    if (!ttext) return { fail: "block" };
    let street = null, cityline = null;
    Array.from(ttext.children).forEach(el => {
      const ln = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!ln || ln === "United States") return;
      if (cityRe.test(ln)) cityline = ln;
      else if (street === null) street = ln;
    });
    if (!street || !cityline) return { fail: "foreign" };
    const cm = cityline.match(cityRe);
    const prices = [];
    const re = /US\$\s*([\d,]+\.\d{2})\s*\/\s*month/g;
    let pm;
    const html = doc.body.innerHTML;
    while ((pm = re.exec(html))) prices.push(parseFloat(pm[1].replace(/,/g, "")));
    return { rec: { street, city: cm[1].trim(), state: cm[2], zip: cm[3],
             min_month: prices.length ? Math.min(...prices) : null, n_plans: prices.length } };
  }
  let frame = null;
  function loadDoc(slug){
    return new Promise(resolve => {
      let settled = false;
      const to = setTimeout(() => { if (!settled) { settled = true; resolve(null); } }, 15000);
      if (!frame) {
        frame = document.createElement("iframe");
        frame.style.cssText = "position:absolute;width:100px;height:100px;left:-9999px;top:-9999px";
        document.body.appendChild(frame);
      }
      frame.onload = () => {
        if (settled) return;
        settled = true; clearTimeout(to);
        setTimeout(() => { try { resolve(frame.contentDocument); } catch (e) { resolve(null); } }, 200);
      };
      frame.onerror = () => { if (!settled) { settled = true; clearTimeout(to); resolve(null); } };
      window[BK]++;
      frame.src = slug + "?b=" + window[BK];   // 随机参数绕 CF 缓存的拦截决策
    });
  }
  (async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    let consecBad = 0, pace = 3600;
    while (true) {
      if (window.__i >= window.__q.length) break;
      const slug = window.__q[window.__i];
      window.__i = window.__i + 1;   // 共享游标取号
      const doc = await loadDoc(slug);
      const parsed = doc ? parseDoc(doc) : { fail: "block" };
      if (parsed.rec) {
        parsed.rec.slug = slug;
        window.__recs.push(parsed.rec);
        try { localStorage.setItem("atmb_recs_v1", JSON.stringify(window.__recs)); } catch (e) {}
        consecBad = 0;
        pace = Math.max(3600, pace - 200);
        await sleep(pace + Math.floor(Math.random() * 1200));
      } else if (parsed.fail === "foreign") {
        window.__errs.push(slug);
        await sleep(1500);            // 非美国地址:快速跳过
      } else {
        window.__errs.push(slug);
        consecBad++;
        pace = Math.min(12000, pace + 2000);
        if (consecBad >= 4) { await sleep(90000); consecBad = 0; }
        else await sleep(10000);
      }
    }
    window[doneFlag] = true;
  })();
  return "worker" + (tag || "A") + " started";
}

// ---------- 【第 3 步】收尾 ----------
// 全跑完后:JSON.stringify(window.__recs.splice(0, window.__recs.length)) 取回,
// 存入 data/browser_recs.jsonl,然后 python scripts/05_merge.py 合并。
// 页面若被站点 JS 刷新:重新执行第 1 步(会自动从 localStorage 恢复 __recs)。
