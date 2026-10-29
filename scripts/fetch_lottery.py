#!/usr/bin/env python3
"""Fetch Chinese lottery draws from multiple free public sources, cross-check, write JSON.

Never invents numbers. On failure, keeps previous successful JSON and records error in status.
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
try:
    from zoneinfo import ZoneInfo

    BJ: timezone | Any = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    BJ = timezone(timedelta(hours=8), name="Asia/Shanghai")

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ISSUE_COUNT = 100

# weekdays: Mon=0 … Sun=6; None = every day
# ready_hm: earliest Beijing time we expect official results online
DRAW_RULES: dict[str, dict[str, Any]] = {
    "fc3d": {"weekdays": None, "draw_hm": (20, 30), "ready_hm": (20, 40), "need_cross": False},
    "pl3": {"weekdays": None, "draw_hm": (20, 30), "ready_hm": (20, 40), "need_cross": False},
    "ssq": {"weekdays": {1, 3, 6}, "draw_hm": (21, 15), "ready_hm": (21, 30), "need_cross": True},
    "qlc": {"weekdays": {0, 2, 4}, "draw_hm": (21, 15), "ready_hm": (21, 30), "need_cross": True},
    "dlt": {"weekdays": {0, 2, 5}, "draw_hm": (21, 25), "ready_hm": (21, 40), "need_cross": True},
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

META = {
    "ssq": {
        "name": "双色球",
        "schedule": "每周二、四、日约 21:15 开奖（以福彩官网为准）",
        "red_count": 6,
        "blue_count": 1,
        "red_max": 33,
        "blue_max": 16,
    },
    "dlt": {
        "name": "大乐透",
        "schedule": "每周一、三、六约 21:25 开奖（以体彩官网为准）",
        "red_count": 5,
        "blue_count": 2,
        "red_max": 35,
        "blue_max": 12,
    },
    "fc3d": {
        "name": "福彩3D",
        "schedule": "每日约 20:30 开奖（以福彩官网为准）",
        "red_count": 3,
        "blue_count": 0,
        "red_max": 9,
        "blue_max": 0,
        "digit": True,
    },
    "pl3": {
        "name": "排列3",
        "schedule": "每日约 20:30 开奖（以体彩官网为准）",
        "red_count": 3,
        "blue_count": 0,
        "red_max": 9,
        "blue_max": 0,
        "digit": True,
    },
    "qlc": {
        "name": "七乐彩",
        "schedule": "每周一、三、五约 21:15 开奖（以福彩官网为准）",
        "red_count": 7,
        "blue_count": 1,
        "red_max": 30,
        "blue_max": 30,
    },
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url: str, headers: dict[str, str] | None = None, timeout: int = 25) -> bytes:
    h = {"User-Agent": USER_AGENT, "Accept": "application/json,text/html,*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()


def norm_issue(code: str) -> str:
    return re.sub(r"\D", "", str(code or ""))


def issue_keys(code: str) -> set[str]:
    """Match 2026108 <-> 26108 style issue numbers across sources."""
    issue = norm_issue(code)
    keys = {issue}
    if len(issue) >= 5:
        keys.add(issue[-5:])
    if len(issue) == 5:
        keys.add("20" + issue)
    if len(issue) == 7 and issue.startswith("20"):
        keys.add(issue[2:])
    return {k for k in keys if k}


def norm_balls(parts: list[Any], width: int = 2) -> list[str]:
    out: list[str] = []
    for p in parts:
        s = str(p).strip()
        if not s:
            continue
        if s.isdigit():
            out.append(s.zfill(width) if width else s)
        else:
            out.append(s)
    return out


def parse_cwl_from_url(url: str, name: str, source_label: str) -> list[dict[str, Any]]:
    headers = {
        "Referer": "https://www.cwl.gov.cn/",
        "Origin": "https://www.cwl.gov.cn",
    }
    raw = http_get(url, headers=headers)
    data = json.loads(raw.decode("utf-8"))
    rows = data.get("result") or []
    draws: list[dict[str, Any]] = []
    for row in rows:
        issue = norm_issue(row.get("code", ""))
        date = str(row.get("date") or "").split("(")[0].strip()
        red_raw = str(row.get("red") or "")
        blue_raw = str(row.get("blue") or "")
        if name == "fc3d":
            red = norm_balls(red_raw.replace(" ", ",").split(","), width=1)
            blue: list[str] = []
        else:
            red = norm_balls(red_raw.replace(" ", ",").split(","), width=2)
            blue = (
                norm_balls(blue_raw.replace(" ", ",").split(","), width=2) if blue_raw else []
            )
        if not issue or not red:
            continue
        draws.append(
            {
                "issue": issue,
                "date": date,
                "red": red,
                "blue": blue,
                "source": source_label,
            }
        )
    return draws


def parse_cwl(name: str) -> list[dict[str, Any]]:
    api_name = {"ssq": "ssq", "fc3d": "3d", "qlc": "qlc"}[name]
    urls = [
        (
            "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
            f"?name={api_name}&issueCount={ISSUE_COUNT}",
            "cwl.gov.cn",
        ),
        (
            "https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice"
            f"?name={api_name}&issueCount={ISSUE_COUNT}",
            "cwl.gov.cn#legacy",
        ),
    ]
    last_err: Exception | None = None
    for url, label in urls:
        try:
            draws = parse_cwl_from_url(url, name, label)
            if draws:
                return draws
        except Exception as e:  # noqa: BLE001
            last_err = e
    if last_err:
        raise last_err
    return []


def parse_cwl_pair(name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch two CWL endpoints separately for cross-check when 500.com unavailable."""
    api_name = {"ssq": "ssq", "fc3d": "3d", "qlc": "qlc"}[name]
    front = (
        "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
        f"?name={api_name}&issueCount={ISSUE_COUNT}"
    )
    legacy = (
        "https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice"
        f"?name={api_name}&issueCount={ISSUE_COUNT}"
    )
    a = parse_cwl_from_url(front, name, "cwl.gov.cn")
    try:
        b = parse_cwl_from_url(legacy, name, "cwl.gov.cn#legacy")
    except Exception:  # noqa: BLE001
        b = []
    return a, b

def parse_sporttery(game_no: str, kind: str) -> list[dict[str, Any]]:
    url = (
        "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
        f"?gameNo={game_no}&provinceId=0&pageSize={ISSUE_COUNT}&isVerify=1&pageNo=1"
    )
    headers = {
        "Referer": "https://www.lottery.gov.cn/",
        "Origin": "https://www.lottery.gov.cn",
    }
    raw = http_get(url, headers=headers)
    data = json.loads(raw.decode("utf-8"))
    if str(data.get("errorCode")) not in ("0", "0.0", ""):
        raise RuntimeError(f"sporttery error: {data.get('errorMessage') or data}")
    rows = (data.get("value") or {}).get("list") or []
    draws: list[dict[str, Any]] = []
    for row in rows:
        issue = norm_issue(row.get("lotteryDrawNum", ""))
        date = str(row.get("lotteryDrawTime") or "").strip()
        result = str(row.get("lotteryDrawResult") or "").strip()
        parts = [p for p in result.split() if p]
        if kind == "dlt":
            if len(parts) < 7:
                continue
            red = norm_balls(parts[:5], width=2)
            blue = norm_balls(parts[5:7], width=2)
        elif kind == "pl3":
            if len(parts) < 3:
                continue
            red = norm_balls(parts[:3], width=1)
            blue = []
        else:
            continue
        if not issue:
            continue
        draws.append(
            {
                "issue": issue,
                "date": date,
                "red": red,
                "blue": blue,
                "source": "sporttery.cn",
            }
        )
    return draws


def _cell_texts(tr: str) -> list[str]:
    tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.I | re.S)
    return [re.sub(r"<[^>]+>", "", t).strip().replace("\xa0", "") for t in tds]


def _find_issue_idx(texts: list[str]) -> int:
    for i, t in enumerate(texts):
        if re.fullmatch(r"\d{5,7}", t or ""):
            return i
    return -1


def parse_500_ball_game(lottery_id: str) -> list[dict[str, Any]]:
    """Parse 500.com history table for ssq/dlt/qlc."""
    path = {"ssq": "ssq", "dlt": "dlt", "qlc": "qlc"}[lottery_id]
    red_n = {"ssq": 6, "dlt": 5, "qlc": 7}[lottery_id]
    blue_n = {"ssq": 1, "dlt": 2, "qlc": 1}[lottery_id]
    url = f"https://datachart.500.com/{path}/history/newinc/history.php?limit={ISSUE_COUNT}&start=03001"
    html = http_get(url, headers={"Referer": "https://datachart.500.com/"}).decode(
        "utf-8", errors="ignore"
    )
    draws: list[dict[str, Any]] = []
    for tr in re.findall(r"<tr[^>]*class=\"t_tr1\"[^>]*>(.*?)</tr>", html, re.I | re.S):
        texts = _cell_texts(tr)
        idx = _find_issue_idx(texts)
        if idx < 0:
            continue
        issue = norm_issue(texts[idx])
        rest = texts[idx + 1 :]
        date = next((t for t in texts if re.match(r"\d{4}-\d{2}-\d{2}", t or "")), "")

        # QLC often packs balls into one cell: "11 13 19 20 25 28 29 26"
        joined = " ".join(rest)
        spaced = re.findall(r"\b\d{1,2}\b", joined)
        # Prefer contiguous numeric cells after issue
        numeric_cells = [t for t in rest if re.fullmatch(r"\d{1,2}", t or "")]

        if lottery_id == "qlc" and len(numeric_cells) < red_n + blue_n and len(spaced) >= red_n + blue_n:
            nums = spaced[: red_n + blue_n]
            red = norm_balls(nums[:red_n], width=2)
            blue = norm_balls(nums[red_n : red_n + blue_n], width=2)
        elif len(numeric_cells) >= red_n + blue_n:
            red = norm_balls(numeric_cells[:red_n], width=2)
            blue = norm_balls(numeric_cells[red_n : red_n + blue_n], width=2)
        else:
            continue

        if issue and len(red) == red_n and len(blue) == blue_n:
            draws.append(
                {
                    "issue": issue,
                    "date": date,
                    "red": red,
                    "blue": blue,
                    "source": "500.com",
                }
            )
    return draws[:ISSUE_COUNT]


def parse_500(lottery_id: str) -> list[dict[str, Any]]:
    if lottery_id in ("ssq", "dlt", "qlc"):
        return parse_500_ball_game(lottery_id)
    # 3D / PL3 chart endpoints are unstable; skip rather than invent
    raise RuntimeError(f"500.com secondary not available for {lottery_id}")


def index_by_issue(draws: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for d in draws:
        for key in issue_keys(d["issue"]):
            out[key] = d
    return out


def cross_check(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    lottery_id: str,
) -> dict[str, Any]:
    s_map = index_by_issue(secondary)
    confirmed: list[dict[str, Any]] = []
    mismatched: list[str] = []
    primary_only: list[str] = []
    seen: set[str] = set()

    for pd in primary:
        canon = norm_issue(pd["issue"])
        if canon in seen:
            continue
        seen.add(canon)

        sd = None
        for key in issue_keys(canon):
            if key in s_map:
                sd = s_map[key]
                break

        if sd is None:
            primary_only.append(canon)
            item = dict(pd)
            item["issue"] = canon
            item["verified"] = False
            item["sources"] = [pd.get("source", "primary")]
            confirmed.append(item)
            continue

        # Compare balls; allow 3D width differences already normalized
        same = pd["red"] == sd["red"] and pd["blue"] == sd["blue"]
        if same:
            item = dict(pd)
            item["issue"] = canon if len(canon) >= len(norm_issue(sd["issue"])) else norm_issue(sd["issue"])
            if len(norm_issue(sd["issue"])) > len(canon):
                item["issue"] = norm_issue(sd["issue"])
            item["issue"] = max([canon, norm_issue(sd["issue"])], key=len)
            item["verified"] = True
            item["sources"] = sorted({pd.get("source", "a"), sd.get("source", "b")})
            if not item.get("date") and sd.get("date"):
                item["date"] = sd["date"]
            confirmed.append(item)
        else:
            mismatched.append(canon)

    confirmed.sort(key=lambda x: x["issue"], reverse=True)
    verified_count = sum(1 for d in confirmed if d.get("verified"))
    ok = len(confirmed) > 0

    confidence = (
        "cross_verified"
        if verified_count >= max(5, len(confirmed) // 3)
        else ("primary_only" if confirmed else "failed")
    )

    notes: list[str] = []
    if mismatched:
        notes.append(f"号码不一致已丢弃: {', '.join(mismatched[:10])}")
    if primary_only and secondary:
        notes.append(f"仅主源匹配到期号外 {len(primary_only)} 期（未交叉到）")
    if not secondary:
        notes.append("次源抓取失败，仅使用主源（已标注未交叉验证）")
        for d in confirmed:
            d["verified"] = False
        confidence = "primary_only" if confirmed else "failed"
        verified_count = 0

    return {
        "id": lottery_id,
        "name": META[lottery_id]["name"],
        "schedule": META[lottery_id]["schedule"],
        "ok": ok,
        "confidence": confidence,
        "updated_at": utc_now_iso(),
        "draw_count": len(confirmed),
        "verified_count": verified_count,
        "notes": notes,
        "error": None,
        "meta": {
            "red_count": META[lottery_id]["red_count"],
            "blue_count": META[lottery_id]["blue_count"],
            "red_max": META[lottery_id]["red_max"],
            "blue_max": META[lottery_id]["blue_max"],
            "digit": META[lottery_id].get("digit", False),
        },
        "draws": [
            {
                "issue": d["issue"],
                "date": d.get("date") or "",
                "red": d["red"],
                "blue": d["blue"],
                "verified": bool(d.get("verified")),
                "sources": d.get("sources") or [],
            }
            for d in confirmed[:ISSUE_COUNT]
        ],
    }


def load_previous(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_one(lottery_id: str) -> dict[str, Any]:
    errors: list[str] = []
    primary: list[dict[str, Any]] = []
    secondary: list[dict[str, Any]] = []

    try:
        if lottery_id in ("ssq", "fc3d", "qlc"):
            primary = parse_cwl(lottery_id)
        elif lottery_id == "dlt":
            primary = parse_sporttery("85", "dlt")
        elif lottery_id == "pl3":
            primary = parse_sporttery("35", "pl3")
            if primary and any(len(d["red"]) != 3 for d in primary[:3]):
                raise RuntimeError("sporttery gameNo=35 返回非排列3结构")
        else:
            raise ValueError(lottery_id)
    except Exception as e:  # noqa: BLE001
        errors.append(f"primary: {e}")
        primary = []

    try:
        if lottery_id in ("ssq", "dlt", "qlc"):
            secondary = parse_500(lottery_id)
        elif lottery_id == "fc3d":
            # Prefer 500; if unavailable, cross-check two official CWL endpoints
            try:
                secondary = parse_500("fc3d")
            except Exception:
                _a, secondary = parse_cwl_pair("fc3d")
                if not primary:
                    primary = _a
        elif lottery_id == "pl3":
            secondary = []
            errors.append("排列3暂无稳定免费次源，仅体彩主源（不伪造第二源）")
        else:
            secondary = []
    except Exception as e:  # noqa: BLE001
        errors.append(f"secondary: {e}")
        secondary = []

    if not primary and secondary:
        primary, secondary = secondary, []
        errors.append("主源失败，改用次源作为主数据")

    if not primary and not secondary:
        return {
            "id": lottery_id,
            "name": META[lottery_id]["name"],
            "schedule": META[lottery_id]["schedule"],
            "ok": False,
            "confidence": "failed",
            "updated_at": utc_now_iso(),
            "draw_count": 0,
            "verified_count": 0,
            "notes": [],
            "error": "; ".join(errors) or "无可用数据源",
            "meta": {
                "red_count": META[lottery_id]["red_count"],
                "blue_count": META[lottery_id]["blue_count"],
                "red_max": META[lottery_id]["red_max"],
                "blue_max": META[lottery_id]["blue_max"],
                "digit": META[lottery_id].get("digit", False),
            },
            "draws": [],
        }

    result = cross_check(primary, secondary, lottery_id)
    if errors:
        result["notes"] = (result.get("notes") or []) + errors
    return result


def _ball_universe(digit: bool, max_n: int) -> list[str]:
    if digit:
        return [str(i) for i in range(0, 10)]
    return [str(i).zfill(2) for i in range(1, max_n + 1)]


def _omission_stats(
    draws: list[dict[str, Any]], key: str, universe: list[str]
) -> list[dict[str, Any]]:
    """500/17500-style omission: appear, current, avg, max, streak, want_rate."""
    n = len(draws)
    # draws[0] is newest
    last_hit: dict[str, int | None] = {u: None for u in universe}
    gaps: dict[str, list[int]] = {u: [] for u in universe}
    appear: Counter[str] = Counter()
    max_streak: dict[str, int] = {u: 0 for u in universe}
    cur_streak: dict[str, int] = {u: 0 for u in universe}

    # Walk oldest -> newest for gap/streak fidelity
    chronological = list(reversed(draws))
    for idx, d in enumerate(chronological):
        hit = set(d.get(key) or [])
        for u in universe:
            if u in hit:
                appear[u] += 1
                if last_hit[u] is not None:
                    gaps[u].append(idx - int(last_hit[u]) - 1)
                last_hit[u] = idx
                cur_streak[u] += 1
                max_streak[u] = max(max_streak[u], cur_streak[u])
            else:
                cur_streak[u] = 0

    newest_idx = n - 1
    rows: list[dict[str, Any]] = []
    for u in universe:
        if last_hit[u] is None:
            current = n
            avg = float(n)
        else:
            current = newest_idx - int(last_hit[u])
            avg = (sum(gaps[u]) / len(gaps[u])) if gaps[u] else max(current, 1)
        max_miss = max(gaps[u] + [current]) if (gaps[u] or current) else 0
        want = round(current / avg, 2) if avg else 0.0
        rows.append(
            {
                "n": u,
                "appear": appear[u],
                "current": current,
                "avg": round(avg, 1),
                "max": max_miss,
                "max_streak": max_streak[u],
                "want_rate": want,
            }
        )
    return rows


def _digit_position_omission(draws: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Per-position omission for 3D / PL3 (百/十/个)."""
    labels = ["bai", "shi", "ge"]
    out: dict[str, list[dict[str, Any]]] = {}
    universe = [str(i) for i in range(10)]
    for pos, lab in enumerate(labels):
        fake = []
        for d in draws:
            red = d.get("red") or []
            val = red[pos] if pos < len(red) else None
            fake.append({"red": [val] if val is not None else []})
        out[lab] = _omission_stats(fake, "red", universe)
    return out


def _pick_by_score(
    rows: list[dict[str, Any]], count: int, mode: str
) -> list[str]:
    scored = list(rows)
    if mode == "hot":
        scored.sort(key=lambda r: (-r["appear"], r["current"], r["n"]))
    elif mode == "cold":
        scored.sort(key=lambda r: (-r["want_rate"], -r["current"], r["n"]))
    else:  # balanced: prefer mid want_rate + some heat
        scored.sort(
            key=lambda r: (
                -abs(r["want_rate"] - 1.2),
                -r["appear"],
                r["n"],
            )
        )
    picked = [r["n"] for r in scored[: max(count * 2, count)]]
    # diversify a bit for balanced
    if mode == "balanced" and len(scored) >= count:
        hot = [r["n"] for r in sorted(rows, key=lambda r: -r["appear"])[: count]]
        cold = [r["n"] for r in sorted(rows, key=lambda r: -r["want_rate"])[: count]]
        mix: list[str] = []
        for pool in (hot, cold, picked):
            for n in pool:
                if n not in mix:
                    mix.append(n)
                if len(mix) >= count:
                    return sorted(mix[:count], key=lambda x: int(x))
        return sorted(mix[:count], key=lambda x: int(x))
    return sorted(picked[:count], key=lambda x: int(x))


def build_reference_picks(payload: dict[str, Any]) -> dict[str, Any]:
    """Rich stats inspired by 500.com + 17500: omission, want_rate, dan/sha, forms."""
    draws = payload.get("draws") or []
    meta = payload.get("meta") or {}
    if not draws or not payload.get("ok"):
        return {
            "ok": False,
            "message": "无真实历史数据，无法生成参考选号",
            "picks": [],
        }

    digit = bool(meta.get("digit"))
    red_max = int(meta.get("red_max") or 33)
    blue_max = int(meta.get("blue_max") or 0)
    red_count = int(meta.get("red_count") or 6)
    blue_count = int(meta.get("blue_count") or 0)
    window = min(len(draws), 100)
    sample = draws[:window]

    red_u = _ball_universe(digit, red_max)
    # Digit games: treat unordered digit bag for hot/cold; position table separate
    red_rows = _omission_stats(sample, "red", red_u)
    blue_u = _ball_universe(False, blue_max) if blue_max else []
    blue_rows = _omission_stats(sample, "blue", blue_u) if blue_u else []

    hot_red = [r["n"] for r in sorted(red_rows, key=lambda r: -r["appear"])[:10]]
    cold_red = [r["n"] for r in sorted(red_rows, key=lambda r: (-r["want_rate"], -r["current"]))[:10]]
    hot_blue = [r["n"] for r in sorted(blue_rows, key=lambda r: -r["appear"])[:6]] if blue_rows else []
    cold_blue = (
        [r["n"] for r in sorted(blue_rows, key=lambda r: (-r["want_rate"], -r["current"]))[:6]]
        if blue_rows
        else []
    )

    picks = [
        {
            "label": "均衡参考",
            "red": _pick_by_score(red_rows, red_count, "balanced"),
            "blue": _pick_by_score(blue_rows, blue_count, "balanced") if blue_count else [],
        },
        {
            "label": "热号参考",
            "red": _pick_by_score(red_rows, red_count, "hot"),
            "blue": _pick_by_score(blue_rows, blue_count, "hot") if blue_count else [],
        },
        {
            "label": "欲出/冷号参考",
            "red": _pick_by_score(red_rows, red_count, "cold"),
            "blue": _pick_by_score(blue_rows, blue_count, "cold") if blue_count else [],
        },
    ]

    # Dan / sha (定胆杀号) — entertainment shrink, same idea as 17500 articles
    last = sample[0] if sample else {}
    last_red = list(last.get("red") or [])
    neighbors: list[str] = []
    if not digit:
        for n in last_red:
            v = int(n)
            for dlt in (-1, 1):
                x = v + dlt
                if 1 <= x <= red_max:
                    s = str(x).zfill(2)
                    if s not in neighbors and s not in last_red:
                        neighbors.append(s)
    want_sorted = sorted(red_rows, key=lambda r: (-r["want_rate"], -r["current"]))
    dan = []
    for n in last_red:
        if n not in dan:
            dan.append(n)
        if len(dan) >= 2:
            break
    for n in neighbors:
        if n not in dan:
            dan.append(n)
        if len(dan) >= 3:
            break
    for r in want_sorted:
        if r["n"] not in dan and r["want_rate"] >= 1.3:
            dan.append(r["n"])
        if len(dan) >= 3:
            break
    sha = [
        r["n"]
        for r in sorted(red_rows, key=lambda r: (r["appear"], -r["current"]))
        if r["n"] not in dan
    ][:3]

    latest_form: dict[str, Any] = {}
    if digit and len(last_red) >= 3:
        a, b, c = (int(last_red[0]), int(last_red[1]), int(last_red[2]))
        s = a + b + c
        span = max(a, b, c) - min(a, b, c)
        uniq = len({a, b, c})
        gtype = "豹子" if uniq == 1 else ("组三" if uniq == 2 else "组六")
        latest_form = {
            "sum": s,
            "span": span,
            "odd_even": f"{sum(1 for x in (a,b,c) if x % 2)}:{sum(1 for x in (a,b,c) if x % 2 == 0)}",
            "big_small": f"{sum(1 for x in (a,b,c) if x >= 5)}:{sum(1 for x in (a,b,c) if x < 5)}",
            "mod3": f"{a%3}{b%3}{c%3}",
            "group": gtype,
        }
    elif last_red:
        vals = [int(x) for x in last_red]
        odd = sum(1 for x in vals if x % 2)
        mid = (red_max + 1) // 2
        big = sum(1 for x in vals if x > mid)
        z1 = red_max // 3
        z2 = 2 * red_max // 3
        zones = [
            sum(1 for x in vals if x <= z1),
            sum(1 for x in vals if z1 < x <= z2),
            sum(1 for x in vals if x > z2),
        ]
        consec = 0
        sv = sorted(vals)
        for i in range(1, len(sv)):
            if sv[i] == sv[i - 1] + 1:
                consec += 1
        latest_form = {
            "sum": sum(vals),
            "span": max(vals) - min(vals) if vals else 0,
            "odd_even": f"{odd}:{len(vals)-odd}",
            "big_small": f"{big}:{len(vals)-big}",
            "zones": f"{zones[0]}:{zones[1]}:{zones[2]}",
            "consecutive_pairs": consec,
            "repeat_vs_prev": len(set(last_red) & set((sample[1].get("red") or []) if len(sample) > 1 else [])),
        }

    result: dict[str, Any] = {
        "ok": True,
        "message": "综合热冷、遗漏、欲出几率与定胆杀号的统计参考（对齐 500/17500 常用指标），不提高中奖概率",
        "based_on_issues": window,
        "method": "omit+want_rate+dan_sha+form",
        "picks": picks,
        "hot_red": hot_red,
        "cold_red": cold_red,
        "hot_blue": hot_blue,
        "cold_blue": cold_blue,
        "omission_red": red_rows,
        "omission_blue": blue_rows,
        "dan": dan[:3],
        "sha": sha,
        "latest_form": latest_form,
        "windows": [30, 50, 100],
    }
    omission_positions = None
    if digit:
        omission_positions = _digit_position_omission(sample)
        result["omission_positions"] = omission_positions
        dig_pick = []
        for lab in ("bai", "shi", "ge"):
            rows = omission_positions.get(lab) or []
            dig_pick.append(_pick_by_score(rows, 1, "balanced")[0] if rows else "0")
        picks.insert(
            0,
            {"label": "定位均衡", "red": dig_pick, "blue": [], "positional": True},
        )
        result["picks"] = picks

    result["next_prediction"] = _build_next_prediction(
        payload.get("id") or "",
        sample,
        meta,
        red_rows,
        blue_rows,
        dan[:3],
        sha,
        omission_positions,
    )
    return result


def _guess_next_issue(last_issue: str) -> str:
    s = re.sub(r"\D", "", str(last_issue or ""))
    if not s:
        return ""
    try:
        return str(int(s) + 1).zfill(len(s))
    except ValueError:
        return ""


def _score_ball(
    row: dict[str, Any], dan: list[str], last_red: list[str], digit: bool
) -> float:
    s = max(0.0, 2.2 - abs(float(row["want_rate"]) - 1.25)) * 3
    s += min(int(row["appear"]), 12) * 0.15
    if row["n"] in dan:
        s += 2.5
    if row["n"] in last_red:
        s += 1.2
    if not digit:
        for x in last_red:
            if abs(int(x) - int(row["n"])) == 1:
                s += 1.0
                break
    if float(row["want_rate"]) > 2.8 and int(row["appear"]) < 2:
        s -= 1.5
    return s


def _reason_ball(
    n: str,
    rows: list[dict[str, Any]],
    dan: list[str],
    sha: list[str],
    last_red: list[str],
    digit: bool,
) -> str:
    row = next((r for r in rows if r["n"] == n), None)
    if not row:
        return "数据不足"
    bits: list[str] = []
    if n in dan:
        bits.append("定胆池")
    if n in last_red:
        bits.append("上期重号候选")
    if not digit and any(abs(int(x) - int(n)) == 1 for x in last_red):
        bits.append("上期邻号")
    wr = float(row["want_rate"])
    if wr >= 1.5:
        bits.append(f"欲出高({wr})")
    elif wr >= 1.2:
        bits.append(f"欲出偏高({wr})")
    elif wr <= 0.4 and int(row["appear"]) > 0:
        bits.append(f"近期偏热(出现{row['appear']})")
    bits.append(f"遗漏{row['current']}/均{row['avg']}")
    if n in sha:
        bits.append("注意：也曾在杀号池")
    return " · ".join(bits)


def _build_next_prediction(
    lottery_id: str,
    sample: list[dict[str, Any]],
    meta: dict[str, Any],
    red_rows: list[dict[str, Any]],
    blue_rows: list[dict[str, Any]],
    dan: list[str],
    sha: list[str],
    omission_positions: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, Any]:
    digit = bool(meta.get("digit"))
    red_count = int(meta.get("red_count") or 6)
    blue_count = int(meta.get("blue_count") or 0)
    last = sample[0] if sample else {}
    last_red = list(last.get("red") or [])
    reasons: list[dict[str, str]] = []

    if digit and omission_positions:
        pos_name = {"bai": "百位", "shi": "十位", "ge": "个位"}
        red: list[str] = []
        for lab in ("bai", "shi", "ge"):
            rows = list(omission_positions.get(lab) or [])
            rows.sort(key=lambda r: -_score_ball(r, [], [], True))
            pick = rows[0]["n"] if rows else "0"
            red.append(pick)
            row = rows[0] if rows else None
            reasons.append(
                {
                    "n": pick,
                    "area": pos_name[lab],
                    "reason": (
                        f"{pos_name[lab]}：欲出{row['want_rate']}，遗漏{row['current']}/均{row['avg']}，出现{row['appear']}"
                        if row
                        else "定位缺省"
                    ),
                }
            )
    else:
        ranked = [r for r in red_rows if r["n"] not in sha]
        ranked.sort(key=lambda r: -_score_ball(r, dan, last_red, digit))
        ordered: list[str] = []
        for n in dan:
            if n not in ordered and any(r["n"] == n for r in ranked):
                ordered.append(n)
        for r in ranked:
            if r["n"] not in ordered:
                ordered.append(r["n"])
        red = sorted(ordered[:red_count], key=lambda x: int(x))
        for n in red:
            reasons.append(
                {
                    "n": n,
                    "area": "前区",
                    "reason": _reason_ball(n, red_rows, dan, sha, last_red, digit),
                }
            )

    blue: list[str] = []
    if blue_count and blue_rows:
        last_blue = list(last.get("blue") or [])
        ranked_b = sorted(
            blue_rows, key=lambda r: -_score_ball(r, [], last_blue, False)
        )
        blue = sorted([r["n"] for r in ranked_b[:blue_count]], key=lambda x: int(x))
        for n in blue:
            reasons.append(
                {
                    "n": n,
                    "area": "后区",
                    "reason": _reason_ball(n, blue_rows, [], [], last_blue, False),
                }
            )

    return {
        "ok": True,
        "for_issue": _guess_next_issue(str(last.get("issue") or "")),
        "after_issue": last.get("issue") or "",
        "after_date": last.get("date") or "",
        "lottery_id": lottery_id,
        "red": red,
        "blue": blue,
        "reasons": reasons,
        "method": "评分=欲出贴近1.25 + 出现次数 + 定胆/重号/邻号加权；默认避开杀号池。娱乐统计，不提高中奖概率。",
        "based_on_issues": len(sample),
        "disclaimer": "依据历史遗漏与形态加权，非保证开奖结果。",
        "updated_at": utc_now_iso(),
    }


def beijing_now() -> datetime:
    return datetime.now(BJ)


def draws_today(lottery_id: str, now: datetime | None = None) -> bool:
    now = now or beijing_now()
    rule = DRAW_RULES[lottery_id]
    days = rule["weekdays"]
    return days is None or now.weekday() in days


def ready_datetime(lottery_id: str, now: datetime | None = None) -> datetime:
    now = now or beijing_now()
    hh, mm = DRAW_RULES[lottery_id]["ready_hm"]
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


def parse_draw_date(s: str) -> str:
    """Normalize to YYYY-MM-DD when possible."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(s or ""))
    return m.group(1) if m else ""


def latest_draw(payload: dict[str, Any]) -> dict[str, Any] | None:
    draws = payload.get("draws") or []
    return draws[0] if draws else None


def has_today_draw(payload: dict[str, Any], today: str) -> bool:
    d = latest_draw(payload)
    if not d:
        return False
    return parse_draw_date(str(d.get("date") or "")) == today


def accuracy_ok(lottery_id: str, payload: dict[str, Any], *, allow_primary_fallback: bool) -> tuple[bool, str]:
    """Gate: never invent; for ball games prefer multi-source agree on newest."""
    if not payload.get("ok"):
        return False, payload.get("error") or "抓取失败"
    newest = latest_draw(payload)
    if not newest:
        return False, "无开奖记录"
    red = newest.get("red") or []
    blue = newest.get("blue") or []
    meta = META[lottery_id]
    if len(red) != meta["red_count"]:
        return False, f"红球个数异常 {len(red)}"
    if len(blue) != meta["blue_count"]:
        return False, f"蓝球个数异常 {len(blue)}"

    need_cross = bool(DRAW_RULES[lottery_id]["need_cross"])
    if need_cross:
        if newest.get("verified"):
            return True, "最新一期已多源交叉核对"
        if allow_primary_fallback and payload.get("confidence") in (
            "cross_verified",
            "primary_only",
        ):
            return True, "超时后接受单源最新期（已标注，未伪造）"
        return False, "等待次源交叉核对最新一期"
    # digit games: structural check only
    return True, "单源官方数据（结构校验通过）"


def write_predictions_board(lottery_ids: list[str]) -> None:
    board: dict[str, Any] = {
        "updated_at": utc_now_iso(),
        "disclaimer": "统计加权下一期参考号，有依据但非保证；不提高中奖概率。",
        "items": {},
    }
    for lid in lottery_ids:
        path = DATA_DIR / f"{lid}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        ref = payload.get("reference") or {}
        np_ = ref.get("next_prediction")
        if np_ and np_.get("ok"):
            board["items"][lid] = {
                "name": payload.get("name") or META[lid]["name"],
                "for_issue": np_.get("for_issue"),
                "after_issue": np_.get("after_issue"),
                "red": np_.get("red"),
                "blue": np_.get("blue"),
                "reasons": np_.get("reasons"),
                "based_on_issues": np_.get("based_on_issues"),
            }
    write_json(DATA_DIR / "predictions.json", board)


def refresh_one(lid: str) -> dict[str, Any]:
    """Fetch one lottery, keep previous on hard failure, rebuild reference when ok."""
    path = DATA_DIR / f"{lid}.json"
    prev = load_previous(path)
    print(f"Fetching {lid}...", flush=True)
    try:
        payload = fetch_one(lid)
    except Exception as e:  # noqa: BLE001
        payload = {
            "id": lid,
            "name": META[lid]["name"],
            "schedule": META[lid]["schedule"],
            "ok": False,
            "error": str(e),
            "draws": [],
            "updated_at": utc_now_iso(),
            "meta": {
                "red_count": META[lid]["red_count"],
                "blue_count": META[lid]["blue_count"],
                "red_max": META[lid]["red_max"],
                "blue_max": META[lid]["blue_max"],
                "digit": META[lid].get("digit", False),
            },
        }

    if not payload.get("ok") and prev and prev.get("ok") and prev.get("draws"):
        kept = dict(prev)
        kept["refresh_ok"] = False
        kept["refresh_error"] = payload.get("error") or "抓取失败"
        kept["refresh_at"] = utc_now_iso()
        kept["notes"] = (kept.get("notes") or []) + [
            "本次更新失败，页面仍显示上一次成功抓取的真实数据"
        ]
        payload = kept
        write_json(path, payload)
        print(f"  WARN {lid}: keep previous ({payload.get('refresh_error')})", flush=True)
    else:
        payload["refresh_ok"] = bool(payload.get("ok"))
        if payload.get("ok"):
            payload["reference"] = build_reference_picks(payload)
        write_json(path, payload)
        print(
            f"  OK {lid}: draws={payload.get('draw_count')} "
            f"verified={payload.get('verified_count')} confidence={payload.get('confidence')}",
            flush=True,
        )
    return payload


def run_refresh(lottery_ids: list[str] | None = None) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lottery_ids = lottery_ids or ["ssq", "dlt", "fc3d", "pl3", "qlc"]
    status: dict[str, Any] = {
        "updated_at": utc_now_iso(),
        "lotteries": {},
        "disclaimer": "开奖数据来自公开免费源交叉核对；统计参考选号非预测。购彩请以官网为准。",
        "mode": "refresh",
    }
    for lid in lottery_ids:
        payload = refresh_one(lid)
        newest = latest_draw(payload) or {}
        status["lotteries"][lid] = {
            "ok": bool(payload.get("ok")),
            "refresh_ok": payload.get("refresh_ok", payload.get("ok")),
            "confidence": payload.get("confidence"),
            "updated_at": payload.get("updated_at"),
            "draw_count": payload.get("draw_count") or len(payload.get("draws") or []),
            "verified_count": payload.get("verified_count"),
            "latest_issue": newest.get("issue"),
            "latest_date": newest.get("date"),
            "latest_verified": bool(newest.get("verified")),
            "error": payload.get("error") or payload.get("refresh_error"),
            "notes": payload.get("notes") or [],
        }

    status["ok"] = any(v.get("ok") for v in status["lotteries"].values())
    write_json(DATA_DIR / "status.json", status)
    write_predictions_board(lottery_ids)
    return status


def run_post_draw(
    *,
    poll_seconds: int = 180,
    max_minutes: int = 100,
    only: list[str] | None = None,
) -> dict[str, Any]:
    """Poll after expected draw time until today's results are accurate enough."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now0 = beijing_now()
    today = now0.strftime("%Y-%m-%d")
    targets = [lid for lid in (only or list(DRAW_RULES)) if draws_today(lid, now0)]
    # Also include games whose ready window already passed today even if script starts late
    if not targets:
        print(f"[{today}] 今日无待开彩种，改为全量刷新一次", flush=True)
        return run_refresh()

    print(
        f"[{today} {now0.strftime('%H:%M')}] 开奖后同步启动，目标: {', '.join(targets)}",
        flush=True,
    )

    done: dict[str, str] = {}
    deadline = now0 + timedelta(minutes=max_minutes)
    changed = False
    round_i = 0

    while True:
        round_i += 1
        now = beijing_now()
        allow_fallback = now >= deadline
        pending = [lid for lid in targets if lid not in done]

        # Skip games not yet past ready time (unless overdue overall)
        active: list[str] = []
        for lid in pending:
            ready = ready_datetime(lid, now)
            if now >= ready or allow_fallback:
                active.append(lid)
            else:
                print(
                    f"  skip {lid}: 未到公布窗口 {ready.strftime('%H:%M')}（北京时间）",
                    flush=True,
                )

        if active:
            status = run_refresh(active)
            changed = True
            for lid in active:
                path = DATA_DIR / f"{lid}.json"
                payload = load_previous(path) or {}
                if not has_today_draw(payload, today):
                    print(f"  wait {lid}: 尚未出现今日({today})开奖", flush=True)
                    continue
                ok, reason = accuracy_ok(lid, payload, allow_primary_fallback=allow_fallback)
                if ok:
                    done[lid] = reason
                    print(f"  READY {lid}: {reason}", flush=True)
                else:
                    print(f"  wait {lid}: {reason}", flush=True)

        pending = [lid for lid in targets if lid not in done]
        summary = {
            "updated_at": utc_now_iso(),
            "mode": "post_draw",
            "beijing_date": today,
            "targets": targets,
            "ready": done,
            "pending": pending,
            "round": round_i,
            "allow_primary_fallback": allow_fallback,
            "ok": len(pending) == 0,
        }
        # merge into status.json freshness fields
        try:
            st = json.loads((DATA_DIR / "status.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            st = {}
        st["post_draw"] = summary
        st["updated_at"] = utc_now_iso()
        write_json(DATA_DIR / "status.json", st)

        if not pending:
            print("全部目标彩种今日开奖已就绪", flush=True)
            break
        if now >= deadline:
            print(
                f"到达截止时间，仍有未完成: {pending}（已尽量保留已核对数据，不伪造）",
                flush=True,
            )
            # one last refresh with fallback acceptance already applied above
            break

        print(f"第 {round_i} 轮未齐，{poll_seconds}s 后重试…", flush=True)
        time.sleep(max(30, poll_seconds))

    final = run_refresh(list(DRAW_RULES))  # refresh all so non-draw games stay warm
    final["mode"] = "post_draw"
    final["post_draw_ready"] = done
    final["beijing_date"] = today
    write_json(DATA_DIR / "status.json", final)
    print(json.dumps({"ready": done, "ok": final.get("ok")}, ensure_ascii=False, indent=2))
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch & cross-check Chinese lottery draws")
    parser.add_argument(
        "--post-draw",
        action="store_true",
        help="开奖后轮询：等到今日开奖出现且准确性门禁通过再结束",
    )
    parser.add_argument("--poll-seconds", type=int, default=180, help="轮询间隔秒")
    parser.add_argument("--max-minutes", type=int, default=100, help="最长等待分钟")
    parser.add_argument(
        "--only",
        nargs="*",
        choices=list(DRAW_RULES),
        help="仅处理指定彩种",
    )
    args = parser.parse_args(argv)

    if args.post_draw:
        status = run_post_draw(
            poll_seconds=args.poll_seconds,
            max_minutes=args.max_minutes,
            only=args.only,
        )
    else:
        status = run_refresh(args.only)
        print(json.dumps({"ok": status["ok"], "lotteries": status["lotteries"]}, ensure_ascii=False, indent=2))
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
