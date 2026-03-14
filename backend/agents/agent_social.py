"""
Agent Social — Twitter (graceful fallback) + Reddit placeholder.
Wynik: data/social_sentiment.json
"""

import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import TWITTER_BEARER_TOKEN, TWITTER_USERNAMES, REQUEST_TIMEOUT, save_json

MAX_TWEETS_PER_USER = 5


def _sanitize(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def fetch_user_tweets(username: str) -> list[dict[str, Any]]:
    """Pobiera ostatnie tweety (API v2). Zwraca [] jesli brak tokena."""
    if not TWITTER_BEARER_TOKEN:
        return []

    headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(
                f"https://api.twitter.com/2/users/by/username/{username}",
                headers=headers,
            )
            r.raise_for_status()
            user_id = r.json().get("data", {}).get("id")
    except Exception as e:
        print(f"  [Twitter] user {username}: {e}")
        return []

    if not user_id:
        return []

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(
                f"https://api.twitter.com/2/users/{user_id}/tweets",
                params={
                    "max_results": min(10, MAX_TWEETS_PER_USER * 2),
                    "tweet.fields": "created_at,public_metrics",
                    "exclude": "replies,retweets",
                },
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"  [Twitter] timeline {username}: {e}")
        return []

    tweets = []
    for t in data.get("data", [])[:MAX_TWEETS_PER_USER]:
        text = (t.get("text") or "").strip()
        if not text:
            continue
        metrics = t.get("public_metrics", {})
        tweets.append({
            "text": _sanitize(text),
            "author": username,
            "created_at": t.get("created_at", "")[:80],
            "tweet_id": t.get("id", ""),
            "url": f"https://twitter.com/{username}/status/{t.get('id', '')}",
            "likes": metrics.get("like_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "replies": metrics.get("reply_count", 0),
        })
    return tweets


def fetch_reddit_placeholder() -> list[dict]:
    """Placeholder dla Reddit — do implementacji w przyszlosci."""
    return []


def run() -> dict:
    """Uruchamia agenta social media."""
    print("[Agent Social] Start...")
    collected_at = datetime.now(timezone.utc).isoformat()

    twitter_posts: list[dict] = []
    twitter_status = "no_token"

    if TWITTER_BEARER_TOKEN:
        twitter_status = "active"
        for username in TWITTER_USERNAMES:
            tweets = fetch_user_tweets(username)
            twitter_posts.extend(tweets)
            time.sleep(0.5)
        twitter_posts.sort(key=lambda t: t.get("created_at") or "", reverse=True)
        print(f"  Twitter: {len(twitter_posts)} postow")
    else:
        print("  Twitter: pominiety (brak TWITTER_BEARER_TOKEN)")

    reddit_posts = fetch_reddit_placeholder()
    print(f"  Reddit: {len(reddit_posts)} postow (placeholder)")

    result = {
        "meta": {
            "collected_at": collected_at,
            "twitter_status": twitter_status,
            "twitter_accounts": list(TWITTER_USERNAMES) if TWITTER_BEARER_TOKEN else [],
            "reddit_status": "placeholder",
        },
        "twitter": twitter_posts,
        "reddit": reddit_posts,
    }

    path = save_json(result, "social_sentiment.json")
    print(f"[Agent Social] Zapisano: {path}")
    return result


if __name__ == "__main__":
    run()
