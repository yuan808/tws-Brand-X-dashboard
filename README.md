# TWS 耳机品类 PM 仪表板

## 快速启动（本地预览）

```bash
cd "4 job"
python3 -m http.server 8765
# 浏览器打开 http://localhost:8765/tws_pm_dashboard.html
```

本地模式下仪表板显示 **mock 数据**（顶栏显示"⚠ 演示数据"），
部署到 GitHub Pages 后会自动切换为 🟢 实时数据。

---

## 部署到 GitHub Pages（5 步）

### 第 1 步：建仓库

1. 登录 [github.com](https://github.com)，点击右上角 **New repository**
2. 仓库名建议：`tws-dashboard`（或任意英文名）
3. 选 **Public**（GitHub Pages 免费版必须 Public）
4. 不要勾选 Initialize with README（我们自己有）

### 第 2 步：推送代码

```bash
cd "4 job"
git init
git add .
git commit -m "init: TWS dashboard with scraper"
git remote add origin https://github.com/你的用户名/tws-dashboard.git
git push -u origin main
```

### 第 3 步：开启 GitHub Pages

仓库 → Settings → Pages → Source 选 **GitHub Actions**（不是 Branch）

### 第 4 步：允许 Actions 写入仓库

仓库 → Settings → Actions → General → Workflow permissions  
→ 选 **Read and write permissions** → Save

### 第 5 步：手动触发第一次爬虫

仓库 → Actions → "TWS Dashboard 数据自动更新" → Run workflow → Run  
等待约 5-10 分钟，完成后 `data.json` 会自动提交到仓库。

访问地址：`https://你的用户名.github.io/tws-dashboard/tws_pm_dashboard.html`

---

## 爬虫文件结构

```
4 job/
├── tws_pm_dashboard.html          # 仪表板主文件
├── data.json                      # 爬虫输出（自动生成，勿手动编辑）
├── .github/
│   └── workflows/
│       └── scraper.yml            # GitHub Actions 定时调度
└── scraper/
    ├── products_config.json       # ← 在这里维护要监控的商品 SKU
    ├── requirements.txt           # Python 依赖
    ├── run_all.py                 # 主调度脚本
    └── crawlers/
        ├── jd_crawler.py          # 京东爬虫
        ├── pdd_crawler.py         # 拼多多爬虫
        ├── rss_crawler.py         # 36kr / IT之家 RSS
        └── taobao_crawler.py      # 淘宝热词
```

---

## 添加 / 修改监控商品

编辑 `scraper/products_config.json`：

```json
"jd_products": [
  {
    "brand": "品牌显示名",
    "sku_id": "京东商品ID",      ← 从京东商品页URL里取，如 item.jd.com/100046036924.html
    "name": "商品全称",
    "note": "备注"
  }
]
```

SKU ID 在京东商品 URL 里：`https://item.jd.com/[SKU_ID].html`

---

## 爬虫更新频率

| 触发方式 | 时间 |
|---------|------|
| 自动定时 | 每天 08:00 和 20:00（北京时间） |
| 手动触发 | 仓库 → Actions → Run workflow |
| 部分更新 | Run workflow 时指定 `only` 参数（jd/pdd/rss/taobao） |

---

## 数据说明

| 数据类型 | 来源 | 真实性 |
|---------|------|--------|
| 出货量 / 市占率 | Canalys 2023-2024 | ✅ 真实（2025-2026 为预测） |
| 竞品价格 | 京东价格接口 + 拼多多页面 | ✅ 爬虫实时 |
| 竞品评分 | 京东评论接口 | ✅ 爬虫实时 |
| 行业资讯 | 36kr / IT之家 / 199IT RSS | ✅ 爬虫实时 |
| 淘宝热词 | 淘宝 Suggest API | ✅ 实时 |
| Brand X 财务数据 | — | ⚠ Mock 演示 |

---

## 本地手动运行爬虫

```bash
# 安装依赖
pip install -r scraper/requirements.txt
playwright install chromium

# 全量跑
python scraper/run_all.py

# 只跑 RSS（调试）
python scraper/run_all.py --only rss

# 跳过拼多多（速度快3倍）
python scraper/run_all.py --skip-pdd
```

运行完成后 `data.json` 会出现在项目根目录，刷新本地服务器即可看到实时数据。
