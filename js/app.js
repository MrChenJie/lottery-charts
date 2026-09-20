const LOTTERIES = [
  { id: "ssq", label: "双色球" },
  { id: "dlt", label: "大乐透" },
  { id: "fc3d", label: "福彩3D" },
  { id: "pl3", label: "排列3" },
  { id: "qlc", label: "七乐彩" },
];

const state = {
  current: "ssq",
  cache: {},
  status: null,
};

function $(id) {
  return document.getElementById(id);
}

function ballHtml(n, color) {
  return `<span class="ball ${color}">${n}</span>`;
}

function ballsHtml(red, blue) {
  const r = (red || []).map((n) => ballHtml(n, "red")).join("");
  const b = (blue || []).map((n) => ballHtml(n, "blue")).join("");
  return r + b;
}

async function loadJson(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} HTTP ${res.status}`);
  return res.json();
}

function setStatus(text, kind) {
  const el = $("statusBar");
  el.textContent = text;
  el.className = "status" + (kind ? ` ${kind}` : "");
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
    btn.addEventListener("click", () => {
      state.current = btn.dataset.id;
      renderTabs();
      renderLottery();
    });
  });
}

function confidenceLabel(c) {
  if (c === "cross_verified") return "多源交叉核对";
  if (c === "primary_only") return "单源（未完全交叉）";
  return "未知";
}

function renderLatest(data) {
  const title = $("lotteryTitle");
  const schedule = $("scheduleText");
  const latest = $("latestDraw");
  title.textContent = data.name || state.current;
  schedule.textContent = data.schedule || "";

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
  latest.innerHTML = `
    <div class="meta-line">第 ${d.issue} 期 · ${d.date || "日期未知"} ${badge}</div>
    <div>${ballsHtml(d.red, d.blue)}</div>
  `;
}

function renderReference(data) {
  const box = $("refPicks");
  const chips = $("hotCold");
  const ref = data.reference;
  if (!ref || !ref.ok) {
    box.innerHTML = `<p class="muted">${(ref && ref.message) || "暂无参考选号"}</p>`;
    chips.innerHTML = "";
    return;
  }
  box.innerHTML = (ref.picks || [])
    .map(
      (p) => `
      <div class="ref-pick">
        <span class="muted">${p.label}</span>
        ${ballsHtml(p.red, p.blue)}
      </div>
      <p class="muted">${ref.message}（基于 ${ref.based_on_issues} 期）</p>
    `
    )
    .join("");

  const parts = [];
  if (ref.hot_red?.length) {
    parts.push(
      `<span class="chip"><strong>热号</strong> ${ref.hot_red.join(" ")}</span>`
    );
  }
  if (ref.cold_red?.length) {
    parts.push(
      `<span class="chip"><strong>冷号</strong> ${ref.cold_red.join(" ")}</span>`
    );
  }
  if (ref.hot_blue?.length) {
    parts.push(
      `<span class="chip"><strong>蓝热</strong> ${ref.hot_blue.join(" ")}</span>`
    );
  }
  if (ref.cold_blue?.length) {
    parts.push(
      `<span class="chip"><strong>蓝冷</strong> ${ref.cold_blue.join(" ")}</span>`
    );
  }
  chips.innerHTML = parts.join("");
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

function drawFreqChart(data) {
  const canvas = $("freqChart");
  const ctx = canvas.getContext("2d");
  const draws = (data.draws || []).slice(0, 30);
  const meta = data.meta || {};
  const digit = !!meta.digit;
  const redMax = meta.red_max || 33;
  const labels = digit
    ? Array.from({ length: 10 }, (_, i) => String(i))
    : Array.from({ length: redMax }, (_, i) => String(i + 1).padStart(2, "0"));
  const freq = freqMap(draws, "red");
  const values = labels.map((l) => freq[l] || 0);
  const maxV = Math.max(1, ...values);

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

  values.forEach((v, i) => {
    const h = (v / maxV) * (plotH - 2);
    const x = padL + i * barW + barW * 0.15;
    const y = padT + plotH - h;
    ctx.fillStyle = "#c62828";
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

function renderTrend(data) {
  const wrap = $("trendWrap");
  const draws = (data.draws || []).slice(0, 20);
  const meta = data.meta || {};
  if (!draws.length) {
    wrap.innerHTML = `<p class="muted" style="padding:0.6rem">暂无走势数据</p>`;
    return;
  }

  const digit = !!meta.digit;
  const redMax = meta.red_max || 33;
  const blueMax = meta.blue_max || 0;
  const redNums = digit
    ? Array.from({ length: 10 }, (_, i) => String(i))
    : Array.from({ length: redMax }, (_, i) => String(i + 1).padStart(2, "0"));
  const blueNums =
    blueMax > 0
      ? Array.from({ length: blueMax }, (_, i) => String(i + 1).padStart(2, "0"))
      : [];

  let head =
    `<tr><th class="issue">期号</th>` +
    redNums.map((n) => `<th>${n}</th>`).join("") +
    (blueNums.length ? `<th>|</th>` + blueNums.map((n) => `<th>${n}</th>`).join("") : "") +
    `</tr>`;

  const body = draws
    .map((d) => {
      const redSet = new Set(d.red || []);
      const blueSet = new Set(d.blue || []);
      const redCells = redNums
        .map((n) =>
          redSet.has(n)
            ? `<td><span class="hit-red">${n}</span></td>`
            : `<td class="miss">·</td>`
        )
        .join("");
      const blueCells = blueNums
        .map((n) =>
          blueSet.has(n)
            ? `<td><span class="hit-blue">${n}</span></td>`
            : `<td class="miss">·</td>`
        )
        .join("");
      return `<tr><td class="issue">${d.issue.slice(-5)}</td>${redCells}${
        blueNums.length ? `<td>·</td>${blueCells}` : ""
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
  if (data.updated_at) notes.push("数据时间：" + data.updated_at);
  if (data.refresh_ok === false) notes.push("最近刷新失败：" + (data.refresh_error || ""));
  if (data.notes?.length) notes.push(...data.notes);
  if (data.error) notes.push("错误：" + data.error);
  $("notesText").textContent = notes.join(" ｜ ");
}

async function ensureData(id) {
  if (state.cache[id]) return state.cache[id];
  const data = await loadJson(`data/${id}.json`);
  state.cache[id] = data;
  return data;
}

async function renderLottery() {
  try {
    const data = await ensureData(state.current);
    renderLatest(data);
    renderReference(data);
    drawFreqChart(data);
    renderTrend(data);
    renderDrawList(data);
    renderNotes(data);

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
        `已加载 ${data.name}：多源交叉核对 ${data.verified_count || 0}/${data.draw_count || 0} 期 · 更新 ${data.updated_at || ""}`,
        "ok"
      );
    } else {
      setStatus(
        `已加载 ${data.name}：${confidenceLabel(data.confidence)} · ${data.draw_count || 0} 期 · 更新 ${data.updated_at || ""}`,
        st?.refresh_ok === false ? "bad" : ""
      );
    }
  } catch (err) {
    setStatus("加载失败：" + err.message + "。请确认 data/*.json 存在且未被伪造。", "bad");
    $("latestDraw").innerHTML = "";
    $("refPicks").innerHTML = `<p class="warn">无法读取真实数据文件</p>`;
    $("hotCold").innerHTML = "";
    $("trendWrap").innerHTML = "";
    $("drawList").innerHTML = "";
  }
}

async function boot() {
  renderTabs();
  try {
    state.status = await loadJson("data/status.json");
  } catch (_) {
    state.status = null;
  }
  await renderLottery();
  window.addEventListener("resize", () => {
    const data = state.cache[state.current];
    if (data) drawFreqChart(data);
  });
}

boot();
