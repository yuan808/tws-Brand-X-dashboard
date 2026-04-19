"""
淘宝热搜词爬虫：调用淘宝 Suggest API
这是唯一合法公开的接口，无需鉴权，稳定可靠
"""
import json
import logging
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# 热词分类规则（与仪表板前端保持一致）
CATEGORY_RULES = {
    "功能需求": ["降噪", "游戏", "运动", "防水", "通话", "低延迟", "高清"],
    "形态词":   ["骨传导", "开放式", "夹耳", "入耳", "平头塞", "真无线"],
    "品牌词":   ["华为", "苹果", "索尼", "三星", "小米", "BOSE", "JBL", "漫步者", "倍思"],
    "价格词":   ["百元", "性价比", "平价", "千元", "旗舰"],
    "配件词":   ["保护套", "硅胶套", "充电仓", "耳帽", "配件"],
    "通用词":   ["新款", "2025", "2026", "推荐", "排行", "评测"],
}


def categorize_word(word: str) -> str:
    for cat, rules in CATEGORY_RULES.items():
        for rule in rules:
            if rule in word:
                return cat
    return "其他"


def fetch_taobao_suggest(keyword: str, max_retry: int = 3) -> list:
    """
    调用淘宝 Suggest API，返回热词列表
    每个元素: {"word": str, "weight": int}
    """
    url = "https://suggest.taobao.com/sug"
    params = {"q": keyword, "code": "utf-8", "callback": "cb"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.taobao.com/",
    }

    for attempt in range(max_retry):
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=10)
            text = resp.text.strip()
            # 去除 JSONP 包装: cb({...})
            m = re.match(r"cb\s*\(\s*(\{.*\})\s*\)", text, re.DOTALL)
            if not m:
                continue
            data = json.loads(m.group(1))
            result = data.get("result", [])
            # result 格式: [["词语", "权重"], ...]
            words = []
            for i, item in enumerate(result[:15]):
                if isinstance(item, list) and len(item) >= 1:
                    words.append({
                        "word": item[0],
                        "weight": int(item[1]) if len(item) > 1 else (15 - i),
                        "rank": i + 1,
                    })
            return words
        except Exception as e:
            logger.warning(f"Taobao suggest [{keyword}] attempt {attempt+1} failed: {e}")
            time.sleep(1)

    return []


def crawl_taobao(keywords: list) -> dict:
    """
    主函数：抓取所有关键词的热搜词，合并去重，分类
    返回适合前端直接使用的结构
    """
    all_words = {}  # word -> {weight, categories, source_keywords}

    for kw in keywords:
        logger.info(f"[Taobao] 抓取热词: {kw}")
        words = fetch_taobao_suggest(kw)
        for item in words:
            w = item["word"]
            if w not in all_words:
                all_words[w] = {
                    "word": w,
                    "weight": item["weight"],
                    "category": categorize_word(w),
                    "source_keywords": [kw],
                    "rank_min": item["rank"],
                }
            else:
                # 合并：取最高权重
                all_words[w]["weight"] = max(all_words[w]["weight"], item["weight"])
                all_words[w]["source_keywords"].append(kw)
                all_words[w]["rank_min"] = min(all_words[w]["rank_min"], item["rank"])
        time.sleep(0.8)  # 温和频率

    # 排序：按权重倒序
    sorted_words = sorted(all_words.values(), key=lambda x: -x["weight"])

    # 分类汇总
    categories = {}
    for item in sorted_words:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    # 统计各类热度占比
    total_weight = sum(x["weight"] for x in sorted_words) or 1
    category_stats = {
        cat: {
            "count": len(words),
            "total_weight": sum(w["weight"] for w in words),
            "pct": round(sum(w["weight"] for w in words) / total_weight * 100, 1),
        }
        for cat, words in categories.items()
    }

    logger.info(f"[Taobao] 共抓取 {len(sorted_words)} 个去重热词")
    return {
        "top_words": sorted_words[:50],      # Top 50 热词
        "categories": categories,
        "category_stats": category_stats,
        "total_words": len(sorted_words),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config_path = Path(__file__).parent.parent / "products_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    data = crawl_taobao(config["taobao_keywords"])
    print(json.dumps(data, ensure_ascii=False, indent=2))
