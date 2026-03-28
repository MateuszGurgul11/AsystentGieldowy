import asyncio
import hashlib
import logging
import httpx
import feedparser
from config import get_settings
from services.prediction_service import process_event
from database import get_supabase

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    # Krypto
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "source": "CoinDesk"},
    {"url": "https://cointelegraph.com/rss", "source": "CoinTelegraph"},
    {"url": "https://www.theblock.co/rss.xml", "source": "TheBlock"},
    {"url": "https://decrypt.co/feed", "source": "Decrypt"},
    # Finanse globalne
    {"url": "https://feeds.reuters.com/reuters/businessNews", "source": "Reuters"},
    {"url": "https://feeds.bloomberg.com/markets/news.rss", "source": "Bloomberg"},
    {"url": "https://seekingalpha.com/market_currents.xml", "source": "SeekingAlpha"},
]

# Słowa kluczowe - tylko artykuły z nimi trafiają do klasyfikatora LLM
RELEVANT_KEYWORDS = [
    "bitcoin", "crypto", "ethereum", "blockchain", "defi",
    "fed", "interest rate", "inflation", "recession", "tariff",
    "sec", "regulation", "etf", "blackrock", "microstrategy",
    "nasdaq", "s&p", "market crash", "bull", "bear",
    "trump", "powell", "yellen",
]


async def news_monitor():
    """Background task: polling RSS feedów co 5 minut."""
    settings = get_settings()
    logger.info("News monitor uruchomiony")

    while True:
        try:
            await _poll_all_feeds()
        except Exception as e:
            logger.error(f"News monitor error: {e}")

        await asyncio.sleep(settings.news_poll_interval)


async def _poll_all_feeds():
    """Pobiera nowe artykuły ze wszystkich feedów."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        for feed_info in RSS_FEEDS:
            try:
                await _process_feed(client, feed_info)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Błąd feedu {feed_info['source']}: {e}")


async def _process_feed(client: httpx.AsyncClient, feed_info: dict):
    """Przetwarza pojedynczy RSS feed."""
    db = get_supabase()
    response = await client.get(feed_info["url"])
    feed = feedparser.parse(response.text)

    for entry in feed.entries[:10]:  # max 10 najnowszych
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        link = entry.get("link", "")
        combined = f"{title} {summary}".lower()

        # Filtruj tylko relevantne artykuły
        if not any(kw in combined for kw in RELEVANT_KEYWORDS):
            continue

        # Deduplikacja po URL hash
        url_hash = hashlib.md5(link.encode()).hexdigest()
        existing = (
            db.table("events")
            .select("id")
            .eq("source", "news")
            .eq("source_id", url_hash)
            .execute()
        )
        if existing.data:
            continue

        logger.info(f"Nowy artykuł [{feed_info['source']}]: {title[:60]}...")

        await process_event({
            "source": "news",
            "source_id": url_hash,
            "author": feed_info["source"],
            "content": f"{title}\n\n{summary[:500]}",
            "url": link,
        })
