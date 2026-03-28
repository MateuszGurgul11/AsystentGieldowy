import json
import logging
from llm.client import ollama_chat
from llm.prompts import EVENT_CLASSIFIER_SYSTEM

logger = logging.getLogger(__name__)


async def classify_event(content: str) -> dict:
    """
    Klasyfikuje zdarzenie (tweet/news) pod kątem wpływu na rynki.
    Zwraca słownik z relevance_score, affected_assets, itp.
    """
    try:
        raw = await ollama_chat(
            system_prompt=EVENT_CLASSIFIER_SYSTEM,
            user_message=content[:2000],  # limit kontekstu
            temperature=0.1,              # bardzo deterministyczny
            max_tokens=512,
        )

        # Wyciągnij JSON z odpowiedzi (LLM może dodać tekst przed/po)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return _default_classification()

        data = json.loads(raw[start:end])
        return data

    except Exception as e:
        logger.warning(f"Classifier error: {e}")
        return _default_classification()


def _default_classification() -> dict:
    return {
        "is_market_relevant": False,
        "relevance_score": 0.0,
        "affected_assets": [],
        "impact_direction": "unknown",
        "is_likely_fake": False,
        "is_pump_signal": False,
        "reasoning": "Błąd klasyfikacji",
        "urgency": "low",
    }
