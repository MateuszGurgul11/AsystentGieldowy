"""
Wspolna konfiguracja dla wszystkich agentow.
API keys, URLe, listy coinow, parametry modelu.
"""

import os
from pathlib import Path

# --- Sciezki ---
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# --- CoinGecko ---
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "CG-2Acrqo3uxa8J7z7fY6JRZQtV")
COINGECKO_USE_PRO = os.environ.get("COINGECKO_USE_PRO", "").strip().lower() in ("1", "true", "yes")

if COINGECKO_USE_PRO and COINGECKO_API_KEY:
    COINGECKO_BASE_URL = "https://pro-api.coingecko.com/api/v3"
    COINGECKO_HEADER_KEY = "x-cg-pro-api-key"
else:
    COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
    COINGECKO_HEADER_KEY = "x-cg-demo-api-key" if COINGECKO_API_KEY else None

COINGECKO_DELAY = 0.5 if COINGECKO_API_KEY else 1.5

# --- Binance ---
BINANCE_BASE_URL = "https://api.binance.com/api/v3"

# --- Top coiny do analizy ---
TOP_COIN_IDS = "bitcoin,ethereum,solana,cardano,ripple,dogecoin,polkadot,avalanche-2,chainlink,matic-network,toncoin,tron,litecoin,uniswap,near"
TOP_BINANCE_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT",
    "DOGEUSDT", "DOTUSDT", "AVAXUSDT", "LINKUSDT", "MATICUSDT",
    "TONUSDT", "TRXUSDT", "LTCUSDT", "UNIUSDT", "NEARUSDT",
]

# --- RSS ---
RSS_FEEDS = [
    {"url": "https://www.coindesk.com/arc/outboundfeeds/rss", "name": "CoinDesk", "lang": "en"},
    {"url": "https://cointelegraph.com/rss", "name": "CoinTelegraph", "lang": "en"},
    {"url": "https://www.theblock.co/rss.xml", "name": "The Block", "lang": "en"},
    {"url": "https://cointelegraph.com/rss/tag/bitcoin", "name": "CoinTelegraph Bitcoin", "lang": "en"},
    {"url": "https://cointelegraph.com/rss/tag/ethereum", "name": "CoinTelegraph Ethereum", "lang": "en"},
    {"url": "https://cointelegraph.com/rss/tag/regulation", "name": "CoinTelegraph Regulation", "lang": "en"},
]

# --- Twitter (graceful fallback) ---
TWITTER_BEARER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN", "").strip()
TWITTER_USERNAMES = [
    "saylor", "APompliano", "DocumentingBTC", "WatcherGuru",
    "CoinDesk", "Cointelegraph", "Reuters", "Bloomberg", "business",
]

# --- Ollama ---
OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "invest-assistant"
OLLAMA_TIMEOUT = 180

# --- Budzet ---
BUDGET_PLN = 10_000

# --- HTTP ---
REQUEST_TIMEOUT = 30


def coingecko_headers() -> dict:
    headers = {"Accept": "application/json"}
    if COINGECKO_HEADER_KEY and COINGECKO_API_KEY:
        headers[COINGECKO_HEADER_KEY] = COINGECKO_API_KEY
    return headers


def coingecko_get(url: str, params: dict | None = None) -> dict | list | None:
    """GET do CoinGecko. Zwraca JSON lub None."""
    import httpx
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(url, params=params or {}, headers=coingecko_headers())
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"  [CoinGecko] {e}")
        return None


def save_json(data: dict, filename: str) -> Path:
    """Zapisuje dict do JSON w DATA_DIR."""
    import json
    path = DATA_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_json(filename: str) -> dict | None:
    """Wczytuje JSON z DATA_DIR. None jesli brak."""
    import json
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
