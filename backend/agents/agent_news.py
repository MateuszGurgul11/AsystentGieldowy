"""
Agent Newsowy — RSS artykuly + wydobywanie tresci top artykulow.
Wynik: data/news_digest.json
"""

import re
import time
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

from .config import RSS_FEEDS, REQUEST_TIMEOUT, save_json

MAX_NEWS_PER_SOURCE = 15
TOP_ARTICLES_TO_FETCH = 5
MAX_ARTICLE_CHARS = 6000
RSS_DELAY = 0.5


def _sanitize(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_article_content(url: str) -> str | None:
    """Pobiera tresc artykulu z URL, zwraca czysty tekst."""
    if not url or not url.startswith("http"):
        return None
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": "MarketAgent/1.0"})
            r.raise_for_status()
            text = _strip_html(r.text)
            return text[:MAX_ARTICLE_CHARS] if len(text) >= 50 else None
    except Exception:
        return None


def fetch_rss_feed(url: str, source_name: str, lang: str) -> list[dict[str, Any]]:
    """Pobiera wpisy z RSS."""
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": "MarketAgent/1.0"})
            r.raise_for_status()
            xml_text = r.text
        feed = feedparser.parse(xml_text)
    except Exception as e:
        print(f"  [RSS] {source_name}: {e}")
        return []

    items = []
    for entry in feed.entries[:MAX_NEWS_PER_SOURCE]:
        title = getattr(entry, "title", None) or ""
        if not title:
            continue
        items.append({
            "title": _sanitize(str(title))[:500],
            "summary": _sanitize(str(getattr(entry, "summary", "") or getattr(entry, "description", "") or ""))[:800],
            "link": str(entry.get("link", ""))[:500],
            "published": str(getattr(entry, "published", "") or getattr(entry, "updated", "") or "")[:80],
            "source": source_name,
            "lang": lang,
        })
    return items


def run() -> dict:
    """Zbiera artykuly RSS i wydobywa tresc najwazniejszych."""
    print("[Agent Newsowy] Start...")
    collected_at = datetime.now(timezone.utc).isoformat()

    all_news: list[dict] = []
    seen_titles: set[str] = set()

    for feed in RSS_FEEDS:
        items = fetch_rss_feed(feed["url"], feed["name"], feed.get("lang", "en"))
        for item in items:
            t = item["title"].lower().strip()
            if t not in seen_titles:
                seen_titles.add(t)
                all_news.append(item)
        print(f"  {feed['name']}: {len(items)} artykulow")
        time.sleep(RSS_DELAY)

    all_news.sort(key=lambda n: n.get("published") or "", reverse=True)

    # Wydobycie tresci top artykulow
    fetched_count = 0
    for article in all_news:
        if fetched_count >= TOP_ARTICLES_TO_FETCH:
            break
        link = article.get("link")
        if link:
            content = fetch_article_content(link)
            if content:
                article["full_content"] = content
                fetched_count += 1
                time.sleep(0.3)

    result = {
        "meta": {
            "collected_at": collected_at,
            "total_articles": len(all_news),
            "articles_with_content": fetched_count,
        },
        "articles": all_news,
    }

    path = save_json(result, "news_digest.json")
    print(f"[Agent Newsowy] Zapisano: {path} ({len(all_news)} artykulow, {fetched_count} z trescia)")
    return result


if __name__ == "__main__":
    run()
