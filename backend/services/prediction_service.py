import json
from database import get_supabase
from llm.scenario_generator import generate_scenarios
from llm.event_classifier import classify_event
from services.alert_service import notify_user


async def process_event(event_data: dict) -> str | None:
    """
    Przetwarza zdarzenie (tweet/news):
    1. Klasyfikuje relevance
    2. Jeśli relevantne - generuje scenariusze
    3. Zapisuje event + predykcję do Supabase
    4. Powiadamia użytkowników

    Zwraca ID predykcji lub None.
    """
    db = get_supabase()

    # 1. Klasyfikacja zdarzenia przez LLM
    classification = await classify_event(event_data["content"])
    relevance_score = classification.get("relevance_score", 0.0)

    from config import get_settings
    settings = get_settings()
    if relevance_score < settings.event_relevance_threshold:
        return None

    # 2. Zapisz zdarzenie
    event_row = {
        "source": event_data.get("source", "twitter"),
        "source_id": event_data.get("source_id"),
        "author": event_data.get("author"),
        "content": event_data["content"],
        "url": event_data.get("url"),
        "relevance_score": relevance_score,
        "affected_assets": classification.get("affected_assets", []),
    }
    event_result = db.table("events").insert(event_row).execute()
    event_id = event_result.data[0]["id"] if event_result.data else None

    # 3. Pobierz ostatnie dane rynkowe dla kontekstu
    market_context = _get_market_context(classification.get("affected_assets", []))

    # 4. Generuj scenariusze
    scenarios_data = await generate_scenarios(
        event_content=event_data["content"],
        affected_assets=classification.get("affected_assets", []),
        market_context=market_context,
        impact_direction=classification.get("impact_direction", "unknown"),
    )

    # 5. Zapisz predykcję (bez user_id - globalna predykcja zdarzenia)
    raw_confidence = scenarios_data.get("confidence", "medium")
    confidence = raw_confidence if raw_confidence in ("low", "medium", "high") else "medium"

    prediction_row = {
        "event_id": event_id,
        "scenarios": json.dumps(scenarios_data.get("scenarios", [])),
        "recommendation": json.dumps(scenarios_data.get("recommendation", {})),
        "llm_reasoning": scenarios_data.get("reasoning"),
        "confidence": confidence,
    }
    pred_result = db.table("predictions").insert(prediction_row).execute()
    prediction_id = pred_result.data[0]["id"] if pred_result.data else None

    # 6. Powiadom wszystkich użytkowników którzy monitorują dotknięte aktywa
    _notify_interested_users(
        affected_assets=classification.get("affected_assets", []),
        event=event_data,
        event_id=event_id,
        prediction_id=prediction_id,
        classification=classification,
    )

    return prediction_id


def _get_market_context(symbols: list[str]) -> dict:
    """Pobiera ostatnie ceny i RSI dla podanych symboli."""
    if not symbols:
        return {}
    db = get_supabase()
    context = {}
    for symbol in symbols[:5]:  # max 5 symboli
        result = (
            db.table("market_snapshots")
            .select("price_pln, price_usd, price_change_24h, rsi_14, macd_signal, fear_greed_index")
            .eq("symbol", symbol.upper())
            .order("snapshot_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            context[symbol] = result.data[0]
    return context


def _notify_interested_users(
    affected_assets: list[str],
    event: dict,
    event_id: str | None,
    prediction_id: str | None,
    classification: dict,
):
    """Wysyła alerty do użytkowników monitorujących dotknięte aktywa."""
    import asyncio
    db = get_supabase()

    for symbol in affected_assets:
        # Znajdź użytkowników monitorujących ten symbol
        result = (
            db.table("alert_settings")
            .select("user_id, twitter_trigger, news_trigger")
            .contains("monitored_symbols", [symbol])
            .execute()
        )
        for row in (result.data or []):
            source = event.get("source", "twitter")
            if source == "twitter" and not row.get("twitter_trigger", True):
                continue
            if source == "news" and not row.get("news_trigger", True):
                continue

            direction = classification.get("impact_direction", "nieznany")
            author = event.get("author", "Nieznany")
            title = f"Zdarzenie rynkowe: {symbol}"
            body = (
                f"{author}: \"{event['content'][:120]}...\"\n"
                f"Wpływ: {direction} | Relevance: {classification.get('relevance_score', 0):.1f}"
            )

            asyncio.create_task(
                notify_user(
                    user_id=row["user_id"],
                    title=title,
                    body=body,
                    alert_type="event_trigger",
                    priority="high" if classification.get("relevance_score", 0) > 0.8 else "medium",
                    event_id=event_id,
                    prediction_id=prediction_id,
                )
            )
