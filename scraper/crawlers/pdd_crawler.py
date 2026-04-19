"""
拼多多爬虫：通过搜索关键词抓取最低价和销量
策略：Playwright 渲染搜索结果页，取第一屏 TOP3 商品
注意：拼多多无公开 API，完全依赖页面解析
"""
import asyncio
import json
import re
import random
import logging
from pathlib import Path

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]


def parse_sales(text: str) -> str:
    """解析「1万+人付款」→ '10000+'"""
    if not text:
        return None
    text = text.strip()
    m = re.search(r"([\d.]+)\s*万", text)
    if m:
        return f"{int(float(m.group(1)) * 10000)}+"
    m = re.search(r"([\d,]+)", text)
    if m:
        return m.group(1).replace(",", "")
    return text


def parse_price(text: str) -> float:
    """解析价格文本 → float"""
    if not text:
        return None
    m = re.search(r"([\d.]+)", text.replace(",", ""))
    return float(m.group(1)) if m else None


async def crawl_pdd_keyword(keyword: str, brand: str, page) -> dict:
    """
    搜索单个关键词，返回 TOP1 商品的价格和销量
    """
    search_url = f"https://mobile.yangkeduo.com/search_result.html?search_key={keyword}"
    result = {
        "brand": brand,
        "platform": "拼多多",
        "keyword": keyword,
        "min_price": None,
        "sales": None,
        "product_name": None,
    }

    try:
        await page.goto(search_url, wait_until="networkidle", timeout=35000)
        await asyncio.sleep(random.uniform(2.5, 5.0))

        # 等待商品列表出现
        await page.wait_for_selector("[class*='goods'], [class*='item'], [class*='product']", timeout=10000)

        # 提取第一个商品的价格
        # 拼多多移动端价格 selector（以分为单位，需 /100）
        price_els = await page.query_selector_all("[class*='price']")
        prices = []
        for el in price_els[:6]:
            txt = await el.inner_text()
            p = parse_price(txt)
            if p and p > 10:   # 过滤掉运费等小数字
                prices.append(p)
        if prices:
            result["min_price"] = min(prices)

        # 提取销量
        sales_els = await page.query_selector_all("[class*='sale'], [class*='sold'], [class*='count']")
        for el in sales_els[:5]:
            txt = await el.inner_text()
            if "付款" in txt or "已售" in txt or "人" in txt:
                result["sales"] = parse_sales(txt)
                break

        # 提取第一个商品名称
        name_els = await page.query_selector_all("[class*='title'], [class*='name'], [class*='goods-name']")
        for el in name_els[:3]:
            txt = (await el.inner_text()).strip()
            if len(txt) > 5:
                result["product_name"] = txt[:60]
                break

        logger.info(f"[PDD] {brand}: 价格={result['min_price']}, 销量={result['sales']}")

    except Exception as e:
        logger.warning(f"[PDD] {brand} 搜索失败: {e}")

    return result


async def crawl_pdd(products: list) -> list:
    """主函数：爬取所有拼多多关键词"""
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-web-security",
            ],
        )
        context = await browser.new_context(
            user_agent=random.choice(UA_POOL),
            viewport={"width": 390, "height": 844},   # 手机端，反爬更宽松
            locale="zh-CN",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        page = await context.new_page()

        for product in products:
            data = await crawl_pdd_keyword(product["keyword"], product["brand"], page)
            results.append(data)
            await asyncio.sleep(random.uniform(4.0, 8.0))

        await browser.close()

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config_path = Path(__file__).parent.parent / "products_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    data = asyncio.run(crawl_pdd(config["pdd_products"]))
    print(json.dumps(data, ensure_ascii=False, indent=2))
