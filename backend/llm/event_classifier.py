import json
import logging
from llm.client import ollama_chat
from llm.prompts import EVENT_CLASSIFIER_SYSTEM

logger = logging.getLogger(__name__)

# Znane symbole krypto i akcji - jedyne dopuszczalne w affected_assets
VALID_MARKET_SYMBOLS = {
    "BTC", "ETH", "SOL", "ADA", "XRP", "DOGE", "DOT", "AVAX", "LINK",
    "MATIC", "TON", "TRX", "LTC", "UNI", "NEAR", "BNB", "USDT", "USDC",
    "SPY", "QQQ", "NVDA", "AAPL", "TSLA", "MSFT", "META", "GOOGL", "AMZN",
    "OIL", "GOLD", "SILVER",
}

# Słowa kluczowe wysokiej relevancji - zawsze przepuszcza do LLM
HIGH_RELEVANCE_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain", "defi",
    "fed ", "federal reserve", "interest rate", "inflation", "tariff",
    "sec ", "regulation", "etf", "halving", "exchange hack", "binance",
    "coinbase", "trump", "powell", "elon", "saylor", "whale", "on-chain",
    "stablecoin", "usdt", "usdc", "cbdc", "ban crypto", "crypto ban",
    "nasdaq", "s&p 500", "sp500", "market crash", "recession", "cpi", "nfp",
    "rate hike", "rate cut", "quantitative", "sanctions", "iran", "china tariff",
]

# Słowa kluczowe niskiej relevancji - odrzuca bez wywołania LLM
LOW_RELEVANCE_KEYWORDS = [
    "data center", "ai model", "language model", "llm release", "nfl", "nba",
    "soccer", "football", "celebrity", "actor", "singer", "award", "oscar",
    "food recall", "weather", "earthquake", "climate", "vaccination",
    "fertilizer supply", "crop yield", "agriculture harvest",
]

# Max realny wpływ na cenę per typ zdarzenia (%)
IMPACT_CAPS = {
    "high": 15.0,    # Fed, ETF approval, exchange hack, ban
    "medium": 8.0,   # Makro US, whale movement, regulatory
    "low": 4.0,      # Sponsoring, partnerstwo, opinia influencera
}


def keyword_prefilter(content: str) -> tuple[bool, float]:
    """
    Szybki pre-filter przed wywołaniem LLM.
    Zwraca (should_process, estimated_relevance).
    """
    content_lower = content.lower()

    # Sprawdź słowa kluczowe niskiej relevancji
    for kw in LOW_RELEVANCE_KEYWORDS:
        if kw in content_lower:
            # Sprawdź czy nie ma override wysokiej relevancji
            has_high = any(h in content_lower for h in HIGH_RELEVANCE_KEYWORDS)
            if not has_high:
                logger.debug(f"Pre-filter odrzucił (low relevance keyword: '{kw}')")
                return False, 0.1

    return True, 0.5


async def classify_event(content: str) -> dict:
    """
    Klasyfikuje zdarzenie pod kątem wpływu na rynki.
    1. Keyword pre-filter (bez LLM)
    2. LLM classifier
    3. Walidacja symboli i kalibracja
    """
    # 1. Pre-filter
    should_process, _ = keyword_prefilter(content)
    if not should_process:
        return _low_relevance_result()

    # 2. LLM classifier — używa małego modelu 3B (szybki filtr)
    from config import get_settings
    settings = get_settings()
    try:
        raw = await ollama_chat(
            system_prompt=EVENT_CLASSIFIER_SYSTEM,
            user_message=content[:2000],
            temperature=0.1,
            max_tokens=512,
            model=settings.ollama_model_classifier,
        )
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return _default_classification()

        data = json.loads(raw[start:end])
    except Exception as e:
        logger.warning(f"Classifier LLM error: {e}")
        return _default_classification()

    # 3. Walidacja i sanityzacja
    data["affected_assets"] = _validate_symbols(data.get("affected_assets", []))

    # Upewnij się że relevance_score jest float w [0,1]
    score = data.get("relevance_score", 0.0)
    try:
        data["relevance_score"] = max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        data["relevance_score"] = 0.0

    return data


def _validate_symbols(symbols: list) -> list:
    """Filtruje symbole - tylko znane krypto/akcje, bez NITROGEN itp."""
    if not isinstance(symbols, list):
        return []
    return [s.upper() for s in symbols if str(s).upper() in VALID_MARKET_SYMBOLS]


def get_impact_cap(urgency: str) -> float:
    """Zwraca maksymalny dopuszczalny wpływ % dla danego urgency."""
    return IMPACT_CAPS.get(urgency, IMPACT_CAPS["medium"])


def _low_relevance_result() -> dict:
    return {
        "is_market_relevant": False,
        "relevance_score": 0.1,
        "affected_assets": [],
        "impact_direction": "unknown",
        "is_likely_fake": False,
        "is_pump_signal": False,
        "reasoning": "Odrzucono przez pre-filter - brak powiązania z rynkami finansowymi",
        "urgency": "low",
    }


def _default_classification() -> dict:
    return {
        "is_market_relevant": False,
        "relevance_score": 0.0,
        "affected_assets": [],
        "impact_direction": "unknown",
        "is_likely_fake": False,
        "is_pump_signal": False,
        "reasoning": "Błąd klasyfikacji LLM",
        "urgency": "low",
    }
