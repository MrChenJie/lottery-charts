/**
 * Cross-lottery analysis aligned with 500.com / 17500 indicators:
 * omission, want_rate, dan/sha, form, positional (3D/PL3).
 * Entertainment stats only — does not improve win odds.
 */
(function (global) {
  function universe(meta) {
    if (meta.digit) return Array.from({ length: 10 }, (_, i) => String(i));
    const max = meta.red_max || 33;
    return Array.from({ length: max }, (_, i) => String(i + 1).padStart(2, "0"));
  }

  function blueUniverse(meta) {
    const max = meta.blue_max || 0;
    if (!max) return [];
    return Array.from({ length: max }, (_, i) => String(i + 1).padStart(2, "0"));
  }

  function omissionStats(draws, key, uni) {
    const n = draws.length;
    const lastHit = Object.fromEntries(uni.map((u) => [u, null]));
    const gaps = Object.fromEntries(uni.map((u) => [u, []]));
    const appear = Object.fromEntries(uni.map((u) => [u, 0]));
    const maxStreak = Object.fromEntries(uni.map((u) => [u, 0]));
    const curStreak = Object.fromEntries(uni.map((u) => [u, 0]));

    const chrono = draws.slice().reverse();
    chrono.forEach((d, idx) => {
      const hit = new Set(d[key] || []);
      uni.forEach((u) => {
        if (hit.has(u)) {
          appear[u] += 1;
          if (lastHit[u] != null) gaps[u].push(idx - lastHit[u] - 1);
          lastHit[u] = idx;
          curStreak[u] += 1;
          maxStreak[u] = Math.max(maxStreak[u], curStreak[u]);
        } else {
          curStreak[u] = 0;
        }
      });
    });

    const newest = n - 1;
    return uni.map((u) => {
      let current;
      let avg;
      if (lastHit[u] == null) {
        current = n;
        avg = n;
      } else {
        current = newest - lastHit[u];
        avg = gaps[u].length ? gaps[u].reduce((a, b) => a + b, 0) / gaps[u].length : Math.max(current, 1);
      }
      const maxMiss = Math.max(current, ...(gaps[u].length ? gaps[u] : [0]));
      const want = avg ? Math.round((current / avg) * 100) / 100 : 0;
      return {
        n: u,
        appear: appear[u],
        current,
        avg: Math.round(avg * 10) / 10,
        max: maxMiss,
        max_streak: maxStreak[u],
        want_rate: want,
      };
    });
  }

  function positionOmission(draws) {
    const labels = ["bai", "shi", "ge"];
    const uni = Array.from({ length: 10 }, (_, i) => String(i));
    const out = {};
    labels.forEach((lab, pos) => {
      const fake = draws.map((d) => {
        const red = d.red || [];
        return { red: red[pos] != null ? [red[pos]] : [] };
      });
      out[lab] = omissionStats(fake, "red", uni);
    });
    return out;
  }

  function pickByScore(rows, count, mode) {
    if (!count || !rows.length) return [];
    const scored = rows.slice();
    if (mode === "hot") scored.sort((a, b) => b.appear - a.appear || a.current - b.current);
    else if (mode === "cold")
      scored.sort((a, b) => b.want_rate - a.want_rate || b.current - a.current);
    else {
      const hot = rows
        .slice()
        .sort((a, b) => b.appear - a.appear)
        .map((r) => r.n);
      const cold = rows
        .slice()
        .sort((a, b) => b.want_rate - a.want_rate)
        .map((r) => r.n);
      const mix = [];
      for (const pool of [hot, cold]) {
        for (const n of pool) {
          if (!mix.includes(n)) mix.push(n);
          if (mix.length >= count) return mix.slice(0, count).sort((a, b) => +a - +b);
        }
      }
      return mix.slice(0, count).sort((a, b) => +a - +b);
    }
    return scored
      .slice(0, count)
      .map((r) => r.n)
      .sort((a, b) => +a - +b);
  }

  function latestForm(draws, meta) {
    if (!draws.length) return {};
    const last = draws[0];
    const red = last.red || [];
    if (meta.digit && red.length >= 3) {
      const vals = red.map(Number);
      const uniq = new Set(vals).size;
      return {
        sum: vals.reduce((a, b) => a + b, 0),
        span: Math.max(...vals) - Math.min(...vals),
        odd_even: `${vals.filter((x) => x % 2).length}:${vals.filter((x) => x % 2 === 0).length}`,
        big_small: `${vals.filter((x) => x >= 5).length}:${vals.filter((x) => x < 5).length}`,
        mod3: vals.map((x) => x % 3).join(""),
        group: uniq === 1 ? "豹子" : uniq === 2 ? "组三" : "组六",
      };
    }
    if (!red.length) return {};
    const vals = red.map(Number);
    const redMax = meta.red_max || 33;
    const mid = Math.floor((redMax + 1) / 2);
    const odd = vals.filter((x) => x % 2).length;
    const big = vals.filter((x) => x > mid).length;
    const z1 = Math.floor(redMax / 3);
    const z2 = Math.floor((2 * redMax) / 3);
    const zones = [
      vals.filter((x) => x <= z1).length,
      vals.filter((x) => x > z1 && x <= z2).length,
      vals.filter((x) => x > z2).length,
    ];
    const sv = vals.slice().sort((a, b) => a - b);
    let consec = 0;
    for (let i = 1; i < sv.length; i++) if (sv[i] === sv[i - 1] + 1) consec++;
    const prev = (draws[1] && draws[1].red) || [];
    return {
      sum: vals.reduce((a, b) => a + b, 0),
      span: Math.max(...vals) - Math.min(...vals),
      odd_even: `${odd}:${vals.length - odd}`,
      big_small: `${big}:${vals.length - big}`,
      zones: zones.join(":"),
      consecutive_pairs: consec,
      repeat_vs_prev: red.filter((n) => prev.includes(n)).length,
    };
  }

  function danSha(draws, redRows, meta) {
    const lastRed = (draws[0] && draws[0].red) || [];
    const neighbors = [];
    if (!meta.digit) {
      const max = meta.red_max || 33;
      lastRed.forEach((n) => {
        const v = +n;
        [-1, 1].forEach((d) => {
          const x = v + d;
          if (x >= 1 && x <= max) {
            const s = String(x).padStart(2, "0");
            if (!neighbors.includes(s) && !lastRed.includes(s)) neighbors.push(s);
          }
        });
      });
    }
    const wantSorted = redRows.slice().sort((a, b) => b.want_rate - a.want_rate || b.current - a.current);
    const dan = [];
    lastRed.forEach((n) => {
      if (!dan.includes(n) && dan.length < 2) dan.push(n);
    });
    neighbors.forEach((n) => {
      if (!dan.includes(n) && dan.length < 3) dan.push(n);
    });
    wantSorted.forEach((r) => {
      if (!dan.includes(r.n) && r.want_rate >= 1.3 && dan.length < 3) dan.push(r.n);
    });
    const sha = redRows
      .slice()
      .sort((a, b) => a.appear - b.appear || b.current - a.current)
      .map((r) => r.n)
      .filter((n) => !dan.includes(n))
      .slice(0, 3);
    return { dan: dan.slice(0, 3), sha };
  }

  /** Build miss-matrix for trend table (newest first), like 500.com 带遗漏. */
  function missMatrix(draws, uni, key) {
    // For each draw row (newest first), current miss of each number at that time
    const chrono = draws.slice().reverse();
    const last = Object.fromEntries(uni.map((u) => [u, -1]));
    const byChrono = [];
    chrono.forEach((d, idx) => {
      const hit = new Set(d[key] || []);
      const row = {};
      uni.forEach((u) => {
        if (hit.has(u)) {
          row[u] = 0;
          last[u] = idx;
        } else {
          row[u] = last[u] < 0 ? idx + 1 : idx - last[u];
        }
      });
      byChrono.push(row);
    });
    return byChrono.reverse();
  }

  function guessNextIssue(lastIssue) {
    const s = String(lastIssue || "").replace(/\D/g, "");
    if (!s) return "";
    try {
      const n = BigInt(s) + 1n;
      return n.toString().padStart(s.length, "0");
    } catch (_) {
      return "";
    }
  }

  /** lottery_id → weekday list (0=Sun … 6=Sat). Daily games use null. */
  const DRAW_WEEKDAYS = {
    ssq: [0, 2, 4],
    dlt: [1, 3, 6],
    qlc: [1, 3, 5],
    fc3d: null,
    pl3: null,
  };

  function nextDrawDateHint(lotteryId, lastDateStr) {
    const base = lastDateStr ? new Date(lastDateStr + "T12:00:00") : new Date();
    if (Number.isNaN(base.getTime())) return "";
    const days = DRAW_WEEKDAYS[lotteryId];
    const d = new Date(base);
    for (let i = 1; i <= 8; i++) {
      d.setDate(base.getDate() + i);
      if (days == null || days.includes(d.getDay())) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        const week = ["日", "一", "二", "三", "四", "五", "六"][d.getDay()];
        return `${y}-${m}-${day}（周${week}）`;
      }
    }
    return "";
  }

  function reasonForBall(n, rows, dan, sha, lastRed, meta) {
    const row = rows.find((r) => r.n === n);
    if (!row) return "数据不足";
    const bits = [];
    if (dan.includes(n)) bits.push("定胆池");
    if ((lastRed || []).includes(n)) bits.push("上期重号候选");
    if (!meta.digit) {
      const last = lastRed || [];
      const near = last.some((x) => Math.abs(+x - +n) === 1);
      if (near) bits.push("上期邻号");
    }
    if (row.want_rate >= 1.5) bits.push(`欲出高(${row.want_rate})`);
    else if (row.want_rate >= 1.2) bits.push(`欲出偏高(${row.want_rate})`);
    else if (row.want_rate <= 0.4 && row.appear > 0) bits.push(`近期偏热(出现${row.appear})`);
    bits.push(`遗漏${row.current}/均${row.avg}`);
    if (sha.includes(n)) bits.push("注意：也曾在杀号池");
    return bits.join(" · ");
  }

  function scoreBall(row, dan, lastRed, meta) {
    let s = 0;
    // Prefer mild rebound + not extreme freeze
    s += Math.max(0, 2.2 - Math.abs(row.want_rate - 1.25)) * 3;
    s += Math.min(row.appear, 12) * 0.15;
    if (dan.includes(row.n)) s += 2.5;
    if ((lastRed || []).includes(row.n)) s += 1.2;
    if (!meta.digit && (lastRed || []).some((x) => Math.abs(+x - +row.n) === 1)) s += 1.0;
    // Penalize ultra-cold with no heat at all
    if (row.want_rate > 2.8 && row.appear < 2) s -= 1.5;
    return s;
  }

  function buildNextPrediction(draws, meta, lotteryId, redRows, blueRows, dan, sha, omission_positions) {
    const last = draws[0] || {};
    const lastRed = last.red || [];
    const redCount = meta.red_count || 6;
    const blueCount = meta.blue_count || 0;
    const reasons = [];

    let red = [];
    if (meta.digit && omission_positions) {
      const labels = ["bai", "shi", "ge"];
      const posName = { bai: "百位", shi: "十位", ge: "个位" };
      red = labels.map((lab) => {
        const rows = (omission_positions[lab] || []).slice();
        rows.sort((a, b) => scoreBall(b, [], [], meta) - scoreBall(a, [], [], meta));
        const pick = rows[0]?.n || "0";
        const row = rows[0];
        reasons.push({
          n: pick,
          area: posName[lab],
          reason: row
            ? `${posName[lab]}：欲出${row.want_rate}，遗漏${row.current}/均${row.avg}，出现${row.appear}`
            : "定位缺省",
        });
        return pick;
      });
    } else {
      const ranked = redRows
        .slice()
        .filter((r) => !sha.includes(r.n))
        .sort((a, b) => scoreBall(b, dan, lastRed, meta) - scoreBall(a, dan, lastRed, meta));
      // ensure dan first if available
      const ordered = [];
      dan.forEach((n) => {
        if (!ordered.includes(n) && ranked.some((r) => r.n === n)) ordered.push(n);
      });
      ranked.forEach((r) => {
        if (!ordered.includes(r.n)) ordered.push(r.n);
      });
      red = ordered.slice(0, redCount).sort((a, b) => +a - +b);
      red.forEach((n) => {
        reasons.push({
          n,
          area: "前区",
          reason: reasonForBall(n, redRows, dan, sha, lastRed, meta),
        });
      });
    }

    let blue = [];
    if (blueCount && blueRows.length) {
      const rankedB = blueRows
        .slice()
        .sort((a, b) => scoreBall(b, [], last.blue || [], meta) - scoreBall(a, [], last.blue || [], meta));
      blue = rankedB
        .slice(0, blueCount)
        .map((r) => r.n)
        .sort((a, b) => +a - +b);
      blue.forEach((n) => {
        reasons.push({
          n,
          area: "后区",
          reason: reasonForBall(n, blueRows, [], [], last.blue || [], meta),
        });
      });
    }

    return {
      ok: true,
      for_issue: guessNextIssue(last.issue),
      after_issue: last.issue || "",
      after_date: last.date || "",
      next_draw_hint: nextDrawDateHint(lotteryId, last.date),
      red,
      blue,
      reasons,
      method:
        "评分=欲出贴近1.25 + 出现次数 + 定胆/重号/邻号加权；默认避开杀号池。娱乐统计，不提高中奖概率。",
      based_on_issues: draws.length,
      disclaimer: "依据历史遗漏与形态加权，非保证开奖结果。",
    };
  }

  function analyze(drawsAll, meta, windowSize, lotteryId) {
    const w = Math.min(windowSize || 50, drawsAll.length);
    const draws = drawsAll.slice(0, w);
    if (!draws.length) {
      return { ok: false, message: "无真实历史数据" };
    }
    const redU = universe(meta);
    const blueU = blueUniverse(meta);
    const redRows = omissionStats(draws, "red", redU);
    const blueRows = blueU.length ? omissionStats(draws, "blue", blueU) : [];
    const redCount = meta.red_count || 6;
    const blueCount = meta.blue_count || 0;
    const { dan, sha } = danSha(draws, redRows, meta);

    const picks = [
      {
        label: "均衡参考",
        red: pickByScore(redRows, redCount, "balanced"),
        blue: pickByScore(blueRows, blueCount, "balanced"),
      },
      {
        label: "热号参考",
        red: pickByScore(redRows, redCount, "hot"),
        blue: pickByScore(blueRows, blueCount, "hot"),
      },
      {
        label: "欲出/冷号参考",
        red: pickByScore(redRows, redCount, "cold"),
        blue: pickByScore(blueRows, blueCount, "cold"),
      },
    ];

    let omission_positions = null;
    if (meta.digit) {
      omission_positions = positionOmission(draws);
      const dig = ["bai", "shi", "ge"].map((lab) => {
        const rows = omission_positions[lab] || [];
        return pickByScore(rows, 1, "balanced")[0] || "0";
      });
      picks.unshift({ label: "定位均衡", red: dig, blue: [], positional: true });
    }

    const next = buildNextPrediction(
      draws,
      meta,
      lotteryId || "",
      redRows,
      blueRows,
      dan,
      sha,
      omission_positions
    );

    return {
      ok: true,
      based_on_issues: w,
      message:
        "综合热冷、遗漏、欲出几率与定胆杀号（对齐 500.com / 17500 常用指标），仅供娱乐，不提高中奖概率",
      picks,
      next_prediction: next,
      hot_red: redRows
        .slice()
        .sort((a, b) => b.appear - a.appear)
        .slice(0, 10)
        .map((r) => r.n),
      cold_red: redRows
        .slice()
        .sort((a, b) => b.want_rate - a.want_rate || b.current - a.current)
        .slice(0, 10)
        .map((r) => r.n),
      hot_blue: blueRows
        .slice()
        .sort((a, b) => b.appear - a.appear)
        .slice(0, 6)
        .map((r) => r.n),
      cold_blue: blueRows
        .slice()
        .sort((a, b) => b.want_rate - a.want_rate || b.current - a.current)
        .slice(0, 6)
        .map((r) => r.n),
      omission_red: redRows,
      omission_blue: blueRows,
      omission_positions,
      dan,
      sha,
      latest_form: latestForm(draws, meta),
      miss_red: missMatrix(draws, redU, "red"),
      miss_blue: blueU.length ? missMatrix(draws, blueU, "blue") : [],
      red_universe: redU,
      blue_universe: blueU,
    };
  }

  global.LotteryAnalysis = { analyze, universe, blueUniverse, buildNextPrediction };
})(typeof window !== "undefined" ? window : globalThis);
