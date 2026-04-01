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
    urgency: str = "medium",
) -> dict:
    """
    Generuje 3-4 scenariusze dla zdarzenia rynkowego.
    Post-processing: normalizacja prawdopodobieństw, EV-based recommendation.
    """
    context_lines = [
        f"ZDARZENIE: {event_content[:500]}",
        f"DOTKNIĘTE AKTYWA: {', '.join(affected_assets)}",
        f"KIERUNEK WPŁYWU: {impact_direction}",
        "",
        "AKTUALNE DANE RYNKOWE:",
    ]
    for symbol, data in market_context.items():
        context_lines.append(
            f"  {symbol}: cena={data.get('price_pln', 'N/A')} PLN, "
            f"zmiana24h={data.get('price_change_24h', 'N/A')}%, "
            f"RSI={data.get('rsi_14', 'N/A')}, MACD={data.get('macd_signal', 'N/A')}, "
            f"F&G={data.get('fear_greed_index', 'N/A')}"
        )
    if budget_pln > 0:
        context_lines += [f"\nBUDŻET UŻYTKOWNIKA: {budget_pln:.0f} PLN", f"PROFIL RYZYKA: {risk_profile}"]

    user_message = "\n".join(context_lines)

    # Używa dużego modelu 35B — głęboka analiza scenariuszy
    from config import get_settings
    settings = get_settings()
    try:
        raw = await ollama_chat(
            system_prompt=SCENARIO_GENERATOR_SYSTEM,
            user_message=user_message,
            temperature=0.3,
            max_tokens=1800,
            model=settings.ollama_model_analyzer,
        )
        result = _extract_json(raw)
        if result is None:
            return _build_fallback(affected_assets, event_content, impact_direction)
    except Exception as e:
        logger.warning(f"Scenario generator LLM error: {e}")
        return _build_fallback(affected_assets, event_content, impact_direction)

    # Post-processing
    from llm.event_classifier import get_impact_cap, VALID_MARKET_SYMBOLS
    impact_cap = get_impact_cap(urgency)

    scenarios = result.get("scenarios", [])
    scenarios = _normalize_probabilities(scenarios)
    scenarios = _fix_asset_consistency(scenarios)
    scenarios = _calibrate_impacts(scenarios, impact_cap, VALID_MARKET_SYMBOLS)
    result["scenarios"] = scenarios

    # Zawsze obliczamy EV i nadpisujemy rekomendację logiką matematyczną
    ev_recommendation = _compute_ev_recommendation(scenarios, affected_assets)
    result["recommendation"] = ev_recommendation

    # Sanityzuj confidence
    conf = result.get("confidence", "medium")
    result["confidence"] = conf if conf in ("low", "medium", "high") else "medium"

    # Upewnij się że reasoning jest wypełniony
    if not result.get("reasoning") or result["reasoning"] in ("Ogólne uzasadnienie analizy", ""):
        result["reasoning"] = _generate_fallback_reasoning(scenarios, affected_assets, impact_direction)

    return result


def _normalize_probabilities(scenarios: list) -> list:
    """Normalizuje prawdopodobieństwa tak żeby sumowały się do 1.0."""
    total = sum(s.get("probability", 0) for s in scenarios)
    if total <= 0:
        equal = round(1.0 / len(scenarios), 2) if scenarios else 0
        for s in scenarios:
            s["probability"] = equal
        return scenarios
    if abs(total - 1.0) < 0.02:
        return scenarios
    for s in scenarios:
        s["probability"] = round(s.get("probability", 0) / total, 2)
    # Popraw błąd zaokrąglenia na pierwszym scenariuszu
    diff = round(1.0 - sum(s["probability"] for s in scenarios), 2)
    if scenarios and diff != 0:
        scenarios[0]["probability"] = round(scenarios[0]["probability"] + diff, 2)
    return scenarios


def _fix_asset_consistency(scenarios: list) -> list:
    """
    Naprawia niespójność: jeśli opis mówi 'nie spada' ale affected_assets < 0 → korekta.
    """
    positive_keywords = ["nie spada", "odbija", "wzrost", "pozytywny", "absorbuje", "short squeeze", "pump"]
    negative_keywords = ["spada", "korekta", "wyprzedaż", "panika", "crash"]

    for s in scenarios:
        desc = s.get("description", "").lower()
        assets = s.get("affected_assets", {})

        has_positive_desc = any(kw in desc for kw in positive_keywords)
        has_negative_desc = any(kw in desc for kw in negative_keywords)

        for asset, impact in assets.items():
            if has_positive_desc and not has_negative_desc and impact < 0:
                assets[asset] = abs(impact) * 0.5  # korekta: lekko pozytywny
            elif not has_positive_desc and not has_negative_desc and impact < -20:
                assets[asset] = -20.0  # cap na -20%
        s["affected_assets"] = assets
    return scenarios


def _compute_ev_recommendation(scenarios: list, affected_assets: list) -> dict:
    """
    Oblicza Expected Value dla każdego aktywa i generuje konkretną rekomendację.
    EV = Σ(probability × impact)
    """
    if not scenarios:
        return {"action": "WAIT", "rationale": "Brak scenariuszy", "steps": [], "expected_values": {}}

    # Zbierz EV per aktywo
    asset_evs: dict[str, float] = {}
    all_assets_in_scenarios = set()
    for s in scenarios:
        for asset in s.get("affected_assets", {}):
            all_assets_in_scenarios.add(asset)

    for asset in all_assets_in_scenarios:
        ev = sum(
            s.get("probability", 0) * s.get("affected_assets", {}).get(asset, 0)
            for s in scenarios
        )
        asset_evs[asset] = round(ev, 2)

    if not asset_evs:
        return {"action": "WAIT", "rationale": "Brak danych do obliczenia EV", "steps": [], "expected_values": {}}

    # Główne aktywo = największy bezwzględny EV
    primary_asset = max(asset_evs, key=lambda a: abs(asset_evs[a]))
    primary_ev = asset_evs[primary_asset]

    # Decyzja na podstawie EV
    if primary_ev <= -7:
        action = "REDUCE_RISK"
    elif primary_ev <= -3:
        action = "SELL"
    elif primary_ev >= 5:
        action = "BUY"
    elif primary_ev >= 2:
        action = "WAIT"  # pozytywny ale czekaj na potwierdzenie
    else:
        action = "HOLD"

    # Oblicz opis EV
    ev_formula = " + ".join(
        f"{s.get('probability', 0):.0%}×{s.get('affected_assets', {}).get(primary_asset, 0):+.0f}%"
        for s in scenarios
        if primary_asset in s.get("affected_assets", {})
    )
    direction_str = "Dominują scenariusze spadkowe." if primary_ev < -1 else (
        "Dominują scenariusze wzrostowe." if primary_ev > 1 else "Scenariusze zbalansowane."
    )
    rationale = f"EV dla {primary_asset}: {primary_ev:+.1f}% ({ev_formula}). {direction_str}"

    # Kroki
    steps = []
    for asset, ev in sorted(asset_evs.items(), key=lambda x: x[1]):
        if ev <= -7:
            steps.append({"symbol": asset, "action": "SELL", "quantity_pct": 30, "note": f"EV={ev:+.1f}%"})
        elif ev <= -3:
            steps.append({"symbol": asset, "action": "SELL", "quantity_pct": 15, "note": f"EV={ev:+.1f}%"})
        elif ev >= 4:
            steps.append({"symbol": asset, "action": "BUY", "quantity_pct": 10, "note": f"EV={ev:+.1f}%"})
        else:
            steps.append({"symbol": asset, "action": "HOLD", "note": f"EV={ev:+.1f}%"})

    return {
        "action": action,
        "rationale": rationale,
        "steps": steps[:4],
        "expected_values": asset_evs,
    }


def _calibrate_impacts(scenarios: list, impact_cap: float, valid_symbols: set) -> list:
    """
    1. Usuwa nieznane symbole (NITROGEN, FERTILIZERS itp.)
    2. Wykrywa czy LLM wstawił ceny bezwzględne zamiast % (np. 250000 zamiast +3%)
       i ignoruje takie wartości (zastępuje 0.0)
    3. Capuje wartości do ±impact_cap
    """
    for s in scenarios:
        assets = s.get("affected_assets", {})
        cleaned = {}
        for symbol, value in assets.items():
            # Filtruj nieznane symbole
            if symbol.upper() not in valid_symbols:
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            # Wykryj wartości bezwzględne: cena BTC to ~30000-500000,
            # procentowy wpływ nigdy nie przekracza ±100%
            if abs(v) > 100:
                logger.warning(f"Odrzucam wartość bezwzględną {symbol}={v} (wygląda jak cena, nie %)")
                continue
            # Capuj do impact_cap
            v = max(-impact_cap, min(impact_cap, v))
            cleaned[symbol.upper()] = round(v, 1)
        s["affected_assets"] = cleaned
    return scenarios


def _generate_fallback_reasoning(scenarios: list, affected_assets: list, impact_direction: str) -> str:
    """Generuje podstawowe reasoning gdy LLM go nie podał."""
    n_positive = sum(1 for s in scenarios if any(v > 0 for v in s.get("affected_assets", {}).values()))
    n_negative = sum(1 for s in scenarios if any(v < 0 for v in s.get("affected_assets", {}).values()))
    assets_str = ", ".join(affected_assets[:3]) if affected_assets else "rynek"
    return (
        f"Zdarzenie z kierunkiem '{impact_direction}' dla {assets_str}. "
        f"Scenariusze: {n_positive} pozytywnych, {n_negative} negatywnych. "
        f"Rekomendacja obliczona na podstawie Expected Value."
    )


def _build_fallback(affected_assets: list, event_content: str, impact_direction: str) -> dict:
    """
    Fallback gdy Ollama nie odpowiada lub zwraca błędny JSON.
    Buduje podstawowe scenariusze z heurystyk zamiast zwracać 'Analiza niedostępna'.
    """
    is_negative = impact_direction in ("negative",)
    is_positive = impact_direction in ("positive",)

    if is_negative:
        scenarios = [
            {
                "id": "A", "label": "Negatywna reakcja rynku", "probability": 0.45,
                "description": "Rynek reaguje wyprzedażą na negatywny news.",
                "affected_assets": {a: -8.0 for a in (affected_assets or ["BTC"])},
                "timeframe": "24-48h", "confidence": "low",
            },
            {
                "id": "B", "label": "Umiarkowana korekta", "probability": 0.35,
                "description": "Krótka korekta, rynek szybko wycenia informację.",
                "affected_assets": {a: -3.0 for a in (affected_assets or ["BTC"])},
                "timeframe": "6-24h", "confidence": "low",
            },
            {
                "id": "C", "label": "Rynek ignoruje", "probability": 0.20,
                "description": "News już był wyceniony lub rynek ma silne wsparcie techniczne.",
                "affected_assets": {a: 1.0 for a in (affected_assets or ["BTC"])},
                "timeframe": "1-6h", "confidence": "low",
            },
        ]
    elif is_positive:
        scenarios = [
            {
                "id": "A", "label": "Pozytywna reakcja rynku", "probability": 0.40,
                "description": "Rynek reaguje wzrostami na pozytywny news.",
                "affected_assets": {a: 6.0 for a in (affected_assets or ["BTC"])},
                "timeframe": "24-48h", "confidence": "low",
            },
            {
                "id": "B", "label": "Umiarkowane wzrosty", "probability": 0.35,
                "description": "Ograniczona reakcja, brak wolumenu potwierdzającego.",
                "affected_assets": {a: 2.0 for a in (affected_assets or ["BTC"])},
                "timeframe": "6-24h", "confidence": "low",
            },
            {
                "id": "C", "label": "Brak reakcji", "probability": 0.25,
                "description": "Rynek już wycenił pozytywne informacje.",
                "affected_assets": {a: -1.0 for a in (affected_assets or ["BTC"])},
                "timeframe": "1-6h", "confidence": "low",
            },
        ]
    else:
        scenarios = [
            {
                "id": "A", "label": "Wpływ negatywny", "probability": 0.35,
                "description": "Rynek interpretuje zdarzenie negatywnie.",
                "affected_assets": {a: -5.0 for a in (affected_assets or ["BTC"])},
                "timeframe": "24-48h", "confidence": "low",
            },
            {
                "id": "B", "label": "Brak wpływu", "probability": 0.40,
                "description": "Rynek ignoruje zdarzenie lub jest już wycenione.",
                "affected_assets": {a: 0.5 for a in (affected_assets or ["BTC"])},
                "timeframe": "6-24h", "confidence": "low",
            },
            {
                "id": "C", "label": "Wpływ pozytywny", "probability": 0.25,
                "description": "Rynek interpretuje zdarzenie pozytywnie.",
                "affected_assets": {a: 4.0 for a in (affected_assets or ["BTC"])},
                "timeframe": "24-48h", "confidence": "low",
            },
        ]

    ev_rec = _compute_ev_recommendation(scenarios, affected_assets)
    return {
        "scenarios": scenarios,
        "recommendation": ev_rec,
        "confidence": "low",
        "reasoning": (
            f"Scenariusze wygenerowane heurystycznie (Ollama niedostępna). "
            f"Zdarzenie: {event_content[:100]}... Kierunek: {impact_direction}. "
            f"Zweryfikuj ręcznie przed podjęciem decyzji."
        ),
    }


def _extract_json(text: str) -> dict | None:
    """Wyciąga poprawny JSON z tekstu LLM."""
    start = text.find("{")
    if start == -1:
        return None
    for end in range(len(text), start, -1):
        if text[end - 1] == "}":
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue
    return None


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
                f"  {pos['symbol']}: {pos['quantity']} szt. @ {pos['avg_buy_price']} {pos.get('currency','PLN')} "
                f"(P&L: {pnl:+.1f}%)"
            )
    else:
        context_parts.append("  (pusty portfel)")

    context_parts.append("\nAKTUALNE DANE RYNKOWE:")
    for symbol, data in list(market_data.items())[:10]:
        context_parts.append(
            f"  {symbol}: {data.get('price_pln', 'N/A')} PLN "
            f"({data.get('price_change_24h', 0):+.1f}% 24h) RSI={data.get('rsi_14', 'N/A')}"
        )

    if recent_alerts:
        context_parts.append("\nOSTATNIE ALERTY:")
        for alert in recent_alerts[:3]:
            context_parts.append(f"  [{alert.get('priority','').upper()}] {alert.get('title','')}: {alert.get('body','')[:100]}")

    full_message = "\n".join(context_parts) + f"\n\nPYTANIE: {user_message}"

    from config import get_settings
    settings = get_settings()
    return await ollama_chat(
        system_prompt=CHAT_SYSTEM,
        user_message=full_message,
        temperature=0.4,
        max_tokens=1500,
        model=settings.ollama_model_analyzer,
    )
