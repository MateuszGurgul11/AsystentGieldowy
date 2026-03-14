"""
Agent Techniczny — RSI, MACD, SMA, Bollinger Bands, wieloramowy (1d + 4h).
Wynik: data/technical_analysis.json
"""

import time
from datetime import datetime, timezone

import httpx

from .config import (
    BINANCE_BASE_URL, REQUEST_TIMEOUT, TOP_BINANCE_SYMBOLS, save_json,
)


def fetch_klines(symbol: str, interval: str = "1d", limit: int = 60) -> list[dict]:
    """Swiece z Binance."""
    url = f"{BINANCE_BASE_URL}/klines"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(url, params={"symbol": symbol, "interval": interval, "limit": limit})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"  [Binance klines] {symbol} {interval}: {e}")
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


def _ema(data: list[float], period: int) -> list[float]:
    multiplier = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append((data[i] - result[-1]) * multiplier + result[-1])
    return result


def compute_indicators(klines: list[dict]) -> dict:
    """RSI(14), MACD(12,26,9), SMA(7,25,50,200), Bollinger Bands(20,2), interpretacja."""
    if len(klines) < 14:
        return {}

    closes = [k["close"] for k in klines]

    # --- SMA ---
    def sma(n):
        return round(sum(closes[-n:]) / n, 4) if len(closes) >= n else None

    sma7, sma25, sma50, sma200 = sma(7), sma(25), sma(50), sma(200)

    # --- RSI(14) ---
    gains, losses = [], []
    for i in range(1, min(15, len(closes))):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(abs(min(d, 0)))
    avg_gain = sum(gains) / 14 if gains else 0
    avg_loss = sum(losses) / 14 if losses else 0.0001
    if len(closes) > 15:
        for i in range(15, len(closes)):
            d = closes[i] - closes[i - 1]
            avg_gain = (avg_gain * 13 + max(d, 0)) / 14
            avg_loss = (avg_loss * 13 + abs(min(d, 0))) / 14
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi = round(100 - (100 / (1 + rs)), 1)

    # --- MACD(12,26,9) ---
    macd_val, signal_val, histogram = None, None, None
    if len(closes) >= 26:
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
        if len(macd_line) >= 9:
            signal_line = _ema(macd_line, 9)
            macd_val = round(macd_line[-1], 4)
            signal_val = round(signal_line[-1], 4)
            histogram = round(macd_val - signal_val, 4)

    # --- Bollinger Bands(20,2) ---
    bb_upper, bb_lower, bb_middle = None, None, None
    if len(closes) >= 20:
        bb_middle = sum(closes[-20:]) / 20
        variance = sum((c - bb_middle) ** 2 for c in closes[-20:]) / 20
        std_dev = variance ** 0.5
        bb_upper = round(bb_middle + 2 * std_dev, 4)
        bb_lower = round(bb_middle - 2 * std_dev, 4)
        bb_middle = round(bb_middle, 4)

    current = closes[-1]

    # --- Interpretacja sygnalow ---
    signals = []
    if rsi > 70:
        signals.append("RSI > 70: WYKUPIENIE (potencjalna sprzedaz)")
    elif rsi < 30:
        signals.append("RSI < 30: WYPRZEDANIE (potencjalny zakup)")
    else:
        signals.append(f"RSI = {rsi}: neutralny")

    if macd_val is not None and signal_val is not None:
        if histogram and histogram > 0:
            signals.append("MACD > Signal: sygnal KUPNA")
        elif histogram and histogram < 0:
            signals.append("MACD < Signal: sygnal SPRZEDAZY")

    if sma7 and sma25:
        if sma7 > sma25:
            signals.append("SMA7 > SMA25: trend wzrostowy (krotkoterminowy)")
        else:
            signals.append("SMA7 < SMA25: trend spadkowy (krotkoterminowy)")

    if bb_upper and bb_lower:
        if current >= bb_upper:
            signals.append("Cena przy gornym Bollingerze: moze byc wykupiony")
        elif current <= bb_lower:
            signals.append("Cena przy dolnym Bollingerze: moze byc wyprzedany")

    overall = "NEUTRALNY"
    buy_signals = sum(1 for s in signals if "zakup" in s.lower() or "kupna" in s.lower() or "wzrostowy" in s.lower() or "wyprzedany" in s.lower())
    sell_signals = sum(1 for s in signals if "sprzedaz" in s.lower() or "spadkowy" in s.lower() or "wykupiony" in s.lower() or "wykupienie" in s.lower())
    if buy_signals > sell_signals:
        overall = "KUPNO"
    elif sell_signals > buy_signals:
        overall = "SPRZEDAZ"

    return {
        "current_price_usd": current,
        "rsi_14": rsi,
        "sma_7": sma7, "sma_25": sma25, "sma_50": sma50, "sma_200": sma200,
        "macd": macd_val, "macd_signal": signal_val, "macd_histogram": histogram,
        "bollinger_upper": bb_upper, "bollinger_middle": bb_middle, "bollinger_lower": bb_lower,
        "signals": signals,
        "overall": overall,
    }


def run() -> dict:
    """Uruchamia agenta technicznego dla wielu timeframe'ow."""
    print("[Agent Techniczny] Start...")
    collected_at = datetime.now(timezone.utc).isoformat()
    analysis = {}

    for sym in TOP_BINANCE_SYMBOLS:
        coin_name = sym.replace("USDT", "")
        coin_data = {"symbol": coin_name}

        for interval, label in [("1d", "daily"), ("4h", "4h")]:
            limit = 60 if interval == "1d" else 100
            klines = fetch_klines(sym, interval=interval, limit=limit)
            if klines:
                indicators = compute_indicators(klines)
                coin_data[label] = indicators
            else:
                coin_data[label] = {}
            time.sleep(0.1)

        analysis[coin_name] = coin_data
        print(f"  {coin_name}: daily={coin_data.get('daily', {}).get('overall', '?')}, "
              f"4h={coin_data.get('4h', {}).get('overall', '?')}")

    result = {
        "meta": {"collected_at": collected_at, "timeframes": ["1d", "4h"]},
        "analysis": analysis,
    }

    path = save_json(result, "technical_analysis.json")
    print(f"[Agent Techniczny] Zapisano: {path}")
    return result


if __name__ == "__main__":
    run()
