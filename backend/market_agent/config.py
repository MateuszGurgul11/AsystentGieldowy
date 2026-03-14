"""
Konfiguracja źródeł dla agenta rynkowego.
RSS = zawsze dostępne (bez kluczy). Twitter = opcjonalnie (TWITTER_BEARER_TOKEN).
"""

import os
# --- RSS: wiarygodne źródła finansowe i crypto (bez API key) ---
RSS_FEEDS = [
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss", "name": "CoinDesk", "lang": "en"},
    {"url": "https://cointelegraph.com/rss", "name": "CoinTelegraph", "lang": "en"},
    {"url": "https://www.theblock.co/rss.xml", "name": "The Block", "lang": "en"},
    {"url": "https://cointelegraph.com/rss/tag/bitcoin", "name": "CoinTelegraph Bitcoin", "lang": "en"},
    {"url": "https://cointelegraph.com/rss/tag/ethereum", "name": "CoinTelegraph Ethereum", "lang": "en"},
    {"url": "https://cointelegraph.com/rss/tag/regulation", "name": "CoinTelegraph Regulation", "lang": "en"},
]

# --- Twitter: wpływowe konta (finanse, crypto, makro). Wymaga TWITTER_BEARER_TOKEN. ---
TWITTER_USERNAMES = [
    "elikouri",           # Elon (ważne dla crypto/sentiment)
    "saylor",             # Michael Saylor (Bitcoin)
    "APompliano",         # Anthony Pompliano
    "DocumentingBTC",     # Bitcoin news
    "WatcherGuru",        # Crypto news
    "CoinDesk",           # CoinDesk
    "Cointelegraph",      # CoinTelegraph
    "Reuters",            # Reuters
    "Bloomberg",          # Bloomberg
    "business",           # Bloomberg Business
]

# Środowisko
TWITTER_BEARER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN", "").strip()
OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKET_INTEL_FILE = os.path.join(OUTPUT_DIR, "market_agent", "market_intel.json")
