#!/usr/bin/env python3
"""Fetch important news from RSS/Atom feeds and send a daily email digest."""

from __future__ import annotations

import html
import json
import logging
import os
import re
import smtplib
import ssl
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger("daily-news")
USER_AGENT = "DailyNewsMailer/1.0 (+https://github.com/)"
MAX_FEED_BYTES = 5 * 1024 * 1024
CATEGORY_ORDER = ("政治", "经济", "科技行业", "国际", "日本", "社会")
CATEGORY_CLASSIFICATION_ORDER = ("科技行业", "经济", "政治", "日本", "国际")
CATEGORY_COLORS = {
    "政治": "#7c3aed",
    "经济": "#047857",
    "科技行业": "#0369a1",
    "国际": "#b45309",
    "日本": "#be123c",
    "社会": "#4b5563",
}

CATEGORY_KEYWORDS = {
    "科技行业": (
        "人工智能",
        "大模型",
        "生成式ai",
        "openai",
        "anthropic",
        "github",
        "程序员",
        "软件",
        "开发者",
        "云计算",
        "云服务",
        "芯片",
        "半导体",
        "gpu",
        "数据中心",
        "网络安全",
        "开源",
        "编程",
        "算法",
        "机器人",
        "操作系统",
        "数据库",
        "artificial intelligence",
        "large language model",
        "generative ai",
        "software",
        "developer",
        "cloud computing",
        "semiconductor",
        "chip",
        "cybersecurity",
        "open source",
        "programming",
        "robot",
        "technology",
        "テクノロジー",
        "人工知能",
        "ソフトウェア",
        "半導体",
        "サイバー",
    ),
    "政治": (
        "政治",
        "政府",
        "国会",
        "议会",
        "选举",
        "总统",
        "首相",
        "外交",
        "制裁",
        "峰会",
        "政党",
        "内阁",
        "部长",
        "外长",
        "政策",
        "访华",
        "government",
        "parliament",
        "election",
        "president",
        "prime minister",
        "diplomacy",
        "sanction",
        "cabinet",
        "minister",
        "policy",
        "政府",
        "国会",
        "選挙",
        "大統領",
        "首相",
        "外交",
        "内閣",
    ),
    "经济": (
        "经济",
        "财经",
        "金融",
        "央行",
        "利率",
        "通胀",
        "市场",
        "股市",
        "汇率",
        "贸易",
        "关税",
        "就业",
        "企业",
        "投资",
        "房地产",
        "消费",
        "economy",
        "business",
        "finance",
        "central bank",
        "interest rate",
        "inflation",
        "market",
        "stock",
        "trade",
        "tariff",
        "employment",
        "investment",
        "経済",
        "金融",
        "中央銀行",
        "金利",
        "市場",
        "貿易",
    ),
    "日本": (
        "日本",
        "东京",
        "大阪",
        "日元",
        "日本央行",
        "自民党",
        "japan",
        "tokyo",
        "osaka",
        "yen",
        "日本",
        "東京",
        "大阪",
        "円",
    ),
    "国际": (
        "国际",
        "美国",
        "欧洲",
        "欧盟",
        "俄罗斯",
        "乌克兰",
        "中东",
        "伊朗",
        "以色列",
        "战争",
        "停火",
        "联合国",
        "北约",
        "美伊",
        "伊美",
        "international",
        "united states",
        "europe",
        "russia",
        "ukraine",
        "middle east",
        "iran",
        "israel",
        "war",
        "ceasefire",
        "united nations",
        "nato",
        "アメリカ",
        "イラン",
        "イスラエル",
        "ウクライナ",
        "ロシア",
        "戦争",
        "停戦",
        "国連",
    ),
    "社会": (
        "社会",
        "教育",
        "医疗",
        "健康",
        "气候",
        "能源",
        "灾害",
        "地震",
        "台风",
        "公共安全",
        "热浪",
        "高温",
        "洪水",
        "火灾",
        "heatwave",
        "climate",
        "health",
        "earthquake",
    ),
}

URGENT_KEYWORDS = (
    "earthquake",
    "tsunami",
    "war",
    "invasion",
    "attack",
    "ceasefire",
    "election",
    "president",
    "prime minister",
    "central bank",
    "interest rate",
    "inflation",
    "recession",
    "emergency",
    "sanction",
    "nuclear",
    "地震",
    "海啸",
    "战争",
    "袭击",
    "停火",
    "选举",
    "总统",
    "首相",
    "央行",
    "利率",
    "通胀",
    "紧急",
    "制裁",
    "核",
    "地震",
    "津波",
    "戦争",
    "攻撃",
    "停戦",
    "選挙",
    "大統領",
    "首相",
    "中央銀行",
    "金利",
    "緊急",
    "制裁",
)

IMPORTANT_KEYWORDS = (
    "government",
    "parliament",
    "economy",
    "market",
    "trade",
    "climate",
    "energy",
    "technology",
    "artificial intelligence",
    "ai ",
    "health",
    "outbreak",
    "court",
    "supreme court",
    "政府",
    "国会",
    "经济",
    "市场",
    "贸易",
    "气候",
    "能源",
    "科技",
    "人工智能",
    "疫情",
    "法院",
    "最高法院",
    "政府",
    "国会",
    "経済",
    "市場",
    "貿易",
    "気候",
    "エネルギー",
    "技術",
    "人工知能",
    "感染",
    "裁判所",
)

LOW_PRIORITY_KEYWORDS = (
    "celebrity",
    "fashion",
    "recipe",
    "horoscope",
    "gossip",
    "明星",
    "时尚",
    "食谱",
    "星座",
    "芸能",
    "ファッション",
    "レシピ",
    "占い",
    "world cup",
    "football",
    "soccer",
    "世界杯",
    "足球",
    "w杯",
    "サッカー",
    "baseball",
    "home run",
    "mlb",
    "野球",
    "大リーグ",
    "ホームラン",
)


@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    category: str = "综合"
    language: str = ""
    weight: float = 1.0
    enabled: bool = True


@dataclass
class Article:
    title: str
    url: str
    summary: str
    published: datetime | None
    source: str
    category: str
    language: str = ""
    source_weight: float = 1.0
    score: float = 0.0
    corroborating_sources: list[str] = field(default_factory=list)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数，当前值为 {value!r}") from exc


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def clean_text(value: str | None, limit: int | None = None) -> str:
    if not value:
        return ""
    parser = _HTMLTextExtractor()
    try:
        parser.feed(value)
        text = parser.text()
    except Exception:
        text = value
    text = html.unescape(text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def contains_chinese(value: str, minimum: int = 4) -> bool:
    """Return true for Chinese text while excluding predominantly Japanese text."""
    han_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", value))
    kana_count = len(re.findall(r"[\u3040-\u30ff]", value))
    return han_count >= minimum and kana_count <= max(2, han_count // 8)


def headline_without_source(title: str) -> str:
    return re.sub(r"\s+[-–—|]\s+[^-–—|]{2,40}$", "", title).strip()


def classify_category(article: Article) -> str:
    title = article.title.lower()
    summary = article.summary.lower()
    for category in CATEGORY_CLASSIFICATION_ORDER:
        if any(keyword in title for keyword in CATEGORY_KEYWORDS[category]):
            return category
    if article.category in CATEGORY_ORDER and article.category != "社会":
        return article.category
    for category in CATEGORY_CLASSIFICATION_ORDER:
        if any(keyword in summary for keyword in CATEGORY_KEYWORDS[category]):
            return category
    if article.category in CATEGORY_ORDER:
        return article.category
    return "社会"


def build_chinese_summary(article: Article, limit: int = 180) -> str:
    """Clean an already translated Chinese summary."""
    title = headline_without_source(article.title)
    summary = clean_text(article.summary)
    summary = summary.replace("查看更多相关报道", "").strip()
    summary = summary.replace("在Google 新闻上查看更多头条新闻和观点", "").strip()
    summary = summary.replace("在 Google 新闻上查看更多头条新闻和观点", "").strip()
    summary = re.sub(
        r"See more headlines.*?Google News",
        "",
        summary,
        flags=re.IGNORECASE,
    ).strip()
    for duplicate in (article.title, title):
        if duplicate and summary.startswith(duplicate):
            summary = summary[len(duplicate) :].strip(" -–—|：:")
    summary = clean_text(summary, limit)
    if contains_chinese(summary, minimum=10):
        return summary
    return clean_text(f"这则新闻聚焦“{title}”，详情请点击标题查看原文。", limit)


def prepare_articles(articles: Iterable[Article]) -> list[Article]:
    prepared: list[Article] = []
    for article in articles:
        article.title = clean_text(article.title, 180)
        article.category = classify_category(article)
        prepared.append(article)
    return prepared


def truncate_utf8(value: str, max_bytes: int = 480) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[: max_bytes - 3].decode("utf-8", errors="ignore").rstrip() + "…"


def infer_language(article: Article) -> str:
    if article.language:
        return article.language
    if contains_chinese(article.title):
        return "zh-CN"
    if re.search(r"[\u3040-\u30ff]", article.title):
        return "ja"
    return "en"


def translate_text_mymemory(
    text: str,
    *,
    source_language: str,
    contact_email: str = "",
    timeout: int = 20,
    retries: int = 3,
) -> str:
    text = truncate_utf8(clean_text(text))
    if not text:
        return ""
    if source_language.lower().startswith("zh") and contains_chinese(text):
        return text

    params = {
        "q": text,
        "langpair": f"{source_language}|zh-CN",
        "mt": "1",
    }
    if contact_email:
        params["de"] = contact_email
    url = "https://api.mymemory.translated.net/get?" + urlencode(params)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
            )
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            translated = clean_text(
                payload.get("responseData", {}).get("translatedText", "")
            )
            status = payload.get("responseStatus", 200)
            if status != 200 or not translated:
                details = payload.get("responseDetails") or "翻译 API 返回空结果"
                raise RuntimeError(str(details))
            if not contains_chinese(translated, minimum=2):
                raise RuntimeError("翻译结果不是中文")
            return translated
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(attempt + 1)
    raise RuntimeError(f"MyMemory 翻译失败：{last_error}")


def translate_articles_to_chinese(
    articles: Iterable[Article],
    *,
    contact_email: str = "",
    timeout: int = 20,
) -> list[Article]:
    translated_articles: list[Article] = []
    for article in articles:
        source_language = infer_language(article)
        original_title = headline_without_source(article.title)
        original_summary = clean_text(article.summary, 320)
        article.title = translate_text_mymemory(
            original_title,
            source_language=source_language,
            contact_email=contact_email,
            timeout=timeout,
        )
        if original_summary:
            article.summary = translate_text_mymemory(
                original_summary,
                source_language=source_language,
                contact_email=contact_email,
                timeout=timeout,
            )
        else:
            article.summary = ""
        article.summary = build_chinese_summary(article)
        if not contains_chinese(article.title) or not contains_chinese(article.summary):
            raise RuntimeError(f"《{original_title}》未能生成完整中文内容")
        translated_articles.append(article)
        LOGGER.info("已翻译：%s", article.title)
    return translated_articles


def safe_url(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def direct_child_text(element: ElementTree.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in element:
        if local_name(child.tag) in wanted:
            return "".join(child.itertext()).strip()
    return ""


def atom_link(entry: ElementTree.Element) -> str:
    fallback = ""
    for child in entry:
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "").strip()
        if not href:
            continue
        if child.attrib.get("rel", "alternate") == "alternate":
            return href
        fallback = fallback or href
    return fallback


def parse_feed(data: bytes, source: FeedSource) -> list[Article]:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError(f"{source.name} 返回的内容不是有效 XML") from exc

    entries = [
        element
        for element in root.iter()
        if local_name(element.tag) in {"item", "entry"}
    ]
    articles: list[Article] = []
    for entry in entries:
        is_atom = local_name(entry.tag) == "entry"
        title = clean_text(direct_child_text(entry, "title"), 240)
        link = atom_link(entry) if is_atom else direct_child_text(entry, "link")
        if not link:
            link = direct_child_text(entry, "guid", "id")
        link = safe_url(link)
        summary = clean_text(
            direct_child_text(entry, "description", "summary", "content", "encoded"),
            360,
        )
        published = parse_date(
            direct_child_text(entry, "pubdate", "published", "updated", "date")
        )
        if not title or not link:
            continue
        articles.append(
            Article(
                title=title,
                url=link,
                summary=summary,
                published=published,
                source=source.name,
                category=source.category,
                language=source.language,
                source_weight=source.weight,
            )
        )
    return articles


def fetch_feed(source: FeedSource, timeout: int = 20) -> list[Article]:
    request = Request(
        source.url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        data = response.read(MAX_FEED_BYTES + 1)
    if len(data) > MAX_FEED_BYTES:
        raise ValueError(f"{source.name} 的 Feed 超过 5 MB，已拒绝处理")
    return parse_feed(data, source)


def normalized_title(title: str) -> str:
    value = title.lower()
    value = re.sub(r"\s+[-–—|]\s+[^-–—|]{2,40}$", "", value)
    value = re.sub(r"[\W_]+", "", value, flags=re.UNICODE)
    return value


def title_grams(title: str) -> set[str]:
    normalized = normalized_title(title)
    if len(normalized) < 3:
        return {normalized} if normalized else set()
    return {normalized[index : index + 3] for index in range(len(normalized) - 2)}


def titles_are_similar(left: str, right: str) -> bool:
    left_normalized = normalized_title(left)
    right_normalized = normalized_title(right)
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    shorter, longer = sorted((left_normalized, right_normalized), key=len)
    if len(shorter) >= 12 and shorter in longer:
        return True
    left_grams = title_grams(left)
    right_grams = title_grams(right)
    union = left_grams | right_grams
    if not union:
        return False
    return len(left_grams & right_grams) / len(union) >= 0.58


def score_article(article: Article, now: datetime) -> float:
    text = f"{article.title} {article.summary}".lower()
    score = article.source_weight
    if article.published:
        age_hours = max(0.0, (now - article.published).total_seconds() / 3600)
        if age_hours <= 6:
            score += 4.0
        elif age_hours <= 12:
            score += 3.0
        elif age_hours <= 24:
            score += 2.0
        elif age_hours <= 36:
            score += 1.0
    score += min(6.0, sum(3.0 for keyword in URGENT_KEYWORDS if keyword in text))
    score += min(3.0, sum(1.0 for keyword in IMPORTANT_KEYWORDS if keyword in text))
    score -= min(3.0, sum(1.5 for keyword in LOW_PRIORITY_KEYWORDS if keyword in text))
    return score


def rank_and_deduplicate(
    articles: Iterable[Article],
    *,
    now: datetime,
    lookback_hours: int,
    max_items: int,
    max_selected_per_source: int | None = None,
    max_selected_per_category: int | None = None,
) -> list[Article]:
    candidates: list[Article] = []
    for article in articles:
        if article.published:
            age_hours = (now - article.published).total_seconds() / 3600
            if age_hours > lookback_hours or age_hours < -2:
                continue
        article.score = score_article(article, now)
        candidates.append(article)

    candidates.sort(
        key=lambda item: (
            item.score,
            item.published or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    unique: list[Article] = []
    seen_urls: set[str] = set()
    for article in candidates:
        canonical_url = article.url.split("#", 1)[0]
        if canonical_url in seen_urls:
            continue
        duplicate = next(
            (existing for existing in unique if titles_are_similar(article.title, existing.title)),
            None,
        )
        if duplicate:
            if article.source not in duplicate.corroborating_sources and article.source != duplicate.source:
                duplicate.corroborating_sources.append(article.source)
                duplicate.score += 2.0
            continue
        seen_urls.add(canonical_url)
        unique.append(article)

    unique.sort(
        key=lambda item: (
            item.score,
            item.published or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    selected: list[Article] = []
    selected_by_source: dict[str, int] = {}
    selected_by_category: dict[str, int] = {}

    # First reserve one strong article for every available category.
    for category in CATEGORY_ORDER:
        article = next(
            (
                candidate
                for candidate in unique
                if candidate.category == category
                and candidate not in selected
                and (
                    not max_selected_per_source
                    or selected_by_source.get(candidate.source, 0)
                    < max_selected_per_source
                )
            ),
            None,
        )
        if article is None:
            continue
        selected.append(article)
        selected_by_source[article.source] = selected_by_source.get(article.source, 0) + 1
        selected_by_category[article.category] = 1
        if len(selected) >= max_items:
            return selected

    for article in unique:
        if article in selected:
            continue
        source_count = selected_by_source.get(article.source, 0)
        category_count = selected_by_category.get(article.category, 0)
        if max_selected_per_source and source_count >= max_selected_per_source:
            continue
        if max_selected_per_category and category_count >= max_selected_per_category:
            continue
        selected.append(article)
        selected_by_source[article.source] = source_count + 1
        selected_by_category[article.category] = category_count + 1
        if len(selected) >= max_items:
            break

    if len(selected) < max_items:
        selected_urls = {article.url for article in selected}
        for article in unique:
            if article.url in selected_urls:
                continue
            source_count = selected_by_source.get(article.source, 0)
            if max_selected_per_source and source_count >= max_selected_per_source:
                continue
            selected.append(article)
            selected_urls.add(article.url)
            selected_by_source[article.source] = source_count + 1
            if len(selected) >= max_items:
                break
    return selected


def load_config(path: Path) -> tuple[dict, list[FeedSource]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    settings = data.get("settings", {})
    sources = [
        FeedSource(
            name=item["name"],
            url=item["url"],
            category=item.get("category", "综合"),
            language=item.get("language", ""),
            weight=float(item.get("weight", 1.0)),
            enabled=bool(item.get("enabled", True)),
        )
        for item in data.get("sources", [])
    ]
    enabled = [source for source in sources if source.enabled]
    if not enabled:
        raise ValueError("配置中没有启用的新闻源")
    return settings, enabled


def format_local_time(value: datetime | None, tz: ZoneInfo) -> str:
    if value is None:
        return "时间未提供"
    return value.astimezone(tz).strftime("%m-%d %H:%M")


def build_plain_text(articles: list[Article], now: datetime, tz: ZoneInfo) -> str:
    lines = [
        f"每日重要新闻 · {now.astimezone(tz):%Y-%m-%d}",
        "",
    ]
    index = 1
    for category in CATEGORY_ORDER:
        category_articles = [item for item in articles if item.category == category]
        if not category_articles:
            continue
        lines.extend([f"【{category}】", ""])
        for article in category_articles:
            sources = [article.source, *article.corroborating_sources]
            lines.extend(
                [
                    f"{index}. {article.title}",
                    f"   摘要：{article.summary}",
                    f"   来源：{'、'.join(sources)} · {format_local_time(article.published, tz)}",
                    f"   原文：{article.url}",
                    "",
                ]
            )
            index += 1
    lines.append("本邮件由 GitHub Actions 自动生成。")
    return "\n".join(line for line in lines if line is not None)


def build_html(articles: list[Article], now: datetime, tz: ZoneInfo) -> str:
    sections: list[str] = []
    index = 1
    for category in CATEGORY_ORDER:
        category_articles = [item for item in articles if item.category == category]
        if not category_articles:
            continue
        color = CATEGORY_COLORS[category]
        cards: list[str] = []
        for article in category_articles:
            sources = [article.source, *article.corroborating_sources]
            source_text = "、".join(sources)
            cards.append(
                f"""
            <tr>
              <td style="padding:0 0 14px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                       style="border:1px solid #e7e9ee;border-radius:12px;background:#ffffff;">
                  <tr>
                    <td style="padding:18px 20px;">
                      <div style="font-size:12px;color:#6b7280;margin-bottom:8px;">
                        {index:02d} ·
                        {html.escape(format_local_time(article.published, tz))}
                      </div>
                      <a href="{html.escape(article.url, quote=True)}"
                         style="font-size:18px;line-height:1.45;font-weight:700;color:#111827;text-decoration:none;">
                        {html.escape(article.title)}
                      </a>
                      <p style="margin:10px 0 0;color:#3f4654;line-height:1.65;">
                        <strong>摘要：</strong>{html.escape(article.summary)}
                      </p>
                      <div style="margin-top:12px;font-size:12px;color:#808797;">
                        来源：{html.escape(source_text)}
                      </div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            """
            )
            index += 1
        sections.append(
            f"""
            <tr>
              <td style="padding:12px 4px 10px;">
                <div style="font-size:20px;font-weight:800;color:{color};">
                  {html.escape(category)}
                </div>
              </td>
            </tr>
            {''.join(cards)}
            """
        )

    date_text = now.astimezone(tz).strftime("%Y年%m月%d日")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>每日重要新闻</title>
</head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr>
      <td align="center" style="padding:28px 12px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px;">
          <tr>
            <td style="padding:0 4px 22px;">
              <div style="font-size:13px;color:#687182;">{date_text}</div>
              <h1 style="margin:4px 0 6px;font-size:28px;line-height:1.25;color:#111827;">每日重要新闻</h1>
              <div style="font-size:14px;color:#687182;">从公开新闻源筛选出的 {len(articles)} 条重点内容</div>
            </td>
          </tr>
          {''.join(sections)}
          <tr>
            <td style="padding:12px 4px;color:#9299a8;font-size:12px;text-align:center;">
              本邮件由 GitHub Actions 自动生成 · 点击标题阅读原文
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def parse_recipients(value: str) -> list[str]:
    recipients = [item.strip() for item in re.split(r"[,;]", value) if item.strip()]
    if not recipients:
        raise ValueError("EMAIL_TO 未设置有效的收件人地址")
    if any("\n" in item or "\r" in item for item in recipients):
        raise ValueError("收件人地址包含非法换行符")
    return recipients


def send_email(subject: str, plain: str, rich_html: str) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    port = env_int("SMTP_PORT", 465)
    security = os.getenv("SMTP_SECURITY", "ssl").strip().lower()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender_address = os.getenv("EMAIL_FROM", "").strip() or username
    sender_name = os.getenv("EMAIL_FROM_NAME", "每日重要新闻").strip()
    recipients = parse_recipients(os.getenv("EMAIL_TO", ""))

    missing = [
        name
        for name, value in {
            "SMTP_USERNAME": username,
            "SMTP_PASSWORD": password,
            "EMAIL_FROM/SMTP_USERNAME": sender_address,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"缺少邮件配置：{', '.join(missing)}")
    if security not in {"ssl", "starttls", "plain"}:
        raise ValueError("SMTP_SECURITY 只能是 ssl、starttls 或 plain")

    message = EmailMessage()
    message["Subject"] = subject.replace("\r", " ").replace("\n", " ")
    message["From"] = formataddr((sender_name, sender_address))
    message["To"] = ", ".join(recipients)
    message.set_content(plain)
    message.add_alternative(rich_html, subtype="html")

    context = ssl.create_default_context()
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            if security == "starttls":
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(levelname)s %(message)s",
    )
    root_dir = Path(__file__).resolve().parent.parent
    config_path = Path(
        os.getenv("NEWS_SOURCES_FILE", root_dir / "config" / "news_sources.json")
    )
    settings, sources = load_config(config_path)
    timezone_name = os.getenv("NEWS_TIMEZONE", settings.get("timezone", "Asia/Tokyo"))
    tz = ZoneInfo(timezone_name)
    max_items = env_int("NEWS_MAX_ITEMS", int(settings.get("max_items", 12)))
    lookback_hours = env_int(
        "NEWS_LOOKBACK_HOURS", int(settings.get("lookback_hours", 36))
    )
    max_per_source = env_int(
        "NEWS_MAX_PER_SOURCE", int(settings.get("max_per_source", 20))
    )
    max_selected_per_source = env_int(
        "NEWS_MAX_SELECTED_PER_SOURCE",
        int(settings.get("max_selected_per_source", 3)),
    )
    max_selected_per_category = env_int(
        "NEWS_MAX_SELECTED_PER_CATEGORY",
        int(settings.get("max_selected_per_category", 4)),
    )
    timeout = env_int("NEWS_FETCH_TIMEOUT", 20)
    translation_timeout = env_int("TRANSLATION_TIMEOUT", 20)
    translation_email = os.getenv("TRANSLATION_EMAIL", "").strip()
    now = datetime.now(timezone.utc)

    all_articles: list[Article] = []
    failures: list[str] = []
    for source in sources:
        try:
            fetched = fetch_feed(source, timeout=timeout)[:max_per_source]
            all_articles.extend(fetched)
            LOGGER.info("%s：读取 %d 条", source.name, len(fetched))
        except Exception as exc:
            failures.append(source.name)
            LOGGER.warning("%s：读取失败（%s）", source.name, exc)

    prepared_articles = prepare_articles(all_articles)
    articles = rank_and_deduplicate(
        prepared_articles,
        now=now,
        lookback_hours=lookback_hours,
        max_items=max_items,
        max_selected_per_source=max_selected_per_source,
        max_selected_per_category=max_selected_per_category,
    )
    if not articles:
        raise RuntimeError(
            f"没有找到近 {lookback_hours} 小时内的新闻；失败源：{', '.join(failures) or '无'}"
        )
    articles = translate_articles_to_chinese(
        articles,
        contact_email=translation_email,
        timeout=translation_timeout,
    )

    plain = build_plain_text(articles, now, tz)
    rich_html = build_html(articles, now, tz)
    date_text = now.astimezone(tz).strftime("%Y-%m-%d")
    prefix = os.getenv("EMAIL_SUBJECT_PREFIX", "每日重要新闻").strip()
    subject = f"{prefix}｜{date_text}｜{len(articles)} 条"

    if env_bool("DRY_RUN"):
        output_dir = root_dir / "output"
        output_dir.mkdir(exist_ok=True)
        (output_dir / "preview.txt").write_text(plain, encoding="utf-8")
        (output_dir / "preview.html").write_text(rich_html, encoding="utf-8")
        LOGGER.info("演练完成，未发送邮件。预览已写入 output/preview.html")
        print("\n" + plain)
        return 0

    send_email(subject, plain, rich_html)
    LOGGER.info(
        "邮件发送成功：%d 条新闻%s",
        len(articles),
        f"；读取失败：{', '.join(failures)}" if failures else "",
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        LOGGER.error("%s", error)
        sys.exit(1)
