"""
Zbieranie danych kryptowalut w stylu Crypto Highlights (https://www.coingecko.com/en/highlights).

Źródła CoinGecko:
- /search/trending – gorące monety i kategorie (wyszukiwania z ostatnich 24h)
- /coins/categories – kategorie z kapitalizacją, wolumenem, zmianą 24h, top 3 monety
- /global – globalny przegląd rynku (dominacja BTC/ETH, łączna kapitalizacja)

Opcjonalnie: Binance (pary USDT). Klucz CoinGecko: COINGECKO_API_KEY (env lub domyślny).
"""

import json
import os
import time
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "data.json"

COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "CG-2Acrqo3uxa8J7z7fY6JRZQtV")
# Demo API (darmowy, klucz CG-...) = api.coingecko.com + x-cg-demo-api-key
# Pro API (płatny) = pro-api.coingecko.com + x-cg-pro-api-key. Ustaw COINGECKO_USE_PRO=1
COINGECKO_USE_PRO = os.environ.get("COINGECKO_USE_PRO", "").strip().lower() in ("1", "true", "yes")
if COINGECKO_USE_PRO and COINGECKO_API_KEY:
    COINGECKO_BASE_URL = "https://pro-api.coingecko.com/api/v3"
    COINGECKO_HEADER_KEY = "x-cg-pro-api-key"
else:
    COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
    COINGECKO_HEADER_KEY = "x-cg-demo-api-key" if COINGECKO_API_KEY else None
REQUEST_TIMEOUT = 30
COINGECKO_DELAY = 0.5 if COINGECKO_API_KEY else 1.5


def _coingecko_headers() -> dict:
    headers = {"Accept": "application/json"}
    if COINGECKO_HEADER_KEY and COINGECKO_API_KEY:
        headers[COINGECKO_HEADER_KEY] = COINGECKO_API_KEY
    return headers


def _get(url: str, params: dict | None = None) -> dict | list | None:
    """Wspólne GET do CoinGecko. Zwraca JSON lub None przy błędzie."""
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(url, params=params or {}, headers=_coingecko_headers())
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        print(f"  CoinGecko HTTP {e.response.status_code}: {url}")
        return None
    except Exception as e:
        print(f"  CoinGecko błąd: {e}")
        return None


def fetch_coingecko_trending(show_max: str = "coins,categories") -> dict:
    """
    Pobiera trending coins i kategorie (jak na stronie Highlights).
    Demo API: do 15 coinów, 6 kategorii. Pro API (COINGECKO_USE_PRO=1): show_max do 30/10.
    """
    url = f"{COINGECKO_BASE_URL}/search/trending"
    params = {}
    if COINGECKO_USE_PRO and COINGECKO_API_KEY and show_max:
        params["show_max"] = show_max
    raw = _get(url, params)
    if not raw:
        return {"coins": [], "categories": [], "nfts": []}

    # Ujednolicone trendy – monety
    coins_out = []
    for item in raw.get("coins", []):
        coin = item.get("item") or item
        data = coin.get("data") or {}
        price_ch = data.get("price_change_percentage_24h")
        if isinstance(price_ch, dict):
            ch_usd, ch_btc = price_ch.get("usd"), price_ch.get("btc")
        else:
            ch_usd, ch_btc = price_ch, None
        coins_out.append({
            "id": coin.get("id"),
            "name": coin.get("name"),
            "symbol": (coin.get("symbol") or "").upper(),
            "market_cap_rank": coin.get("market_cap_rank"),
            "score": coin.get("score"),
            "price_usd": data.get("price"),
            "price_btc": data.get("price_btc"),
            "market_cap": data.get("market_cap"),
            "volume_24h": data.get("total_volume"),
            "price_change_24h_usd_pct": ch_usd,
            "price_change_24h_btc_pct": ch_btc,
            "thumb": coin.get("thumb"),
            "slug": coin.get("slug"),
        })

    # Trendy – kategorie (nazwy / id)
    categories_out = []
    for cat in raw.get("categories", []):
        c = cat.get("item") or cat
        categories_out.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "market_cap_rank": c.get("market_cap_rank"),
            "score": c.get("score"),
        })

    return {"coins": coins_out, "categories": categories_out, "nfts": raw.get("nfts", [])}


def fetch_coingecko_categories(order: str = "market_cap_desc") -> list[dict]:
    """Pobiera listę kategorii z danymi rynkowymi (kapitalizacja, wolumen, zmiana 24h, top 3 monety)."""
    url = f"{COINGECKO_BASE_URL}/coins/categories"
    params = {"order": order}
    data = _get(url, params)
    if not data or not isinstance(data, list):
        return []

    return [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "market_cap": c.get("market_cap"),
            "market_cap_change_24h_pct": c.get("market_cap_change_24h"),
            "volume_24h": c.get("volume_24h"),
            "top_3_coins": c.get("top_3_coins") or [],
            "content": (c.get("content") or "")[:500],
            "updated_at": c.get("updated_at"),
        }
        for c in data
    ]


def fetch_coingecko_global() -> dict | None:
    """Pobiera globalny przegląd rynku: łączna kapitalizacja, dominacja BTC/ETH, liczba aktywnych walut."""
    url = f"{COINGECKO_BASE_URL}/global"
    data = _get(url)
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
        "updated_at": inner.get("updated_at"),
    }


def fetch_usd_pln_rate() -> float:
    """Pobiera aktualny kurs USD/PLN z darmowego API. Fallback: 4.05."""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get("https://api.nbp.pl/api/exchangerates/rates/a/usd/?format=json")
            r.raise_for_status()
            return float(r.json()["rates"][0]["mid"])
    except Exception:
        try:
            with httpx.Client(timeout=10) as client:
                r = client.get("https://open.er-api.com/v6/latest/USD")
                r.raise_for_status()
                return float(r.json().get("rates", {}).get("PLN", 4.05))
        except Exception:
            return 4.05


def fetch_coingecko_top_coins_pln(coin_ids: str = "bitcoin,ethereum,solana,cardano,ripple,dogecoin,polkadot,avalanche-2,chainlink,polygon") -> list[dict]:
    """Pobiera aktualne ceny top koinów w PLN i USD z CoinGecko /coins/markets."""
    url = f"{COINGECKO_BASE_URL}/coins/markets"
    params = {
        "vs_currency": "pln",
        "ids": coin_ids,
        "order": "market_cap_desc",
        "per_page": 20,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "1h,24h,7d,30d",
    }
    data = _get(url, params)
    if not data or not isinstance(data, list):
        return []

    result = []
    for c in data:
        result.append({
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
        })
    return result


def fetch_binance_klines(symbol: str = "BTCUSDT", interval: str = "1d", limit: int = 30) -> list[dict]:
    """Pobiera świece (klines) z Binance do obliczenia wskaźników technicznych."""
    url = "https://api.binance.com/api/v3/klines"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(url, params={"symbol": symbol, "interval": interval, "limit": limit})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"Binance klines {symbol}: {e}")
        return []

    return [
        {
            "open_time": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in data
    ]


def compute_technical_indicators(klines: list[dict]) -> dict:
    """Oblicza RSI(14), SMA(7), SMA(25), MACD z danych klines."""
    if len(klines) < 14:
        return {}

    closes = [k["close"] for k in klines]

    # SMA
    sma7 = sum(closes[-7:]) / 7 if len(closes) >= 7 else None
    sma25 = sum(closes[-25:]) / 25 if len(closes) >= 25 else None

    # RSI(14)
    gains, losses = [], []
    for i in range(1, min(15, len(closes))):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    avg_gain = sum(gains) / 14 if gains else 0
    avg_loss = sum(losses) / 14 if losses else 0.0001
    if len(closes) > 15:
        for i in range(15, len(closes)):
            delta = closes[i] - closes[i - 1]
            avg_gain = (avg_gain * 13 + max(delta, 0)) / 14
            avg_loss = (avg_loss * 13 + abs(min(delta, 0))) / 14
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    macd_val, signal_val, histogram = None, None, None
    if len(closes) >= 26:
        def ema(data, period):
            multiplier = 2 / (period + 1)
            result = [data[0]]
            for i in range(1, len(data)):
                result.append((data[i] - result[-1]) * multiplier + result[-1])
            return result

        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
        if len(macd_line) >= 9:
            signal_line = ema(macd_line, 9)
            macd_val = macd_line[-1]
            signal_val = signal_line[-1]
            histogram = macd_val - signal_val

    current_price = closes[-1]
    prev_price = closes[-2] if len(closes) >= 2 else current_price

    return {
        "current_price_usd": current_price,
        "prev_close_usd": prev_price,
        "rsi_14": round(rsi, 1),
        "sma_7": round(sma7, 2) if sma7 else None,
        "sma_25": round(sma25, 2) if sma25 else None,
        "macd": round(macd_val, 2) if macd_val is not None else None,
        "macd_signal": round(signal_val, 2) if signal_val is not None else None,
        "macd_histogram": round(histogram, 2) if histogram is not None else None,
        "price_vs_sma7": f"{((current_price / sma7) - 1) * 100:+.1f}%" if sma7 else None,
        "price_vs_sma25": f"{((current_price / sma25) - 1) * 100:+.1f}%" if sma25 else None,
    }


def fetch_technical_analysis(symbols: list[str] = None) -> dict[str, dict]:
    """Pobiera wskaźniki techniczne dla listy par Binance."""
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT",
                    "DOGEUSDT", "DOTUSDT", "AVAXUSDT", "LINKUSDT", "MATICUSDT"]
    result = {}
    for sym in symbols:
        klines = fetch_binance_klines(sym, interval="1d", limit=30)
        if klines:
            ta = compute_technical_indicators(klines)
            ta["symbol"] = sym.replace("USDT", "")
            result[sym] = ta
        time.sleep(0.1)
    return result


def fetch_binance_tickers() -> list[dict]:
    """Pobiera 24h tickery z Binance (pary *USDT). Bez klucza API."""
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"Binance błąd: {e}")
        return []

    # Tylko pary USDT
    out = []
    for t in data:
        symbol = t.get("symbol") or ""
        if not symbol.endswith("USDT"):
            continue
        base = symbol.replace("USDT", "")
        out.append({
            "source": "binance",
            "symbol": base,
            "pair": symbol,
            "last_price": float(t.get("lastPrice") or 0),
            "volume_24h": float(t.get("volume") or 0),
            "quote_volume_24h": float(t.get("quoteVolume") or 0),
            "price_change_pct": float(t.get("priceChangePercent") or 0),
            "high_24h": float(t.get("highPrice") or 0),
            "low_24h": float(t.get("lowPrice") or 0),
        })
    # Sortowanie po wolumenie (quote volume w USDT)
    out.sort(key=lambda x: x["quote_volume_24h"], reverse=True)
    return out[:150]  # top 150 par


def collect_and_save(
    include_binance: bool = True,
    trending_show_max: str = "coins,categories",
) -> None:
    """Pobiera dane w stylu Crypto Highlights i zapisuje do data.json."""
    from datetime import datetime, timezone

    result = {
        "meta": {
            "sources": ["coingecko_trending", "coingecko_categories", "coingecko_global"],
            "collected_at": datetime.now(timezone.utc).isoformat(),
        },
        "trending": {"coins": [], "categories": []},
        "categories": [],
        "global": {},
        "binance": [],
    }

    # 1. Trending (gorące monety i kategorie z ostatnich 24h)
    print("Pobieram CoinGecko (trending / highlights)...")
    trending = fetch_coingecko_trending(show_max=trending_show_max)
    result["trending"]["coins"] = trending["coins"]
    result["trending"]["categories"] = trending["categories"]
    print(f"  → {len(trending['coins'])} trending coins, {len(trending['categories'])} trending categories")
    time.sleep(COINGECKO_DELAY)

    # 2. Kategorie z danymi rynkowymi
    print("Pobieram CoinGecko (categories)...")
    result["categories"] = fetch_coingecko_categories(order="market_cap_desc")
    print(f"  → {len(result['categories'])} kategorii")
    time.sleep(COINGECKO_DELAY)

    # 3. Global market overview
    print("Pobieram CoinGecko (global)...")
    global_data = fetch_coingecko_global()
    if global_data:
        result["global"] = global_data
        print("  → OK (kapitalizacja, dominacja BTC/ETH)")
    else:
        print("  → brak danych")
    time.sleep(COINGECKO_DELAY)

    # 4. Opcjonalnie Binance
    if include_binance:
        print("Pobieram Binance (ticker 24h)...")
        result["binance"] = fetch_binance_tickers()
        result["meta"]["sources"].append("binance")
        print(f"  → {len(result['binance'])} par USDT")

    OUTPUT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Zapisano: {OUTPUT_FILE}")


if __name__ == "__main__":
    collect_and_save(
        include_binance=True,
        trending_show_max="coins,categories",
    )
