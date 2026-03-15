"""
Agent Sumaryzujacy — scala 5 JSON-ow, streszcza przez LLM.
Wynik: data/summary.json
"""

import json
from datetime import datetime, timezone

import httpx

from .config import (
    OLLAMA_URL, MODEL_NAME, OLLAMA_TIMEOUT, load_json, save_json,
)

MAX_CONTEXT_CHARS = 12000


def _truncate(text: str, limit: int) -> str:
    return text[:limit] if len(text) > limit else text


def _build_context() -> str:
    """Buduje tekstowy kontekst z 5 plikow JSON."""
    sections = []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections.append(f"=== DATA ANALIZY: {now} ===")

    # 1. Ceny rynkowe
    market = load_json("market_prices.json")
    if market:
        usd_pln = market.get("meta", {}).get("usd_pln_rate", "?")
        coins = market.get("coins", [])
        lines = [f"Kurs USD/PLN: {usd_pln}"]
        for c in coins[:15]:
            lines.append(
                f"  {c['symbol']}: {c.get('price_pln')} PLN "
                f"(${c.get('price_usd', '?')}) "
                f"24h: {c.get('price_change_24h_pct', '?')}% "
                f"7d: {c.get('price_change_7d_pct', '?')}%"
            )
        glob = market.get("global", {})
        if glob:
            cap = glob.get("total_market_cap_usd")
            btc_dom = glob.get("market_cap_percentage_btc")
            lines.append(f"  Globalna kapitalizacja: ${cap}, BTC dominacja: {btc_dom}%")
        sections.append("=== CENY RYNKOWE ===\n" + "\n".join(lines))

    # 2. Analiza techniczna
    ta = load_json("technical_analysis.json")
    if ta:
        lines = []
        for coin_name, coin_data in ta.get("analysis", {}).items():
            daily = coin_data.get("daily", {})
            h4 = coin_data.get("4h", {})
            lines.append(
                f"  {coin_name}: RSI(d)={daily.get('rsi_14','?')} "
                f"MACD(d)={daily.get('overall','?')} "
                f"RSI(4h)={h4.get('rsi_14','?')} "
                f"MACD(4h)={h4.get('overall','?')}"
            )
            for sig in (daily.get("signals") or [])[:2]:
                lines.append(f"    -> {sig}")
        sections.append("=== ANALIZA TECHNICZNA ===\n" + "\n".join(lines))

    # 3. Newsy
    news = load_json("news_digest.json")
    if news:
        articles = news.get("articles", [])[:20]
        lines = []
        for a in articles:
            coins_tag = ""
            mentioned = a.get("mentioned_coins", [])
            if mentioned:
                coins_tag = f" [dotyczy: {', '.join(mentioned)}]"
            lines.append(f"  [{a.get('source')}] {a.get('title')}{coins_tag}")
            if a.get("full_content"):
                lines.append(f"    Tresc: {a['full_content'][:300]}...")
        sections.append("=== NEWSY ===\n" + "\n".join(lines))

    # 4. Social media
    social = load_json("social_sentiment.json")
    if social:
        tw = social.get("twitter", [])
        status = social.get("meta", {}).get("twitter_status", "?")
        lines = [f"  Twitter status: {status}, postow: {len(tw)}"]
        for t in tw[:5]:
            lines.append(f"  @{t.get('author')}: {t.get('text', '')[:150]}")
        sections.append("=== SOCIAL MEDIA ===\n" + "\n".join(lines))

    # 5. Kontekst makro
    macro = load_json("macro_context.json")
    if macro:
        fng = macro.get("fear_and_greed", {})
        rates = macro.get("exchange_rates", {})
        glob = macro.get("global_crypto", {})
        lines = [
            f"  Fear & Greed: {fng.get('value')} ({fng.get('classification')})",
        ]
        if fng.get("interpretation"):
            lines.append(f"  Interpretacja: {fng['interpretation']}")
        if fng.get("trend"):
            lines.append(f"  Trend F&G: {fng['trend']}")
        lines.extend([
            f"  USD/PLN: {rates.get('usd_pln')}, EUR/PLN: {rates.get('eur_pln')}",
            f"  Globalna kap.: ${glob.get('total_market_cap_usd')}, BTC dom.: {glob.get('btc_dominance_pct')}%",
            f"  Zmiana kap. 24h: {glob.get('market_cap_change_24h_pct')}%",
        ])
        fng_hist = fng.get("history", [])
        if len(fng_hist) > 1:
            vals = [h["value"] for h in fng_hist]
            lines.append(f"  F&G historia (7d): {vals}")
        sections.append("=== KONTEKST MAKRO ===\n" + "\n".join(lines))

    full_context = "\n\n".join(sections)
    return _truncate(full_context, MAX_CONTEXT_CHARS)


SUMMARIZER_PROMPT = """ROLA: Jestes analitykiem rynku kryptowalut. Piszesz streszczenie surowych danych.

KRYTYCZNE ZASADY (BEZWZGLEDNIE PRZESTRZEGAJ):
- Korzystaj WYLACZNIE z danych podanych ponizej w sekcji "DANE".
- NIE wymyslaj ZADNYCH faktow, dat, cen, wartosci, zdarzen, newsow.
- Jesli czegoś nie ma w danych — napisz "brak danych" zamiast wymyslac.
- Kazda liczba (RSI, cena, procent, Fear & Greed) musi pochodzi DOKLADNIE z podanych danych.
- Dzisiejsza data jest podana w danych na samym poczatku — UZYWAJ JEJ, NIE WYMYSLAJ INNEJ.
- NIE dodawaj informacji o wydarzeniach, ktore nie sa wymienione w newsach.

ZADANIE: Napisz ZWIEZLE streszczenie (max 1000 slow) po polsku:
1. STAN RYNKU: trend i sentyment na podstawie Fear & Greed i zmian cen z DANYCH.
2. SYGNALY TECHNICZNE: RSI, MACD, Bollinger — podaj DOKLADNE wartosci z DANYCH.
3. KLUCZOWE NEWSY: tylko te ktore sa w sekcji NEWSY w DANYCH. Nie dodawaj wlasnych.
4. KONTEKST MAKRO: Fear & Greed, kursy walut — TYLKO z sekcji MAKRO w DANYCH.
5. PODSUMOWANIE: 3-5 wnioskow opartych WYLACZNIE o podane dane.

Odpowiadaj WYLACZNIE po polsku."""


def run() -> dict:
    """Uruchamia agenta sumaryzujacego."""
    print("[Agent Sumaryzujacy] Start...")
    collected_at = datetime.now(timezone.utc).isoformat()

    context = _build_context()
    if not context.strip():
        print("[Agent Sumaryzujacy] Brak danych do sumaryzacji!")
        return {"meta": {"collected_at": collected_at, "error": "no_data"}, "summary": ""}

    prompt = f"{SUMMARIZER_PROMPT}\n\n--- DANE ---\n{context}"

    print(f"  Wysylam do Ollama ({MODEL_NAME}), kontekst: {len(context)} znakow...")
    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            r = client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 2048},
                },
            )
            r.raise_for_status()
            response_text = r.json().get("response", "")
    except Exception as e:
        print(f"  [Ollama] Blad: {e}")
        response_text = f"Blad komunikacji z modelem: {e}"

    result = {
        "meta": {
            "collected_at": collected_at,
            "model": MODEL_NAME,
            "context_chars": len(context),
        },
        "summary": response_text,
    }

    path = save_json(result, "summary.json")
    print(f"[Agent Sumaryzujacy] Zapisano: {path} ({len(response_text)} znakow)")
    return result


if __name__ == "__main__":
    run()
