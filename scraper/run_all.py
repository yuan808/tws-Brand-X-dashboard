"""
主调度脚本：依次运行所有爬虫，聚合输出 data.json
用法：
  python run_all.py              # 全量更新
  python run_all.py --skip-pdd  # 跳过拼多多（调试用）
  python run_all.py --only rss  # 只跑 RSS
"""
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 把 crawlers 目录加入路径
sys.path.insert(0, str(Path(__file__).parent))

from crawlers.jd_crawler import crawl_jd
from crawlers.pdd_crawler import crawl_pdd
from crawlers.rss_crawler import crawl_rss
from crawlers.taobao_crawler import crawl_taobao

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scraper/scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "scraper" / "products_config.json"
OUTPUT_PATH = ROOT / "data.json"   # 仪表板直接读这个文件


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_existing_data() -> dict:
    """加载已有 data.json，用于在某模块失败时保留旧数据"""
    if OUTPUT_PATH.exists():
        try:
            return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def merge_product_data(jd_list: list, pdd_list: list) -> list:
    """
    将京东和拼多多数据按品牌合并为统一结构
    [
      {
        brand, jd_price, jd_rating, jd_review_count, jd_url,
        pdd_min_price, pdd_sales,
        price_diff_pct   // 拼多多比京东便宜多少%
      }
    ]
    """
    jd_map = {item["brand"]: item for item in jd_list}
    pdd_map = {item["brand"]: item for item in pdd_list}

    brands = list({**jd_map, **pdd_map}.keys())
    merged = []

    for brand in brands:
        jd = jd_map.get(brand, {})
        pdd = pdd_map.get(brand, {})

        jd_price = jd.get("price")
        pdd_price = pdd.get("min_price")
        price_diff_pct = None
        if jd_price and pdd_price and jd_price > 0:
            price_diff_pct = round((pdd_price - jd_price) / jd_price * 100, 1)

        merged.append({
            "brand": brand,
            "product_name": jd.get("product_name") or brand,
            "jd_price": jd_price,
            "jd_origin_price": jd.get("origin_price"),
            "jd_rating": jd.get("rating"),
            "jd_review_count": jd.get("review_count"),
            "jd_url": jd.get("url"),
            "pdd_min_price": pdd_price,
            "pdd_sales": pdd.get("sales"),
            "price_diff_pct": price_diff_pct,
        })

    return merged


async def main(skip_pdd=False, only=None):
    config = load_config()
    existing = load_existing_data()
    ts = datetime.now(timezone.utc).isoformat()
    ts_cn = datetime.now().strftime("%Y-%m-%d %H:%M")

    result = {
        "_meta": {
            "updated_at": ts,
            "updated_at_cn": ts_cn,
            "version": "1.0",
        },
        "products": existing.get("products", []),
        "news": existing.get("news", []),
        "taobao": existing.get("taobao", {}),
    }

    # ── 1. 京东爬虫 ──
    if only in (None, "jd"):
        logger.info("=" * 40)
        logger.info("▶ 开始：京东爬虫")
        try:
            t0 = time.time()
            jd_data = await crawl_jd(config["jd_products"])
            logger.info(f"✅ 京东完成，耗时 {time.time()-t0:.1f}s，{len(jd_data)} 条")
        except Exception as e:
            logger.error(f"❌ 京东爬虫失败: {e}")
            jd_data = []
    else:
        jd_data = []

    # ── 2. 拼多多爬虫 ──
    pdd_data = []
    if not skip_pdd and only in (None, "pdd"):
        logger.info("=" * 40)
        logger.info("▶ 开始：拼多多爬虫")
        try:
            t0 = time.time()
            pdd_data = await crawl_pdd(config["pdd_products"])
            logger.info(f"✅ 拼多多完成，耗时 {time.time()-t0:.1f}s，{len(pdd_data)} 条")
        except Exception as e:
            logger.error(f"❌ 拼多多爬虫失败: {e}")

    # ── 合并商品数据 ──
    if jd_data or pdd_data:
        result["products"] = merge_product_data(jd_data, pdd_data)
    else:
        logger.warning("⚠ 商品数据全部失败，保留上次缓存")

    # ── 3. RSS 爬虫 ──
    if only in (None, "rss"):
        logger.info("=" * 40)
        logger.info("▶ 开始：RSS 资讯爬虫")
        try:
            t0 = time.time()
            news_data = crawl_rss(config["rss_sources"])
            logger.info(f"✅ RSS 完成，耗时 {time.time()-t0:.1f}s，{len(news_data)} 条")
            result["news"] = news_data
        except Exception as e:
            logger.error(f"❌ RSS 爬虫失败: {e}")

    # ── 4. 淘宝热词 ──
    if only in (None, "taobao"):
        logger.info("=" * 40)
        logger.info("▶ 开始：淘宝热词爬虫")
        try:
            t0 = time.time()
            taobao_data = crawl_taobao(config["taobao_keywords"])
            logger.info(f"✅ 淘宝热词完成，耗时 {time.time()-t0:.1f}s，{taobao_data['total_words']} 个词")
            result["taobao"] = taobao_data
        except Exception as e:
            logger.error(f"❌ 淘宝热词失败: {e}")

    # ── 写出 data.json ──
    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    logger.info("=" * 40)
    logger.info(f"✅ data.json 已写出 → {OUTPUT_PATH}")
    logger.info(f"   商品数: {len(result['products'])} | 资讯数: {len(result['news'])} | 热词数: {result['taobao'].get('total_words', 0)}")


if __name__ == "__main__":
    skip_pdd = "--skip-pdd" in sys.argv
    only_arg = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only_arg = sys.argv[idx + 1]

    asyncio.run(main(skip_pdd=skip_pdd, only=only_arg))
