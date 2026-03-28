import json
import logging
from llm.client import ollama_chat
from llm.prompts import SCENARIO_GENERATOR_SYSTEM

logger = logging.getLogger(__name__)


async def generate_scenarios(
    event_content: str,
    affected_assets: list[str],
    market_context: dict,
    impact_direction: str,
    budget_pln: float = 0.0,
    risk_profile: str = "medium",
) -> dict:
    """
    Generuje 3-4 scenariusze dla zdarzenia rynkowego.
    Zwraca dict ze scenarios, recommendation, confidence, reasoning.
    """
    context_lines = [
        f"ZDARZENIE: {event_content[:500]}",
        f"DOTKNIĘTE AKTYWA: {', '.join(affected_assets)}",
        f"KIERUNEK WPŁYWU: {impact_direction}",
        "",
        "AKTUALNE DANE RYNKOWE:",
    ]

    for symbol, data in market_context.items():
        price_pln = data.get("price_pln", "N/A")
        change_24h = data.get("price_change_24h", "N/A")
        rsi = data.get("rsi_14", "N/A")
        macd = data.get("macd_signal", "N/A")
        fg = data.get("fear_greed_index", "N/A")
        context_lines.append(
            f"  {symbol}: cena={price_pln} PLN, zmiana24h={change_24h}%, RSI={rsi}, MACD={macd}, F&G={fg}"
        )

    if budget_pln > 0:
        context_lines.append(f"\nBUDŻET UŻYTKOWNIKA: {budget_pln:.0f} PLN")
        context_lines.append(f"PROFIL RYZYKA: {risk_profile}")

    user_message = "\n".join(context_lines)

    try:
        raw = await ollama_chat(
            system_prompt=SCENARIO_GENERATOR_SYSTEM,
            user_message=user_message,
            temperature=0.3,
            max_tokens=1500,
        )

        result = _extract_json(raw)
        if result is None:
            return _default_scenarios(affected_assets)

        # Sanityzuj confidence
        conf = result.get("confidence", "medium")
        result["confidence"] = conf if conf in ("low", "medium", "high") else "medium"
        return result

    except Exception as e:
        logger.warning(f"Scenario generator error: {e}")
        return _default_scenarios(affected_assets)


def _extract_json(text: str) -> dict | None:
    """Próbuje wyciągnąć poprawny JSON z tekstu LLM."""
    # Szukaj od pierwszego { do ostatniego }
    start = text.find("{")
    if start == -1:
        return None

    # Próbuj coraz krótsze fragmenty jeśli JSON jest niepoprawny
    for end in range(len(text), start, -1):
        if text[end - 1] == "}":
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue
    return None


def _default_scenarios(affected_assets: list[str]) -> dict:
    return {
        "scenarios": [
            {
                "id": "A",
                "label": "Analiza niedostępna",
                "probability": 1.0,
                "description": "Nie udało się wygenerować scenariuszy. Sprawdź połączenie z Ollama.",
                "affected_assets": {s: 0.0 for s in affected_assets},
                "timeframe": "nieznany",
                "confidence": "low",
            }
        ],
        "recommendation": {
            "action": "WAIT",
            "rationale": "Brak danych do analizy",
            "steps": [],
        },
        "confidence": "low",
        "reasoning": "Błąd generowania scenariuszy",
    }


async def generate_chat_response(
    user_message: str,
    portfolio: dict,
    budget_pln: float,
    risk_profile: str,
    market_data: dict,
    recent_alerts: list[dict],
) -> str:
    """Generuje odpowiedź chatbota z pełnym kontekstem użytkownika."""
    from llm.prompts import CHAT_SYSTEM

    context_parts = [
        f"BUDŻET: {budget_pln:.0f} PLN",
        f"PROFIL RYZYKA: {risk_profile}",
        "",
        "PORTFEL UŻYTKOWNIKA:",
    ]

    positions = portfolio.get("positions", [])
    if positions:
        for pos in positions:
            pnl = pos.get("pnl_pct", 0) or 0
            context_parts.append(
                f"  {pos['symbol']}: {pos['quantity']} szt. @ {pos['avg_buy_price_pln']} PLN "
                f"(P&L: {pnl:+.1f}%)"
            )
    else:
        context_parts.append("  (pusty portfel)")

    context_parts.append("\nAKTUALNE DANE RYNKOWE:")
    for symbol, data in list(market_data.items())[:10]:
        context_parts.append(
            f"  {symbol}: {data.get('price_pln', 'N/A')} PLN "
            f"({data.get('price_change_24h', 0):+.1f}% 24h) "
            f"RSI={data.get('rsi_14', 'N/A')}"
        )

    if recent_alerts:
        context_parts.append("\nOSTATNIE ALERTY (ostatnie 3):")
        for alert in recent_alerts[:3]:
            context_parts.append(f"  [{alert.get('priority', '').upper()}] {alert.get('title', '')}: {alert.get('body', '')[:100]}")

    context = "\n".join(context_parts)
    full_message = f"{context}\n\nPYTANIE UŻYTKOWNIKA: {user_message}"

    return await ollama_chat(
        system_prompt=CHAT_SYSTEM,
        user_message=full_message,
        temperature=0.4,
        max_tokens=1500,
    )
