import asyncio
import logging
from datetime import datetime, timezone
from config import get_settings
from services.prediction_service import process_event
from database import get_supabase

logger = logging.getLogger(__name__)

# Konta VIP które zawsze monitorujemy
VIP_ACCOUNTS = [
    "realDonaldTrump",
    "elonmusk",
    "federalreserve",
    "SECGov",
    "Michael_Saylor",
    "cz_binance",
    "VitalikButerin",
    "Reuters",
    "Bloomberg",
    "APompliano",
    "WatcherGuru",
    "DocumentingBTC",
]

# Słowa kluczowe które zwiększają relevance nawet bez VIP konta
HIGH_IMPACT_KEYWORDS = [
    "tariff", "taryfa", "bitcoin", "crypto", "fed rate", "interest rate",
    "sec", "regulation", "ban", "sanctions", "inflation", "recession",
    "etf", "halving", "blackrock", "microstrategy",
]


async def twitter_monitor():
    """Background task: polling Twittera co 3 minuty."""
    settings = get_settings()

    if not settings.twitter_bearer_token:
        logger.warning("TWITTER_BEARER_TOKEN nie ustawiony - monitor wyłączony")
        return

    try:
        import tweepy
        client = tweepy.AsyncClient(bearer_token=settings.twitter_bearer_token)
    except ImportError:
        logger.error("tweepy nie zainstalowany")
        return

    logger.info("Twitter monitor uruchomiony")

    while True:
        try:
            await _poll_twitter(client)
        except Exception as e:
            logger.error(f"Twitter monitor error: {e}")

        await asyncio.sleep(settings.twitter_poll_interval)


async def _poll_twitter(client):
    """Pobiera nowe tweety od VIP kont i przetwarza istotne."""
    db = get_supabase()

    for username in VIP_ACCOUNTS:
        try:
            # Pobierz user ID
            user_response = await client.get_user(username=username)
            if not user_response.data:
                continue

            user_id_tw = user_response.data.id

            # Pobierz ostatnie 5 tweetów (exclude retweets/replies)
            tweets_response = await client.get_users_tweets(
                id=user_id_tw,
                max_results=5,
                exclude=["retweets", "replies"],
                tweet_fields=["created_at", "public_metrics"],
            )

            if not tweets_response.data:
                continue

            for tweet in tweets_response.data:
                tweet_id = str(tweet.id)

                # Sprawdź czy już przetwarzaliśmy
                existing = (
                    db.table("events")
                    .select("id")
                    .eq("source", "twitter")
                    .eq("source_id", tweet_id)
                    .execute()
                )
                if existing.data:
                    continue

                # Czy tweet zawiera słowa kluczowe?
                text_lower = tweet.text.lower()
                has_keywords = any(kw in text_lower for kw in HIGH_IMPACT_KEYWORDS)
                is_vip = username in ["realDonaldTrump", "elonmusk", "federalreserve", "SECGov"]

                if not has_keywords and not is_vip:
                    continue

                logger.info(f"Nowy tweet od @{username}: {tweet.text[:80]}...")

                await process_event({
                    "source": "twitter",
                    "source_id": tweet_id,
                    "author": f"@{username}",
                    "content": tweet.text,
                    "url": f"https://twitter.com/{username}/status/{tweet_id}",
                })

            await asyncio.sleep(1)  # rate limiting między kontami

        except Exception as e:
            logger.warning(f"Błąd pobierania tweetów od @{username}: {e}")
            continue
