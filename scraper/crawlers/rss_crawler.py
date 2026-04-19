"""
RSS 资讯爬虫：解析 36kr / IT之家 / 199IT 的 RSS Feed
完全不需要反爬，直接解析 XML，稳定可靠
"""
import json
import re
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (compatible; TWS-Dashboard-Bot/1.0)"

# RSS 命名空间
NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
}


def fetch_rss(url: str, timeout: int = 15) -> str | None:
    """拉取 RSS XML 内容"""
    try:
        resp = httpx.get(url, headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning(f"RSS fetch failed [{url}]: {e}")
        return None


def parse_rss(xml_text: str, source_name: str, keywords: list, max_items: int = 20) -> list:
    """
    解析 RSS XML，过滤包含关键词的条目
    返回标准化新闻列表
    """
    items = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as e:
        logger.warning(f"RSS parse error [{source_name}]: {e}")
        return items

    # 兼容 RSS 2.0 和 Atom
    channel = root.find("channel")
    entries = []
    if channel is not None:
        entries = channel.findall("item")
    else:
        # Atom format
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")

    for entry in entries:
        if len(items) >= max_items:
            break

        # 提取标题
        title_el = (
            entry.find("title") or
            entry.find("{http://www.w3.org/2005/Atom}title")
        )
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        # 提取链接
        link_el = (
            entry.find("link") or
            entry.find("{http://www.w3.org/2005/Atom}link")
        )
        if link_el is not None:
            link = link_el.text or link_el.get("href", "")
        else:
            link = ""

        # 提取描述/摘要
        desc_el = (
            entry.find("description") or
            entry.find("summary") or
            entry.find("{http://www.w3.org/2005/Atom}summary") or
            entry.find("{http://www.w3.org/2005/Atom}content")
        )
        description = ""
        if desc_el is not None and desc_el.text:
            # 去除 HTML 标签
            description = re.sub(r"<[^>]+>", "", desc_el.text).strip()
            description = description[:200]  # 截断到200字

        # 提取发布时间
        pub_el = (
            entry.find("pubDate") or
            entry.find("dc:date", NS) or
            entry.find("{http://www.w3.org/2005/Atom}published") or
            entry.find("{http://www.w3.org/2005/Atom}updated")
        )
        pub_date = pub_el.text.strip() if pub_el is not None and pub_el.text else ""

        # 关键词过滤（标题或描述包含任意关键词）
        combined = (title + " " + description).lower()
        matched_kw = [kw for kw in keywords if kw.lower() in combined]
        if not matched_kw:
            continue

        # 判断影响类别
        impact = classify_impact(title + description)

        items.append({
            "source": source_name,
            "title": title,
            "summary": description[:120] + ("..." if len(description) > 120 else ""),
            "url": link.strip(),
            "pub_date": pub_date,
            "matched_keywords": matched_kw[:3],
            "impact": impact,
        })

    logger.info(f"[RSS] {source_name}: 抓到 {len(items)} 条相关资讯")
    return items


def classify_impact(text: str) -> str:
    """
    简单规则分类资讯影响级别
    返回: "高" / "中" / "低"
    """
    high_words = ["发布", "新品", "上市", "降价", "召回", "供应链", "缺货", "断供", "涨价", "收购", "合并"]
    mid_words = ["专利", "合作", "融资", "销量", "市占", "出货", "评测", "测评"]

    for w in high_words:
        if w in text:
            return "高"
    for w in mid_words:
        if w in text:
            return "中"
    return "低"


def crawl_rss(sources: list) -> list:
    """主函数：爬取所有 RSS 源，合并去重，按时间倒序"""
    all_items = []

    for source in sources:
        logger.info(f"[RSS] 拉取: {source['name']} ({source['url']})")
        xml = fetch_rss(source["url"])
        if not xml:
            continue
        items = parse_rss(xml, source["name"], source["keywords"])
        all_items.extend(items)

    # 按来源去重（同标题）
    seen_titles = set()
    unique = []
    for item in all_items:
        key = item["title"][:30]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(item)

    # 最多返回 30 条
    return unique[:30]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config_path = Path(__file__).parent.parent / "products_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    data = crawl_rss(config["rss_sources"])
    print(json.dumps(data, ensure_ascii=False, indent=2))
