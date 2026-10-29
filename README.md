# 开奖走势查阅

手机可打开的多彩种开奖走势 / 分析页。数据来自**多个免费公开源交叉核对**，抓不到会提示，**不伪造号码**。

支持：**双色球 · 大乐透 · 福彩3D · 排列3 · 七乐彩**。

分析指标对齐 [500.com 走势图](https://datachart.500.com/) / [17500 遗漏表](https://www.17500.cn/) 常用口径：

- **今日总览**：五彩种最新开奖 + 下一期统计号一屏切换
- 近 30 / 50 / 100 期窗口切换（本地记住）
- 下一期统计预测（每号带依据）+ **一键复制**
- **复式注数估算**（红/蓝选号数 → 注数与金额）
- 出现次数、当前/平均/最大遗漏、最大连出、**欲出几率**
- 定胆 / 杀号（重号·邻号·欲出阈值，娱乐缩号）
- 上期形态；3D/排列3 百十个位遗漏；走势带遗漏值
- 开奖后自动同步（本机任务 + GitHub Actions 云端定时）

线上：`https://mrchenjie.github.io/lottery-charts/`

## 本地更新数据

```bash
python scripts/fetch_lottery.py
```

然后用本地静态服务器打开（避免 `file://` 下 fetch 受限）：

```bash
python -m http.server 8080
```

浏览器访问 `http://localhost:8080`。

## 下一期统计预测

页面顶部有「下一期统计预测」：每个号码都带依据（欲出几率、遗漏、定胆/重号/邻号等），  
并写入 `data/predictions.json`。**有依据 ≠ 能提高中奖概率**，仅供娱乐查阅。

## 自动刷新开奖 + 预测（开奖后立即同步）

按**开奖时间结束后**轮询公开源，**交叉核对通过才视为就绪**（双色球/大乐透/七乐彩要求最新期多源一致；3D/排列3 做结构校验）。失败时保留上一次真实数据，**绝不伪造号码**。

| 任务名 | 北京时间 | 作用 |
|--------|----------|------|
| `LotteryChartsPostDraw2040` | 每天 **20:40** | 3D/排列3 开奖后开始轮询（约每 3 分钟，最长约 100 分钟） |
| `LotteryChartsPostDraw2130` | 每天 **21:30** | 双色球/七乐彩等晚间开奖后再盯 |
| `LotteryChartsPostDraw2145` | 每天 **21:45** | 大乐透开奖后再盯一轮 |
| `LotteryChartsDailyPredict` | 每天 **09:00** | 日间板面刷新 |
| `LotteryChartsAutoUpdate` | 每 **6 小时** | 兜底全量刷新 |

安装 / 重置定时任务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\PC\Projects\lottery-charts\scripts\install_schedules.ps1
```

- 开奖后脚本：`scripts/post_draw_update.ps1` → `python scripts/fetch_lottery.py --post-draw`
- 普通刷新：`scripts/update_and_push.ps1`
- 日志：`%LOCALAPPDATA%\lottery-charts\update.log`

手动立刻（普通）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\PC\Projects\lottery-charts\scripts\update_and_push.ps1
```

手动模拟开奖后轮询：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\PC\Projects\lottery-charts\scripts\post_draw_update.ps1
```

注意：电脑关机时任务不会跑；开机后会按「可用时运行」补跑。要「开奖后马上在平台看到」，尽量保持开奖时段开机，或之后补上 GitHub Actions 云端定时。

## 发布到 GitHub Pages

1. 把本仓库推到 GitHub
2. Settings → Pages → Source 选 `Deploy from a branch`，分支 `main`（或 `master`），文件夹 `/ (root)`
3. Actions 会每 6 小时自动抓取更新；也可手动 Run workflow

## 说明

- 不含付费荐号爬取
- 统计参考选号不提高中奖概率
- 购彩请以中国福彩 / 体彩官网为准
