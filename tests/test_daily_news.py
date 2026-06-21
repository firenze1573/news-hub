from __future__ import annotations

import sys
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from daily_news import (  # noqa: E402
    Article,
    FeedSource,
    build_html,
    build_chinese_summary,
    classify_category,
    contains_chinese,
    parse_feed,
    prepare_articles,
    rank_and_deduplicate,
    send_email,
    titles_are_similar,
    translate_text_mymemory,
)


class DailyNewsTests(unittest.TestCase):
    def test_parse_rss(self) -> None:
        source = FeedSource("Example", "https://example.com/rss", "国际", weight=1.5)
        data = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>Central bank changes interest rates</title>
          <link>https://example.com/story</link>
          <description><![CDATA[<p>A major policy decision.</p>]]></description>
          <pubDate>Sat, 21 Jun 2026 00:00:00 GMT</pubDate>
        </item></channel></rss>"""
        articles = parse_feed(data, source)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].summary, "A major policy decision.")
        self.assertEqual(articles[0].category, "国际")
        self.assertEqual(articles[0].published.tzinfo, timezone.utc)

    def test_parse_atom(self) -> None:
        source = FeedSource("Atom", "https://example.com/feed")
        data = b"""<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>Important update</title>
          <link rel="alternate" href="https://example.com/update" />
          <summary>Details here</summary>
          <updated>2026-06-21T01:02:03Z</updated>
        </entry></feed>"""
        articles = parse_feed(data, source)
        self.assertEqual(articles[0].url, "https://example.com/update")
        self.assertEqual(articles[0].published.hour, 1)

    def test_deduplicates_similar_headlines_and_boosts_score(self) -> None:
        now = datetime(2026, 6, 21, 2, tzinfo=timezone.utc)
        first = Article(
            "Major earthquake strikes coastal city",
            "https://one.example/story",
            "",
            now - timedelta(hours=1),
            "Source One",
            "国际",
        )
        second = Article(
            "Major earthquake strikes coastal city - Source Two",
            "https://two.example/story",
            "",
            now - timedelta(hours=2),
            "Source Two",
            "国际",
        )
        ranked = rank_and_deduplicate(
            [first, second], now=now, lookback_hours=36, max_items=10
        )
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].corroborating_sources, ["Source Two"])
        self.assertGreater(ranked[0].score, 5)

    def test_old_articles_are_filtered(self) -> None:
        now = datetime(2026, 6, 21, tzinfo=timezone.utc)
        article = Article(
            "Old news",
            "https://example.com/old",
            "",
            now - timedelta(hours=50),
            "Example",
            "综合",
        )
        self.assertEqual(
            rank_and_deduplicate(
                [article], now=now, lookback_hours=36, max_items=10
            ),
            [],
        )

    def test_limits_selected_items_from_one_source(self) -> None:
        now = datetime(2026, 6, 21, tzinfo=timezone.utc)
        headlines = [
            "Central bank raises benchmark interest rate",
            "Government announces a new energy policy",
            "Technology company releases new processor",
            "Court issues ruling in major trade dispute",
            "Scientists publish climate change findings",
        ]
        articles = [
            Article(
                headline,
                f"https://example.com/{index}",
                "",
                now - timedelta(minutes=index),
                "Busy Source",
                "综合",
            )
            for index, headline in enumerate(headlines)
        ]
        articles.append(
            Article(
                "Another publisher has an update",
                "https://other.example/story",
                "",
                now,
                "Other Source",
                "国际",
            )
        )
        ranked = rank_and_deduplicate(
            articles,
            now=now,
            lookback_hours=36,
            max_items=5,
            max_selected_per_source=2,
        )
        self.assertEqual(
            sum(article.source == "Busy Source" for article in ranked),
            2,
        )
        self.assertTrue(any(article.source == "Other Source" for article in ranked))

    def test_prefers_category_diversity(self) -> None:
        now = datetime(2026, 6, 21, tzinfo=timezone.utc)
        world_headlines = [
            "Government calls emergency election",
            "Peace talks resume after border conflict",
            "President announces international sanctions",
            "Parliament approves climate treaty",
            "Humanitarian aid reaches coastal region",
        ]
        articles = [
            Article(
                headline,
                f"https://world.example/{index}",
                "",
                now - timedelta(minutes=index),
                f"World Source {index}",
                "国际",
            )
            for index, headline in enumerate(world_headlines)
        ]
        articles.append(
            Article(
                "New processor changes technology market",
                "https://tech.example/story",
                "",
                now - timedelta(hours=1),
                "Tech Source",
                "科技行业",
            )
        )
        ranked = rank_and_deduplicate(
            articles,
            now=now,
            lookback_hours=36,
            max_items=4,
            max_selected_per_category=3,
        )
        self.assertEqual(sum(item.category == "国际" for item in ranked), 3)
        self.assertTrue(any(item.category == "科技行业" for item in ranked))

    def test_title_similarity(self) -> None:
        self.assertTrue(
            titles_are_similar(
                "Global markets fall after rate decision",
                "Global markets fall after rate decision - BBC News",
            )
        )
        self.assertFalse(
            titles_are_similar(
                "Global markets fall after rate decision",
                "New spacecraft reaches Mars orbit",
            )
        )

    def test_chinese_language_filter(self) -> None:
        self.assertTrue(contains_chinese("人工智能行业迎来新的发展机会"))
        self.assertFalse(contains_chinese("Artificial intelligence market update"))
        self.assertFalse(contains_chinese("日本の人工知能市場が拡大している"))

    def test_category_prioritizes_technology_industry(self) -> None:
        article = Article(
            "政府发布人工智能与大模型产业新政策",
            "https://example.com/ai",
            "政策涉及芯片、云计算和软件开发企业。",
            None,
            "科技新闻",
            "政治",
        )
        self.assertEqual(classify_category(article), "科技行业")

    def test_ai_substring_does_not_misclassify_politics(self) -> None:
        article = Article(
            "Bolivian president declares state of emergency",
            "https://example.com/politics",
            "Military units were deployed after anti-government protests.",
            None,
            "World News",
            "国际",
        )
        self.assertEqual(classify_category(article), "政治")

    def test_builds_chinese_summary_fallback(self) -> None:
        article = Article(
            "人工智能公司发布新模型 - 示例媒体",
            "https://example.com/ai",
            "English summary only",
            None,
            "科技新闻",
            "科技行业",
        )
        summary = build_chinese_summary(article)
        self.assertTrue(contains_chinese(summary))
        self.assertIn("详情请点击标题查看原文", summary)

    def test_prepare_articles_keeps_original_languages_and_classifies(self) -> None:
        articles = [
            Article(
                "软件开发行业发布新的人工智能工具",
                "https://example.com/zh",
                "新工具面向开发者和云计算团队。",
                None,
                "科技新闻",
                "科技行业",
            ),
            Article(
                "New software development tool released",
                "https://example.com/en",
                "English summary",
                None,
                "Tech News",
                "科技行业",
            ),
        ]
        prepared = prepare_articles(articles)
        self.assertEqual(len(prepared), 2)
        self.assertEqual(prepared[0].category, "科技行业")
        self.assertEqual(prepared[1].category, "科技行业")

    @patch("daily_news.urlopen")
    def test_mymemory_translation_returns_chinese(self, urlopen) -> None:
        payload = {
            "responseData": {"translatedText": "人工智能市场迎来新的变化"},
            "responseStatus": 200,
        }
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            payload
        ).encode("utf-8")
        translated = translate_text_mymemory(
            "The artificial intelligence market is changing",
            source_language="en",
            contact_email="owner@example.com",
        )
        self.assertEqual(translated, "人工智能市场迎来新的变化")
        request = urlopen.call_args.args[0]
        self.assertIn("langpair=en%7Czh-CN", request.full_url)
        self.assertIn("de=owner%40example.com", request.full_url)

    def test_html_escapes_feed_content(self) -> None:
        now = datetime(2026, 6, 21, tzinfo=timezone.utc)
        article = Article(
            "<script>alert(1)</script> Important",
            "https://example.com/?a=1&b=2",
            "<b>Summary</b>",
            now,
            "Example & Co",
            "科技行业",
        )
        rendered = build_html([article], now, timezone.utc)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("a=1&amp;b=2", rendered)

    @patch("daily_news.smtplib.SMTP_SSL")
    def test_email_from_defaults_to_smtp_username(self, smtp_ssl) -> None:
        smtp = smtp_ssl.return_value.__enter__.return_value
        environment = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "465",
            "SMTP_SECURITY": "ssl",
            "SMTP_USERNAME": "sender@example.com",
            "SMTP_PASSWORD": "secret",
            "EMAIL_TO": "recipient@example.com",
            "EMAIL_FROM": "",
        }
        with patch.dict("os.environ", environment, clear=True):
            send_email("Subject", "Plain", "<p>HTML</p>")
        message = smtp.send_message.call_args.args[0]
        self.assertIn("sender@example.com", message["From"])


if __name__ == "__main__":
    unittest.main()
