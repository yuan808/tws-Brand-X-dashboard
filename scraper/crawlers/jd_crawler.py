"""
京东爬虫：抓取商品价格、评分、评论数
策略：
  - 价格：直接调用京东价格接口（无需登录，公开可用）
  - 评分/评论数：Playwright 渲染商品详情页提取
"""
import asyncio
import json
import re
import random
import time
import logging
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# 随机 User-Agent 池
UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_jd_price(sku_id: str) -> dict:
    """
    调用京东价格接口（公开无鉴权）
    返回 {"price": 1299.0, "origin_price": 1599.0}
    """
    url = f"https://p.3.cn/prices/mgets?skuIds=J_{sku_id}&type=1"
    headers = {
        "User-Agent": random.choice(UA_POOL),
        "Referer": f"https://item.jd.com/{sku_id}.html",
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data and len(data) > 0:
            item = data[0]
            price = float(item.get("p", 0))           # 现价
            origin = float(item.get("op", price))     # 原价
            return {"price": price, "origin_price": origin}
    except Exception as e:
        logger.warning(f"JD price API failed for {sku_id}: {e}")
    return {"price": None, "origin_price": None}


async def get_jd_detail(sku_id: str, browser) -> dict:
    """
    用 Playwright 渲染京东商品详情页，提取评分和评论数
    """
    url = f"https://item.jd.com/{sku_id}.html"
    result = {"rating": None, "review_count": None, "product_name": None}

    try:
        context = await browser.new_context(
            user_agent=random.choice(UA_POOL),
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = await context.new_page()

        # 注入 stealth 脚本，规避 webdriver 检测
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
        """)

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # 随机等待模拟人工浏览
        await asyncio.sleep(random.uniform(2.0, 4.5))

        # 提取商品名称
        try:
            name_el = await page.query_selector(".sku-name")
            if name_el:
                result["product_name"] = (await name_el.inner_text()).strip()
        except Exception:
            pass

        # 提取评论数（京东评论数在 .count 或 #comment-count）
        try:
            # 先尝试评论数接口
            review_url = (
                f"https://club.jd.com/comment/productCommentSummaries.action"
                f"?referenceIds={sku_id}"
            )
            resp = httpx.get(review_url, headers={"User-Agent": random.choice(UA_POOL)}, timeout=8)
            rdata = resp.json()
            summaries = rdata.get("CommentsCount", [])
            if summaries:
                count_str = str(summaries[0].get("ShowCount", ""))
                result["review_count"] = count_str
                avg_score = summaries[0].get("AverageScore", None)
                if avg_score:
                    result["rating"] = round(float(avg_score), 1)
        except Exception:
            # 降级：从页面提取
            try:
                count_el = await page.query_selector("[class*='comment'] [class*='count'], .J-count")
                if count_el:
                    txt = await count_el.inner_text()
                    m = re.search(r"([\d.]+[万+]*)", txt)
                    if m:
                        result["review_count"] = m.group(1)
            except Exception:
                pass

        await context.close()

    except Exception as e:
        logger.warning(f"JD detail failed for {sku_id}: {e}")

    return result


async def crawl_jd(products: list) -> list:
    """
    主函数：并发爬取所有京东商品，返回结果列表
    """
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )

        for product in products:
            sku_id = product["sku_id"]
            brand = product["brand"]
            logger.info(f"[JD] 爬取: {brand} (SKU: {sku_id})")

            # 1. 价格接口（快速，无需浏览器）
            price_data = get_jd_price(sku_id)

            # 2. 详情页（Playwright）
            detail_data = await get_jd_detail(sku_id, browser)

            results.append({
                "brand": brand,
                "platform": "京东",
                "sku_id": sku_id,
                "product_name": detail_data.get("product_name") or product["name"],
                "price": price_data["price"],
                "origin_price": price_data["origin_price"],
                "rating": detail_data.get("rating"),
                "review_count": detail_data.get("review_count"),
                "url": f"https://item.jd.com/{sku_id}.html",
            })

            # 请求间隔：随机 3-7 秒，规避频率检测
            await asyncio.sleep(random.uniform(3.0, 7.0))

        await browser.close()

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config_path = Path(__file__).parent.parent / "products_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    data = asyncio.run(crawl_jd(config["jd_products"]))
    print(json.dumps(data, ensure_ascii=False, indent=2))
