#!/usr/bin/env python3
"""Fetch Chinese lottery draws from multiple free public sources, cross-check, write JSON.

Never invents numbers. On failure, keeps previous successful JSON and records error in status.
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ISSUE_COUNT = 50

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
    url = f"https://datachart.500.com/{path}/history/newinc/history.php?limit=50&start=03001"
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


def build_reference_picks(payload: dict[str, Any]) -> dict[str, Any]:
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

    red_freq: Counter[str] = Counter()
    blue_freq: Counter[str] = Counter()
    for d in draws:
        for n in d.get("red") or []:
            red_freq[n] += 1
        for n in d.get("blue") or []:
            blue_freq[n] += 1

    if digit:
        universe = [str(i) for i in range(0, 10)]
    else:
        universe = [str(i).zfill(2) for i in range(1, red_max + 1)]

    hot_red = [n for n, _ in red_freq.most_common(red_count + 3)]
    cold_red = sorted(universe, key=lambda n: (red_freq.get(n, 0), n))[: red_count + 3]

    pick_red: list[str] = []
    for pool in (hot_red, cold_red):
        for n in pool:
            if n not in pick_red:
                pick_red.append(n)
            if len(pick_red) >= red_count:
                break
        if len(pick_red) >= red_count:
            break
    pick_red = sorted(pick_red[:red_count], key=lambda x: int(x))

    pick_blue: list[str] = []
    if blue_count and blue_max:
        blue_u = [str(i).zfill(2) for i in range(1, blue_max + 1)]
        hot_b = [n for n, _ in blue_freq.most_common(blue_count + 2)]
        cold_b = sorted(blue_u, key=lambda n: (blue_freq.get(n, 0), n))
        for pool in (hot_b, cold_b):
            for n in pool:
                if n not in pick_blue:
                    pick_blue.append(n)
                if len(pick_blue) >= blue_count:
                    break
            if len(pick_blue) >= blue_count:
                break
        pick_blue = sorted(pick_blue[:blue_count], key=lambda x: int(x))

    return {
        "ok": True,
        "message": "基于已核对真实开奖的热号/冷号混合统计，仅供娱乐参考，不提高中奖概率",
        "based_on_issues": len(draws),
        "picks": [{"label": "统计参考一注", "red": pick_red, "blue": pick_blue}],
        "hot_red": hot_red[:10],
        "cold_red": cold_red[:10],
        "hot_blue": [n for n, _ in blue_freq.most_common(6)],
        "cold_blue": (
            sorted(blue_u, key=lambda n: (blue_freq.get(n, 0), n))[:6] if blue_max else []
        ),
    }


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lottery_ids = ["ssq", "dlt", "fc3d", "pl3", "qlc"]
    status: dict[str, Any] = {
        "updated_at": utc_now_iso(),
        "lotteries": {},
        "disclaimer": "开奖数据来自公开免费源交叉核对；统计参考选号非预测。购彩请以官网为准。",
    }

    for lid in lottery_ids:
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
            payload["reference"] = build_reference_picks(payload)
            write_json(path, payload)
            print(
                f"  OK {lid}: draws={payload.get('draw_count')} "
                f"verified={payload.get('verified_count')} confidence={payload.get('confidence')}",
                flush=True,
            )

        status["lotteries"][lid] = {
            "ok": bool(payload.get("ok")),
            "refresh_ok": payload.get("refresh_ok", payload.get("ok")),
            "confidence": payload.get("confidence"),
            "updated_at": payload.get("updated_at"),
            "draw_count": payload.get("draw_count") or len(payload.get("draws") or []),
            "verified_count": payload.get("verified_count"),
            "error": payload.get("error") or payload.get("refresh_error"),
            "notes": payload.get("notes") or [],
        }

    status["ok"] = any(v.get("ok") for v in status["lotteries"].values())
    write_json(DATA_DIR / "status.json", status)
    print(json.dumps({"ok": status["ok"], "lotteries": status["lotteries"]}, ensure_ascii=False, indent=2))
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
