# 开奖走势查阅

手机可打开的多彩种开奖走势 / 分析页。数据来自**多个免费公开源交叉核对**，抓不到会提示，**不伪造号码**。

## 本地更新数据

```bash
python scripts/fetch_lottery.py
```

然后用本地静态服务器打开（避免 `file://` 下 fetch 受限）：

```bash
python -m http.server 8080
```

浏览器访问 `http://localhost:8080`。

## 发布到 GitHub Pages

1. 把本仓库推到 GitHub
2. Settings → Pages → Source 选 `Deploy from a branch`，分支 `main`（或 `master`），文件夹 `/ (root)`
3. Actions 会每 6 小时自动抓取更新；也可手动 Run workflow

## 说明

- 不含付费荐号爬取
- 统计参考选号不提高中奖概率
- 购彩请以中国福彩 / 体彩官网为准
