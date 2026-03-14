"""
Agent Rynkowy — ceny PLN/USD, wolumeny, globalne dane, Binance tickery.
Wynik: data/market_prices.json
"""

import time
from datetime import datetime, timezone

import httpx

from .config import (
    COINGECKO_BASE_URL, COINGECKO_DELAY, REQUEST_TIMEOUT,
    BINANCE_BASE_URL, TOP_COIN_IDS,
    coingecko_get, save_json,
)


def fetch_usd_pln_rate() -> float:
    """Kurs USD/PLN z NBP, fallback open.er-api.com, domyslnie 4.05."""
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


def fetch_top_coins_pln(coin_ids: str = TOP_COIN_IDS) -> list[dict]:
    """Aktualne ceny top koinow w PLN z CoinGecko /coins/markets."""
    url = f"{COINGECKO_BASE_URL}/coins/markets"
    params = {
        "vs_currency": "pln",
        "ids": coin_ids,
        "order": "market_cap_desc",
        "per_page": 25,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "1h,24h,7d,30d",
    }
    data = coingecko_get(url, params)
    if not data or not isinstance(data, list):
        return []
    return [
        {
            "id": c.get("id"),
            "symbol": (c.get("symbol") or "").upper(),
            "name": c.get("name"),
            "price_pln": c.get("current_price"),
            "market_cap_pln": c.get("market_cap"),
            "volume_24h_pln": c.get("total_volume"),
            "price_change_1h_pct": c.get("price_change_percentage_1h_in_currency"),
            "price_change_24h_pct": c.get("price_change_percentage_24h_in_currency"),
            "price_change_7d_pct": c.get("price_change_percentage_7d_in_currency"),
            "price_change_30d_pct": c.get("price_change_percentage_30d_in_currency"),
            "ath_pln": c.get("ath"),
            "ath_change_pct": c.get("ath_change_percentage"),
            "ath_date": c.get("ath_date"),
            "high_24h_pln": c.get("high_24h"),
            "low_24h_pln": c.get("low_24h"),
            "circulating_supply": c.get("circulating_supply"),
            "max_supply": c.get("max_supply"),
            "market_cap_rank": c.get("market_cap_rank"),
        }
        for c in data
    ]


def fetch_top_coins_usd(coin_ids: str = TOP_COIN_IDS) -> list[dict]:
    """Aktualne ceny top koinow w USD z CoinGecko /coins/markets."""
    url = f"{COINGECKO_BASE_URL}/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": coin_ids,
        "order": "market_cap_desc",
        "per_page": 25,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "1h,24h,7d",
    }
    data = coingecko_get(url, params)
    if not data or not isinstance(data, list):
        return []
    return [
        {
            "id": c.get("id"),
            "symbol": (c.get("symbol") or "").upper(),
            "price_usd": c.get("current_price"),
            "market_cap_usd": c.get("market_cap"),
            "volume_24h_usd": c.get("total_volume"),
        }
        for c in data
    ]


def fetch_global() -> dict | None:
    """Globalny przeglad rynku: kapitalizacja, dominacja BTC/ETH."""
    url = f"{COINGECKO_BASE_URL}/global"
    data = coingecko_get(url)
    if not data or not isinstance(data, dict):
        return None
    inner = data.get("data", data)
    return {
        "total_market_cap_usd": inner.get("total_market_cap", {}).get("usd"),
        "total_volume_usd": inner.get("total_volume", {}).get("usd"),
        "market_cap_percentage_btc": inner.get("market_cap_percentage", {}).get("btc"),
        "market_cap_percentage_eth": inner.get("market_cap_percentage", {}).get("eth"),
        "market_cap_change_24h_pct": inner.get("market_cap_change_percentage_24h_usd"),
        "active_cryptocurrencies": inner.get("active_cryptocurrencies"),
        "markets": inner.get("markets"),
    }


def fetch_binance_tickers_top(limit: int = 30) -> list[dict]:
    """Top tickery Binance (pary USDT) po wolumenie."""
    url = f"{BINANCE_BASE_URL}/ticker/24hr"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"  [Binance] {e}")
        return []

    out = []
    for t in data:
        symbol = t.get("symbol") or ""
        if not symbol.endswith("USDT"):
            continue
        out.append({
            "symbol": symbol.replace("USDT", ""),
            "pair": symbol,
            "last_price_usd": float(t.get("lastPrice") or 0),
            "volume_24h": float(t.get("volume") or 0),
            "quote_volume_24h_usd": float(t.get("quoteVolume") or 0),
            "price_change_pct_24h": float(t.get("priceChangePercent") or 0),
            "high_24h_usd": float(t.get("highPrice") or 0),
            "low_24h_usd": float(t.get("lowPrice") or 0),
        })
    out.sort(key=lambda x: x["quote_volume_24h_usd"], reverse=True)
    return out[:limit]


def run() -> dict:
    """Uruchamia agenta rynkowego i zwraca wynik."""
    print("[Agent Rynkowy] Start...")
    collected_at = datetime.now(timezone.utc).isoformat()

    print("  Kurs USD/PLN...")
    usd_pln = fetch_usd_pln_rate()
    print(f"  -> USD/PLN = {usd_pln}")

    print("  Ceny top koinow (PLN)...")
    coins_pln = fetch_top_coins_pln()
    print(f"  -> {len(coins_pln)} koinow")
    time.sleep(COINGECKO_DELAY)

    print("  Ceny top koinow (USD)...")
    coins_usd = fetch_top_coins_usd()
    print(f"  -> {len(coins_usd)} koinow")
    time.sleep(COINGECKO_DELAY)

    usd_map = {c["id"]: c for c in coins_usd}
    for coin in coins_pln:
        usd_data = usd_map.get(coin["id"], {})
        coin["price_usd"] = usd_data.get("price_usd")
        coin["market_cap_usd"] = usd_data.get("market_cap_usd")
        coin["volume_24h_usd"] = usd_data.get("volume_24h_usd")

    print("  Dane globalne...")
    global_data = fetch_global() or {}
    time.sleep(COINGECKO_DELAY)

    print("  Binance tickery...")
    binance = fetch_binance_tickers_top(30)
    print(f"  -> {len(binance)} par")

    result = {
        "meta": {"collected_at": collected_at, "usd_pln_rate": usd_pln},
        "coins": coins_pln,
        "global": global_data,
        "binance_top": binance,
    }

    path = save_json(result, "market_prices.json")
    print(f"[Agent Rynkowy] Zapisano: {path}")
    return result


if __name__ == "__main__":
    run()
