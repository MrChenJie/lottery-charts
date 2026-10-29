const LOTTERIES = [
  { id: "ssq", label: "双色球", price: 2, redNeed: 6, blueNeed: 1 },
  { id: "dlt", label: "大乐透", price: 2, redNeed: 5, blueNeed: 2 },
  { id: "fc3d", label: "福彩3D", price: 2, redNeed: 3, blueNeed: 0, digit: true },
  { id: "pl3", label: "排列3", price: 2, redNeed: 3, blueNeed: 0, digit: true },
  { id: "qlc", label: "七乐彩", price: 2, redNeed: 7, blueNeed: 1 },
];

const state = {
  current: localStorage.getItem("lc_lottery") || "ssq",
  cache: {},
  status: null,
  predictions: null,
  window: Number(localStorage.getItem("lc_window") || 50),
  omitView: "red",
  lastPredictText: "",
  bust: "",
};

function $(id) {
  return document.getElementById(id);
}

function toast(msg) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 1600);
}

function formatBeijing(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).replace(/Z$/, "").replace("T", " ");
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const get = (t) => parts.find((p) => p.type === t)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")} 北京时间`;
}

function ballHtml(n, color) {
  return `<span class="ball ${color}">${n}</span>`;
}

function ballsHtml(red, blue) {
  const r = (red || []).map((n) => ballHtml(n, "red")).join("");
  const b = (blue || []).map((n) => ballHtml(n, "blue")).join("");
  return r + b;
}

function pickText(red, blue) {
  const r = (red || []).join(" ");
  const b = (blue || []).join(" ");
  return b ? `${r} + ${b}` : r;
}

async function loadJson(path) {
  const q = state.bust ? `?v=${encodeURIComponent(state.bust)}` : `?t=${Date.now()}`;
  const res = await fetch(path + q, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} HTTP ${res.status}`);
  return res.json();
}

function setStatus(text, kind) {
  const el = $("statusBar");
  el.textContent = text;
  el.className = "status" + (kind ? ` ${kind}` : "");
}

function lotteryMeta(id) {
  return LOTTERIES.find((l) => l.id === id) || LOTTERIES[0];
}

function selectLottery(id) {
  if (!LOTTERIES.some((l) => l.id === id)) return;
  state.current = id;
  state.omitView = "red";
  localStorage.setItem("lc_lottery", id);
  if (location.hash.replace("#", "") !== id) {
    history.replaceState(null, "", "#" + id);
  }
  renderTabs();
  renderBoard();
  renderLottery();
}

function renderTabs() {
  const tabs = $("tabs");
  tabs.innerHTML = LOTTERIES.map(
    (l) =>
      `<button type="button" data-id="${l.id}" class="${
        l.id === state.current ? "active" : ""
      }">${l.label}</button>`
  ).join("");
  tabs.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => selectLottery(btn.dataset.id));
  });
}

function renderWindowBar() {
  const bar = $("windowBar");
  bar.querySelectorAll("button[data-w]").forEach((btn) => {
    btn.classList.toggle("active", Number(btn.dataset.w) === state.window);
    btn.onclick = () => {
      state.window = Number(btn.dataset.w);
      localStorage.setItem("lc_window", String(state.window));
      renderWindowBar();
      renderLottery();
    };
  });
}

function confidenceLabel(c) {
  if (c === "cross_verified") return "多源交叉核对";
  if (c === "primary_only") return "单源（未完全交叉）";
  return "未知";
}

function beijingToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function comb(n, k) {
  n = Number(n);
  k = Number(k);
  if (k < 0 || n < 0 || k > n) return 0;
  if (k === 0 || k === n) return 1;
  k = Math.min(k, n - k);
  let r = 1;
  for (let i = 1; i <= k; i++) r = (r * (n - k + i)) / i;
  return Math.round(r);
}

function renderFreshness(data) {
  const el = $("freshness");
  if (!el) return;
  const d = (data.draws || [])[0];
  const today = beijingToday();
  const date = (d && String(d.date || "").slice(0, 10)) || "";
  const stLot = state.status?.lotteries?.[state.current] || {};
  const post = state.status?.post_draw;
  const parts = [];
  if (date && date === today) {
    parts.push(`<span class="badge ok">含今日开奖 ${date}</span>`);
  } else if (date) {
    parts.push(`<span class="badge warn">最新开奖日 ${date}（今日 ${today}）</span>`);
  }
  if (d?.verified) parts.push(`<span class="badge ok">最新期已交叉核对</span>`);
  else if (d) parts.push(`<span class="badge warn">最新期单源</span>`);
  if (data.confidence === "cross_verified") {
    parts.push(`<span class="chip"><strong>置信</strong> 多源核对</span>`);
  }
  if (post?.beijing_date === today && post?.ready?.[state.current]) {
    parts.push(`<span class="chip"><strong>开奖后同步</strong> 已就绪</span>`);
  }
  parts.push(
    `<span class="muted">数据更新 ${formatBeijing(data.updated_at || stLot.updated_at)}</span>`
  );
  el.innerHTML = parts.join(" ");
}

function renderLatest(data) {
  const title = $("lotteryTitle");
  const schedule = $("scheduleText");
  const latest = $("latestDraw");
  title.textContent = data.name || state.current;
  schedule.textContent = data.schedule || "";
  renderFreshness(data);

  if (!data.ok || !(data.draws || []).length) {
    latest.innerHTML = `<p class="warn">暂无真实开奖数据${
      data.error ? "：" + data.error : ""
    }</p>`;
    return;
  }

  const d = data.draws[0];
  const badge = d.verified
    ? `<span class="badge ok">已交叉核对</span>`
    : `<span class="badge warn">单源</span>`;
  const sources = (d.sources || []).length
    ? `<span class="muted">来源 ${(d.sources || []).join(" + ")}</span>`
    : "";
  const text = pickText(d.red, d.blue);
  latest.innerHTML = `
    <div class="meta-line">第 ${d.issue} 期 · ${d.date || "日期未知"} ${badge} ${sources}</div>
    <div class="predict-balls">${ballsHtml(d.red, d.blue)}
      <button type="button" class="btn ghost" data-copy="${text}">复制开奖号</button>
    </div>
  `;
  latest.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        toast("已复制开奖号");
      } catch (_) {
        toast("复制失败，请长按号码");
      }
    };
  });
}

function getAnalysis(data) {
  const meta = data.meta || {};
  const draws = data.draws || [];
  if (!window.LotteryAnalysis || !draws.length) return null;
  return LotteryAnalysis.analyze(draws, meta, state.window, state.current);
}

function renderNextPredict(analysis) {
  const box = $("nextPredict");
  const np = analysis?.next_prediction;
  if (!np || !np.ok) {
    state.lastPredictText = "";
    box.innerHTML = `<p class="muted">暂无下一期预测（需真实开奖数据）</p>`;
    return;
  }
  state.lastPredictText = pickText(np.red, np.blue);
  const issueLine = np.for_issue
    ? `面向第 <strong>${np.for_issue}</strong> 期`
    : "面向下一期";
  const when = np.next_draw_hint ? ` · 预计开奖 ${np.next_draw_hint}` : "";
  const after = np.after_issue
    ? `基于已开第 ${np.after_issue} 期（${np.after_date || "日期未知"}）`
    : "";
  const reasons = (np.reasons || [])
    .map(
      (r) =>
        `<li><span class="ball sm ${r.area === "后区" ? "blue" : "red"}">${r.n}</span>
        <span class="reason-area">${r.area || ""}</span>
        <span class="reason-text">${r.reason}</span></li>`
    )
    .join("");
  box.innerHTML = `
    <div class="meta-line">${issueLine}${when}</div>
    <p class="muted">${after} · 统计窗口 ${np.based_on_issues} 期</p>
    <div class="predict-balls">${ballsHtml(np.red, np.blue)}</div>
    <ol class="reason-list">${reasons}</ol>
    <p class="muted">${np.method || ""}</p>
  `;
  renderBetCalc(np);
}

function renderBetCalc(np) {
  const box = $("betCalc");
  const meta = lotteryMeta(state.current);
  const redDefault = Math.max(meta.redNeed, (np?.red || []).length || meta.redNeed);
  const blueDefault = meta.blueNeed
    ? Math.max(meta.blueNeed, (np?.blue || []).length || meta.blueNeed)
    : 0;

  if (meta.digit) {
    box.innerHTML = `
      <p class="muted">3D / 排列3 直选单注 ${meta.price} 元。定位复式：百×十×个 种直选组合。</p>
      <div class="calc-fields">
        <label>百位个数<input id="cBai" type="number" min="1" max="10" value="1" /></label>
        <label>十位个数<input id="cShi" type="number" min="1" max="10" value="1" /></label>
        <label>个位个数<input id="cGe" type="number" min="1" max="10" value="1" /></label>
      </div>
      <div class="calc-out" id="calcOut"></div>
    `;
    const recalc = () => {
      const a = Math.min(10, Math.max(1, Number($("cBai").value) || 1));
      const b = Math.min(10, Math.max(1, Number($("cShi").value) || 1));
      const c = Math.min(10, Math.max(1, Number($("cGe").value) || 1));
      const n = a * b * c;
      $("calcOut").innerHTML = `直选约 <strong>${n}</strong> 注 · 金额 <strong>${n * meta.price}</strong> 元`;
    };
    ["cBai", "cShi", "cGe"].forEach((id) => ($(id).oninput = recalc));
    recalc();
    return;
  }

  box.innerHTML = `
    <div class="calc-fields">
      <label>前区/红球选号数<input id="cRed" type="number" min="${meta.redNeed}" max="35" value="${redDefault}" /></label>
      ${
        meta.blueNeed
          ? `<label>后区/蓝球选号数<input id="cBlue" type="number" min="${meta.blueNeed}" max="16" value="${blueDefault}" /></label>`
          : ""
      }
    </div>
    <div class="calc-out" id="calcOut"></div>
  `;
  const recalc = () => {
    const r = Math.max(meta.redNeed, Number($("cRed").value) || meta.redNeed);
    const b = meta.blueNeed
      ? Math.max(meta.blueNeed, Number($("cBlue")?.value) || meta.blueNeed)
      : 0;
    const n = comb(r, meta.redNeed) * (meta.blueNeed ? comb(b, meta.blueNeed) : 1);
    $("calcOut").innerHTML = `复式约 <strong>${n.toLocaleString("zh-CN")}</strong> 注 · 金额 <strong>${(
      n * meta.price
    ).toLocaleString("zh-CN")}</strong> 元 <span class="muted">（${meta.price}元/注）</span>`;
  };
  $("cRed").oninput = recalc;
  if ($("cBlue")) $("cBlue").oninput = recalc;
  recalc();
}

function renderReference(analysis) {
  const box = $("refPicks");
  const chips = $("hotCold");
  const danSha = $("danSha");
  if (!analysis || !analysis.ok) {
    box.innerHTML = `<p class="muted">${(analysis && analysis.message) || "暂无参考选号"}</p>`;
    chips.innerHTML = "";
    danSha.innerHTML = "";
    return;
  }
  box.innerHTML = (analysis.picks || [])
    .map((p) => {
      const text = pickText(p.red, p.blue);
      return `
      <div class="ref-pick">
        <span class="pick-label">${p.label}</span>
        ${ballsHtml(p.red, p.blue)}
        <button type="button" class="btn ghost" data-copy="${text}">复制</button>
      </div>`;
    })
    .join("") +
    `<p class="muted">${analysis.message}（基于 ${analysis.based_on_issues} 期）</p>`;

  box.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        toast("已复制");
      } catch (_) {
        toast("复制失败");
      }
    };
  });

  const parts = [];
  if (analysis.hot_red?.length) {
    parts.push(`<span class="chip"><strong>热号</strong> ${analysis.hot_red.join(" ")}</span>`);
  }
  if (analysis.cold_red?.length) {
    parts.push(`<span class="chip"><strong>冷/欲出</strong> ${analysis.cold_red.join(" ")}</span>`);
  }
  if (analysis.hot_blue?.length) {
    parts.push(`<span class="chip"><strong>蓝热</strong> ${analysis.hot_blue.join(" ")}</span>`);
  }
  if (analysis.cold_blue?.length) {
    parts.push(`<span class="chip"><strong>蓝冷</strong> ${analysis.cold_blue.join(" ")}</span>`);
  }
  chips.innerHTML = parts.join("");

  danSha.innerHTML = `
    <div class="ds-row"><span class="ds-tag dan">定胆</span> ${
      analysis.dan?.length
        ? analysis.dan.map((n) => ballHtml(n, "red")).join("")
        : '<span class="muted">—</span>'
    }</div>
    <div class="ds-row"><span class="ds-tag sha">杀号</span> ${
      analysis.sha?.length
        ? analysis.sha.map((n) => `<span class="ball kill">${n}</span>`).join("")
        : '<span class="muted">—</span>'
    }</div>
    <p class="muted">定胆：重号 / 邻号 / 欲出≥1.3；杀号：低频高遗漏候选（娱乐缩号）</p>
  `;
}

function renderForm(analysis) {
  const grid = $("formGrid");
  const f = analysis?.latest_form || {};
  const keys = Object.keys(f);
  if (!keys.length) {
    grid.innerHTML = `<p class="muted">暂无形态数据</p>`;
    return;
  }
  const labels = {
    sum: "和值",
    span: "跨度",
    odd_even: "奇偶比",
    big_small: "大小比",
    zones: "三区比",
    consecutive_pairs: "连号组数",
    repeat_vs_prev: "重号个数",
    mod3: "012路",
    group: "组选类型",
  };
  grid.innerHTML = keys
    .map(
      (k) => `
    <div class="form-item">
      <div class="form-k">${labels[k] || k}</div>
      <div class="form-v">${f[k]}</div>
    </div>`
    )
    .join("");
}

function omitRowsForView(analysis, meta) {
  if (state.omitView === "blue") return analysis.omission_blue || [];
  if (meta.digit && analysis.omission_positions) {
    if (state.omitView === "bai") return analysis.omission_positions.bai || [];
    if (state.omitView === "shi") return analysis.omission_positions.shi || [];
    if (state.omitView === "ge") return analysis.omission_positions.ge || [];
  }
  return analysis.omission_red || [];
}

function renderOmit(analysis, meta) {
  const tabs = $("omitTabs");
  const table = $("omitTable");
  if (!analysis?.ok) {
    tabs.innerHTML = "";
    table.innerHTML = `<p class="muted">暂无遗漏表</p>`;
    return;
  }

  const tabDefs = [];
  if (meta.digit) {
    tabDefs.push(
      { id: "bai", label: "百位" },
      { id: "shi", label: "十位" },
      { id: "ge", label: "个位" },
      { id: "red", label: "不分位" }
    );
  } else {
    tabDefs.push({ id: "red", label: meta.blue_count ? "前区/红球" : "号码" });
    if ((meta.blue_max || 0) > 0) tabDefs.push({ id: "blue", label: "后区/蓝球" });
  }
  if (!tabDefs.some((t) => t.id === state.omitView)) state.omitView = tabDefs[0].id;

  tabs.innerHTML = tabDefs
    .map(
      (t) =>
        `<button type="button" data-omit="${t.id}" class="${
          state.omitView === t.id ? "active" : ""
        }">${t.label}</button>`
    )
    .join("");
  tabs.querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => {
      state.omitView = btn.dataset.omit;
      renderOmit(analysis, meta);
    };
  });

  const rows = omitRowsForView(analysis, meta)
    .slice()
    .sort((a, b) => +a.n - +b.n);
  const head = `
    <tr>
      <th>号码</th><th>出现</th><th>当前遗漏</th><th>平均遗漏</th>
      <th>最大遗漏</th><th>最大连出</th><th>欲出几率</th>
    </tr>`;
  const body = rows
    .map((r) => {
      const hot = r.want_rate >= 1.5 ? " want" : "";
      return `<tr class="${hot}">
        <td><strong>${r.n}</strong></td>
        <td>${r.appear}</td>
        <td>${r.current}</td>
        <td>${r.avg}</td>
        <td>${r.max}</td>
        <td>${r.max_streak}</td>
        <td>${r.want_rate}</td>
      </tr>`;
    })
    .join("");
  table.innerHTML = `<table class="omit">${head}${body}</table>`;
}

function freqMap(draws, key) {
  const map = {};
  for (const d of draws) {
    for (const n of d[key] || []) {
      map[n] = (map[n] || 0) + 1;
    }
  }
  return map;
}

function drawFreqChart(data, analysis) {
  const canvas = $("freqChart");
  const ctx = canvas.getContext("2d");
  const draws = (data.draws || []).slice(0, state.window);
  const meta = data.meta || {};
  const digit = !!meta.digit;
  const redMax = meta.red_max || 33;
  const labels = digit
    ? Array.from({ length: 10 }, (_, i) => String(i))
    : Array.from({ length: redMax }, (_, i) => String(i + 1).padStart(2, "0"));
  const freq = freqMap(draws, "red");
  const values = labels.map((l) => freq[l] || 0);
  const maxV = Math.max(1, ...values);
  $("freqHint").textContent = `近 ${draws.length} 期号码出现次数（真实开奖）`;

  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.parentElement.clientWidth || 320;
  const cssH = 180;
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  canvas.style.width = cssW + "px";
  canvas.style.height = cssH + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const padL = 28;
  const padR = 8;
  const padT = 12;
  const padB = 28;
  const plotW = cssW - padL - padR;
  const plotH = cssH - padT - padB;
  const barW = plotW / labels.length;

  ctx.strokeStyle = "#c5d3e0";
  ctx.beginPath();
  ctx.moveTo(padL, padT);
  ctx.lineTo(padL, padT + plotH);
  ctx.lineTo(padL + plotW, padT + plotH);
  ctx.stroke();

  const wantMap = Object.fromEntries(
    (analysis?.omission_red || []).map((r) => [r.n, r.want_rate])
  );

  values.forEach((v, i) => {
    const h = (v / maxV) * (plotH - 2);
    const x = padL + i * barW + barW * 0.15;
    const y = padT + plotH - h;
    const wr = wantMap[labels[i]] || 0;
    ctx.fillStyle = wr >= 1.5 ? "#c45c26" : "#c62828";
    ctx.fillRect(x, y, barW * 0.7, h);
  });

  ctx.fillStyle = "#5a6b7d";
  ctx.font = "10px sans-serif";
  ctx.textAlign = "center";
  const step = labels.length > 20 ? 2 : 1;
  labels.forEach((l, i) => {
    if (i % step !== 0) return;
    ctx.fillText(l, padL + i * barW + barW / 2, cssH - 10);
  });
}

function renderTrend(data, analysis) {
  const wrap = $("trendWrap");
  const draws = (data.draws || []).slice(0, Math.min(30, state.window));
  if (!draws.length || !analysis?.ok) {
    wrap.innerHTML = `<p class="muted" style="padding:0.6rem">暂无走势数据</p>`;
    return;
  }

  const redNums = analysis.red_universe || [];
  const blueNums = analysis.blue_universe || [];
  const missRed = (analysis.miss_red || []).slice(0, draws.length);
  const missBlue = (analysis.miss_blue || []).slice(0, draws.length);

  const head =
    `<tr><th class="issue">期号</th>` +
    redNums.map((n) => `<th>${n}</th>`).join("") +
    (blueNums.length ? `<th class="sep">|</th>` + blueNums.map((n) => `<th>${n}</th>`).join("") : "") +
    `</tr>`;

  const body = draws
    .map((d, i) => {
      const redSet = new Set(d.red || []);
      const blueSet = new Set(d.blue || []);
      const mr = missRed[i] || {};
      const mb = missBlue[i] || {};
      const redCells = redNums
        .map((n) =>
          redSet.has(n)
            ? `<td><span class="hit-red">${n}</span></td>`
            : `<td class="miss">${mr[n] != null ? mr[n] : "·"}</td>`
        )
        .join("");
      const blueCells = blueNums
        .map((n) =>
          blueSet.has(n)
            ? `<td><span class="hit-blue">${n}</span></td>`
            : `<td class="miss">${mb[n] != null ? mb[n] : "·"}</td>`
        )
        .join("");
      return `<tr><td class="issue">${String(d.issue).slice(-5)}</td>${redCells}${
        blueNums.length ? `<td class="sep">·</td>${blueCells}` : ""
      }</tr>`;
    })
    .join("");

  wrap.innerHTML = `<table class="trend"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function renderDrawList(data) {
  const list = $("drawList");
  const draws = (data.draws || []).slice(0, 15);
  if (!draws.length) {
    list.innerHTML = `<p class="muted">暂无开奖列表</p>`;
    return;
  }
  list.innerHTML = draws
    .map((d) => {
      const badge = d.verified
        ? `<span class="badge ok">交叉</span>`
        : `<span class="badge warn">单源</span>`;
      return `
      <div class="draw-row">
        <div class="meta-line">第 ${d.issue} 期 · ${d.date || "—"} ${badge}
          <span class="muted"> ${(d.sources || []).join(" + ") || ""}</span>
        </div>
        <div class="balls">${ballsHtml(d.red, d.blue)}</div>
      </div>`;
    })
    .join("");
}

function renderNotes(data) {
  const notes = [];
  if (data.confidence) notes.push("置信度：" + confidenceLabel(data.confidence));
  if (data.updated_at) notes.push("数据时间：" + formatBeijing(data.updated_at));
  if (data.refresh_ok === false) notes.push("最近刷新失败：" + (data.refresh_error || ""));
  if (data.notes?.length) notes.push(...data.notes);
  if (data.error) notes.push("错误：" + data.error);
  notes.push(`当前统计窗口：近 ${state.window} 期`);
  $("notesText").textContent = notes.join(" ｜ ");
}

function renderBoard() {
  const grid = $("boardGrid");
  if (!grid) return;
  const today = beijingToday();
  grid.innerHTML = LOTTERIES.map((l) => {
    const data = state.cache[l.id];
    const d = data?.draws?.[0];
    const pred = state.predictions?.items?.[l.id];
    const date = d ? String(d.date || "").slice(0, 10) : "";
    const fresh =
      date === today
        ? `<span class="badge ok">今日</span>`
        : date
          ? `<span class="badge warn">${date.slice(5)}</span>`
          : `<span class="badge warn">无数据</span>`;
    const ver = d?.verified
      ? `<span class="badge ok">交叉</span>`
      : d
        ? `<span class="badge warn">单源</span>`
        : "";
    return `
      <button type="button" class="board-item ${l.id === state.current ? "active" : ""}" data-id="${l.id}">
        <div class="b-name">${l.label} ${fresh} ${ver}</div>
        <div class="b-meta">最新 ${d ? "第 " + d.issue + " 期" : "—"}</div>
        <div class="b-row">${d ? ballsHtml(d.red, d.blue) : ""}</div>
        <div class="b-label">下一期统计 ${pred?.for_issue ? "· " + pred.for_issue : ""}</div>
        <div class="b-row">${
          pred ? ballsHtml(pred.red, pred.blue) : '<span class="muted">加载中…</span>'
        }</div>
      </button>`;
  }).join("");
  grid.querySelectorAll("button[data-id]").forEach((btn) => {
    btn.onclick = () => selectLottery(btn.dataset.id);
  });
}

async function ensureData(id) {
  if (state.cache[id]) return state.cache[id];
  const data = await loadJson(`data/${id}.json`);
  state.cache[id] = data;
  return data;
}

async function preloadBoard() {
  await Promise.all(
    LOTTERIES.map(async (l) => {
      try {
        await ensureData(l.id);
      } catch (_) {
        /* ignore single failure */
      }
    })
  );
  renderBoard();
}

async function renderLottery() {
  try {
    const data = await ensureData(state.current);
    const analysis = getAnalysis(data);
    renderLatest(data);
    renderNextPredict(analysis);
    renderReference(analysis);
    renderForm(analysis);
    renderOmit(analysis, data.meta || {});
    drawFreqChart(data, analysis);
    renderTrend(data, analysis);
    renderDrawList(data);
    renderNotes(data);
    renderBoard();

    const st = state.status?.lotteries?.[state.current];
    if (!data.ok) {
      setStatus(
        `「${data.name || state.current}」真实数据不可用：${data.error || "未知原因"}。请核官网。`,
        "bad"
      );
    } else if (data.refresh_ok === false) {
      setStatus(
        `显示上一次成功抓取的真实数据；最近更新失败：${data.refresh_error || ""}`,
        "bad"
      );
    } else if (data.confidence === "cross_verified") {
      setStatus(
        `已加载 ${data.name}：多源交叉核对 ${data.verified_count || 0}/${data.draw_count || 0} 期 · 窗口 ${state.window} · 更新 ${formatBeijing(data.updated_at)}`,
        "ok"
      );
    } else {
      setStatus(
        `已加载 ${data.name}：${confidenceLabel(data.confidence)} · ${data.draw_count || 0} 期 · 窗口 ${state.window} · 更新 ${formatBeijing(data.updated_at)}`,
        st?.refresh_ok === false ? "bad" : ""
      );
    }
  } catch (err) {
    setStatus("加载失败：" + err.message + "。请确认 data/*.json 存在且未被伪造。", "bad");
    $("latestDraw").innerHTML = "";
    $("nextPredict").innerHTML = `<p class="warn">无法读取真实数据文件</p>`;
    $("refPicks").innerHTML = `<p class="warn">无法读取真实数据文件</p>`;
    $("betCalc").innerHTML = "";
    $("hotCold").innerHTML = "";
    $("danSha").innerHTML = "";
    $("formGrid").innerHTML = "";
    $("omitTabs").innerHTML = "";
    $("omitTable").innerHTML = "";
    $("trendWrap").innerHTML = "";
    $("drawList").innerHTML = "";
  }
}

async function boot() {
  const hash = location.hash.replace("#", "");
  if (LOTTERIES.some((l) => l.id === hash)) state.current = hash;
  if (![30, 50, 100].includes(state.window)) state.window = 50;

  renderTabs();
  renderWindowBar();

  const copyBtn = $("copyPredictBtn");
  if (copyBtn) {
    copyBtn.onclick = async () => {
      if (!state.lastPredictText) {
        toast("暂无可复制号码");
        return;
      }
      try {
        await navigator.clipboard.writeText(state.lastPredictText);
        toast("已复制预测号码");
      } catch (_) {
        toast("复制失败");
      }
    };
  }

  window.addEventListener("hashchange", () => {
    const id = location.hash.replace("#", "");
    if (id && id !== state.current) selectLottery(id);
  });

  try {
    state.status = await loadJson("data/status.json");
    state.bust = state.status?.updated_at || "";
  } catch (_) {
    state.status = null;
  }
  try {
    state.predictions = await loadJson("data/predictions.json");
  } catch (_) {
    state.predictions = null;
  }

  await renderLottery();
  preloadBoard();
  window.addEventListener("resize", () => {
    const data = state.cache[state.current];
    if (data) drawFreqChart(data, getAnalysis(data));
  });
}

boot();
