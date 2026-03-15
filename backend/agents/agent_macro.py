"""
Agent Makro — Fear & Greed Index, kursy walut, dane globalne.
Wynik: data/macro_context.json
"""

import time
from datetime import datetime, timezone

import httpx

from .config import (
    COINGECKO_BASE_URL, COINGECKO_DELAY, REQUEST_TIMEOUT,
    coingecko_get, save_json,
)


def fetch_fear_and_greed() -> dict:
    """Fear & Greed Index z alternative.me (darmowe API)."""
    url = "https://api.alternative.me/fng/?limit=7&format=json"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"  [Fear&Greed] {e}")
        return {"value": None, "classification": "unknown", "history": []}

    entries = data.get("data", [])
    if not entries:
        return {"value": None, "classification": "unknown", "history": []}

    current = entries[0]
    current_val = int(current.get("value", 0))
    history = [
        {
            "value": int(e.get("value", 0)),
            "classification": e.get("value_classification", ""),
            "timestamp": e.get("timestamp", ""),
        }
        for e in entries
    ]

    # Interpretacja trendu F&G
    trend_text = ""
    if len(history) >= 2:
        week_ago_val = history[-1]["value"]
        diff = current_val - week_ago_val
        if diff > 10:
            trend_text = f"ROSNIE (z {week_ago_val} do {current_val}, +{diff} w 7 dni) — sentyment sie poprawia"
        elif diff < -10:
            trend_text = f"SPADA (z {week_ago_val} do {current_val}, {diff} w 7 dni) — sentyment sie pogarsza"
        else:
            trend_text = f"STABILNY (z {week_ago_val} do {current_val}, {diff:+d} w 7 dni)"

    interpretation = ""
    if current_val <= 25:
        interpretation = "EXTREME FEAR — rynek bardzo wyprzedany, historycznie dobry moment na zakup"
    elif current_val <= 45:
        interpretation = "FEAR — inwestorzy sa ostrozni, mozliwe okazje"
    elif current_val <= 55:
        interpretation = "NEUTRALNY — rynek w rownowadze"
    elif current_val <= 75:
        interpretation = "GREED — optymizm rosnie, uwaga na przegrzanie"
    else:
        interpretation = "EXTREME GREED — rynek moze byc przegrzany, ryzyko korekty"

    return {
        "value": current_val,
        "classification": current.get("value_classification", "unknown"),
        "interpretation": interpretation,
        "trend": trend_text,
        "timestamp": current.get("timestamp", ""),
        "history": history,
    }


def fetch_usd_pln() -> float:
    """Kurs USD/PLN."""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get("https://api.nbp.pl/api/exchangerates/rates/a/usd/?format=json")
            r.raise_for_status()
            return float(r.json()["rates"][0]["mid"])
    except Exception:
        pass
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get("https://open.er-api.com/v6/latest/USD")
            r.raise_for_status()
            return float(r.json().get("rates", {}).get("PLN", 4.05))
    except Exception:
        return 4.05


def fetch_eur_pln() -> float:
    """Kurs EUR/PLN."""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get("https://api.nbp.pl/api/exchangerates/rates/a/eur/?format=json")
            r.raise_for_status()
            return float(r.json()["rates"][0]["mid"])
    except Exception:
        return 4.30


def fetch_global_crypto() -> dict:
    """Globalne dane krypto (kapitalizacja, dominacja BTC)."""
    url = f"{COINGECKO_BASE_URL}/global"
    data = coingecko_get(url)
    if not data or not isinstance(data, dict):
        return {}
    inner = data.get("data", data)
    return {
        "total_market_cap_usd": inner.get("total_market_cap", {}).get("usd"),
        "total_volume_24h_usd": inner.get("total_volume", {}).get("usd"),
        "btc_dominance_pct": inner.get("market_cap_percentage", {}).get("btc"),
        "eth_dominance_pct": inner.get("market_cap_percentage", {}).get("eth"),
        "market_cap_change_24h_pct": inner.get("market_cap_change_percentage_24h_usd"),
        "active_cryptocurrencies": inner.get("active_cryptocurrencies"),
    }


def run() -> dict:
    """Uruchamia agenta makro."""
    print("[Agent Makro] Start...")
    collected_at = datetime.now(timezone.utc).isoformat()

    print("  Fear & Greed Index...")
    fng = fetch_fear_and_greed()
    print(f"  -> {fng.get('value')} ({fng.get('classification')})")

    print("  Kursy walut...")
    usd_pln = fetch_usd_pln()
    eur_pln = fetch_eur_pln()
    print(f"  -> USD/PLN={usd_pln}, EUR/PLN={eur_pln}")

    print("  Globalne dane krypto...")
    time.sleep(COINGECKO_DELAY)
    global_crypto = fetch_global_crypto()

    result = {
        "meta": {"collected_at": collected_at},
        "fear_and_greed": fng,
        "exchange_rates": {
            "usd_pln": usd_pln,
            "eur_pln": eur_pln,
        },
        "global_crypto": global_crypto,
    }

    path = save_json(result, "macro_context.json")
    print(f"[Agent Makro] Zapisano: {path}")
    return result


if __name__ == "__main__":
    run()
