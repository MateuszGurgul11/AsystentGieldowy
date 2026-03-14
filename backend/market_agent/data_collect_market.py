"""
Agent danych decyzyjnych: świeże artykuły (RSS) + opcjonalnie posty z Twittera.

Źródła:
- RSS: CoinDesk, CoinTelegraph, The Block (bez kluczy API).
- Twitter: wymaga TWITTER_BEARER_TOKEN (developer.twitter.com, Free tier: odczyt z ostatnich 7 dni).

Wynik: market_intel.json z polami news[] i twitter[] (daty, źródła, linki).
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# Konfiguracja
try:
    from .config import RSS_FEEDS, TWITTER_BEARER_TOKEN, TWITTER_USERNAMES
except ImportError:
    from config import RSS_FEEDS, TWITTER_BEARER_TOKEN, TWITTER_USERNAMES

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "market_intel.json"
REQUEST_TIMEOUT = 25
MAX_NEWS_PER_SOURCE = 15
MAX_TWEETS_PER_USER = 5
RSS_DELAY = 0.5


def _sanitize(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]


def fetch_rss_feed(url: str, source_name: str, lang: str) -> list[dict[str, Any]]:
    """Pobiera wpisy z jednego RSS (feedparser). Zwraca listę {title, summary, link, published_iso, source}."""
    try:
        import feedparser
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": "MarketAgent/1.0"})
            r.raise_for_status()
            xml_text = r.text
        feed = feedparser.parse(xml_text)
    except Exception as e:
        print(f"[RSS] {source_name} ({url}): {e}")
        return []

    items = []
    for entry in feed.entries[:MAX_NEWS_PER_SOURCE]:
        title = getattr(entry, "title", None) or ""
        link = entry.get("link", "") or ""
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        published = getattr(entry, "published", "") or getattr(entry, "updated", "") or ""
        if not title:
            continue
        items.append({
            "title": _sanitize(str(title))[:500],
            "summary": _sanitize(str(summary))[:800],
            "link": str(link)[:500] if link else "",
            "published_iso": str(published)[:80],
            "source": source_name,
            "lang": lang,
        })
    return items


def fetch_twitter_user_tweets(username: str) -> list[dict[str, Any]]:
    """Pobiera ostatnie tweety użytkownika (API v2, Free tier: ostatnie 7 dni)."""
    if not TWITTER_BEARER_TOKEN:
        return []

    # Najpierw user id po username
    url_user = "https://api.twitter.com/2/users/by/username/" + username
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(
                url_user,
                headers={"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"},
            )
            r.raise_for_status()
            data = r.json()
            user_id = data.get("data", {}).get("id")
    except Exception as e:
        print(f"[Twitter] user {username}: {e}")
        return []

    if not user_id:
        return []

    # Ostatnie tweety (timeline)
    url_timeline = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": min(10, MAX_TWEETS_PER_USER * 2),
        "tweet.fields": "created_at,public_metrics",
        "exclude": "replies,retweets",
    }
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(
                url_timeline,
                params=params,
                headers={"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"[Twitter] timeline {username}: {e}")
        return []

    tweets = []
    for t in data.get("data", [])[:MAX_TWEETS_PER_USER]:
        text = (t.get("text") or "").strip()
        if not text:
            continue
        created = t.get("created_at", "")
        tweets.append({
            "text": _sanitize(text)[:500],
            "author": username,
            "created_iso": created[:80],
            "id": t.get("id", ""),
            "url": f"https://twitter.com/{username}/status/{t.get('id', '')}",
        })
    return tweets


def collect_all() -> dict[str, Any]:
    """Zbiera artykuły z RSS i opcjonalnie tweety. Zwraca słownik do zapisu JSON."""
    collected_at = datetime.now(timezone.utc).isoformat()

    # --- RSS ---
    all_news: list[dict[str, Any]] = []
    for feed in RSS_FEEDS:
        items = fetch_rss_feed(feed["url"], feed["name"], feed.get("lang", "en"))
        all_news.extend(items)
        time.sleep(RSS_DELAY)

    # Sortowanie po dacie (jeśli mamy published_iso; inaczej kolejność wejścia)
    def _sort_key(n):
        s = n.get("published_iso") or ""
        return s

    all_news.sort(key=_sort_key, reverse=True)

    # --- Twitter (opcjonalnie) ---
    twitter_posts: list[dict[str, Any]] = []
    if TWITTER_BEARER_TOKEN:
        for username in TWITTER_USERNAMES:
            tweets = fetch_twitter_user_tweets(username)
            twitter_posts.extend(tweets)
            time.sleep(0.5)
        twitter_posts.sort(key=lambda t: t.get("created_iso") or "", reverse=True)
    else:
        print("[Twitter] Pominięto (brak TWITTER_BEARER_TOKEN)")

    return {
        "meta": {
            "collected_at": collected_at,
            "sources_rss": [f["name"] for f in RSS_FEEDS],
            "sources_twitter": list(TWITTER_USERNAMES) if TWITTER_BEARER_TOKEN else [],
        },
        "news": all_news,
        "twitter": twitter_posts,
    }


def main():
    print("Zbieram dane rynkowe (RSS + Twitter)...")
    data = collect_all()
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Zapisano: {OUTPUT_FILE}")
    print(f"  Artykuły: {len(data['news'])}")
    print(f"  Tweety:   {len(data['twitter'])}")


if __name__ == "__main__":
    main()
