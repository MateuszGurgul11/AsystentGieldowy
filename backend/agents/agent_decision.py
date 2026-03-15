"""
Agent Decyzyjny — 3 strategie inwestycyjne na podstawie pelnej analizy rynku.

Python pre-compute: ranking WSZYSTKICH koinow, 3 portfele (konserwatywny/zbalansowany/agresywny),
obliczenie jednostek, stop-loss, take-profit.
LLM: uzasadnienie, ocena ryzyka, scenariusze.
"""

from datetime import datetime, timezone

import httpx

from .config import (
    OLLAMA_URL, MODEL_NAME, OLLAMA_TIMEOUT, BUDGET_PLN,
    load_json, save_json,
)


# ---------------------------------------------------------------------------
# Formalny scoring -2/+2 per wskaznik
# ---------------------------------------------------------------------------

def _compute_formal_score(daily: dict, h4: dict, fng_value: int | None) -> tuple[int, str, list[str]]:
    """
    Oblicza formalny score dla coina.
    Zwraca: (score, decision, breakdown_lines)
    Skala per wskaznik: -2 do +2, laczny zakres ok. -10 do +10.
    """
    score = 0
    breakdown = []

    # 1. RSI daily
    rsi = daily.get("rsi_14", 50)
    if rsi < 30:
        pts = 2
    elif rsi < 45:
        pts = 1
    elif rsi > 70:
        pts = -2
    elif rsi > 55:
        pts = -1
    else:
        pts = 0
    score += pts
    breakdown.append(f"RSI({pts:+d})")

    # 2. MACD histogram daily
    hist = daily.get("macd_histogram")
    if hist is not None and hist > 0:
        pts = 1
    elif hist is not None and hist < 0:
        pts = -1
    else:
        pts = 0
    score += pts
    breakdown.append(f"MACD({pts:+d})")

    # 3. EMA 200 (trend dlugoterminowy)
    ema200 = daily.get("ema_200")
    price = daily.get("current_price_usd", 0)
    if ema200 and price > ema200:
        pts = 1
    elif ema200 and price < ema200:
        pts = -1
    else:
        pts = 0
    score += pts
    breakdown.append(f"EMA200({pts:+d})")

    # 4. EMA 50 (trend srednioterminowy)
    ema50 = daily.get("ema_50")
    if ema50 and price > ema50:
        pts = 1
    elif ema50 and price < ema50:
        pts = -1
    else:
        pts = 0
    score += pts
    breakdown.append(f"EMA50({pts:+d})")

    # 5. Bollinger Bands
    bb_lower = daily.get("bollinger_lower")
    bb_upper = daily.get("bollinger_upper")
    pts = 0
    if bb_lower and price <= bb_lower:
        pts = 1
    elif bb_upper and price >= bb_upper:
        pts = -1
    score += pts
    breakdown.append(f"BB({pts:+d})")

    # 6. Fear & Greed (kontrarianski)
    pts = 0
    if fng_value is not None:
        if fng_value < 20:
            pts = 1
        elif fng_value > 80:
            pts = -1
    score += pts
    breakdown.append(f"F&G({pts:+d})")

    # 7. RSI 4h (potwierdzenie krotkoterminowe)
    rsi_4h = h4.get("rsi_14", 50)
    if rsi_4h < 35:
        pts = 1
    elif rsi_4h > 65:
        pts = -1
    else:
        pts = 0
    score += pts
    breakdown.append(f"4hRSI({pts:+d})")

    # Decyzja
    if score >= 3:
        decision = "BUY"
    elif score <= -3:
        decision = "SELL"
    else:
        decision = "HOLD"

    return score, decision, breakdown


# ---------------------------------------------------------------------------
# Analiza i scoring WSZYSTKICH koinow
# ---------------------------------------------------------------------------

def _score_all_coins() -> list[dict]:
    """
    Analizuje WSZYSTKIE dostepne coiny, oblicza formalny score i zwraca posortowana liste.
    """
    market = load_json("market_prices.json")
    ta = load_json("technical_analysis.json")
    macro = load_json("macro_context.json")
    if not market:
        return []

    coins = market.get("coins", [])
    analysis = ta.get("analysis", {}) if ta else {}
    usd_pln_rate = market.get("meta", {}).get("usd_pln_rate", 4.0)

    fng_value = None
    if macro:
        fng_value = macro.get("fear_and_greed", {}).get("value")

    scored = []
    for coin in coins:
        symbol = coin.get("symbol", "")
        price_pln = coin.get("price_pln")
        if not price_pln or price_pln <= 0:
            continue

        ta_data = analysis.get(symbol, {})
        daily = ta_data.get("daily", {})
        h4 = ta_data.get("4h", {})

        overall_d = daily.get("overall", "NEUTRALNY")
        overall_4h = h4.get("overall", "NEUTRALNY")

        formal_score, decision, breakdown = _compute_formal_score(daily, h4, fng_value)

        rank = coin.get("market_cap_rank") or 100

        ch_7d = abs(coin.get("price_change_7d_pct") or 0)
        ch_30d = abs(coin.get("price_change_30d_pct") or 0)
        volatility = (ch_7d + ch_30d / 4) / 2

        if rank <= 2:
            risk_class = "niski"
        elif rank <= 8:
            risk_class = "sredni"
        else:
            risk_class = "wysoki"

        # Stop-loss / Take-profit (bazowe, na podstawie Bollinger)
        bb_lower = daily.get("bollinger_lower")
        bb_upper = daily.get("bollinger_upper")

        if bb_lower and usd_pln_rate:
            sl_pln = round(bb_lower * usd_pln_rate, 2)
            sl_pct = round((sl_pln / price_pln - 1) * 100, 1)
            if sl_pct > -3:
                sl_pln = round(price_pln * 0.90, 2)
                sl_pct = -10.0
        else:
            sl_pln = round(price_pln * 0.90, 2)
            sl_pct = -10.0

        if bb_upper and usd_pln_rate:
            tp_pln = round(bb_upper * usd_pln_rate, 2)
            tp_pct = round((tp_pln / price_pln - 1) * 100, 1)
            if tp_pct < 3:
                tp_pln = round(price_pln * 1.20, 2)
                tp_pct = 20.0
        else:
            tp_pln = round(price_pln * 1.20, 2)
            tp_pct = 20.0

        scored.append({
            "symbol": symbol,
            "name": coin.get("name"),
            "price_pln": price_pln,
            "price_usd": coin.get("price_usd"),
            "market_cap_rank": rank,
            "score": formal_score,
            "decision": decision,
            "score_breakdown": breakdown,
            "score_text": " + ".join(breakdown) + f" = {formal_score:+d} -> {decision}",
            "risk_class": risk_class,
            "volatility": round(volatility, 1),
            "ta_signal_daily": overall_d,
            "ta_signal_4h": overall_4h,
            "rsi_daily": daily.get("rsi_14"),
            "rsi_4h": h4.get("rsi_14"),
            "macd_hist_daily": daily.get("macd_histogram"),
            "ema_50": daily.get("ema_50"),
            "ema_200": daily.get("ema_200"),
            "signals_daily": daily.get("signals", []),
            "bb_lower": bb_lower,
            "bb_upper": bb_upper,
            "sma_7": daily.get("sma_7"),
            "sma_25": daily.get("sma_25"),
            "sma_50": daily.get("sma_50"),
            "sma_200": daily.get("sma_200"),
            "stop_loss_pln": sl_pln,
            "stop_loss_pct": sl_pct,
            "take_profit_pln": tp_pln,
            "take_profit_pct": tp_pct,
            "change_1h": coin.get("price_change_1h_pct"),
            "change_24h": coin.get("price_change_24h_pct"),
            "change_7d": coin.get("price_change_7d_pct"),
            "change_30d": coin.get("price_change_30d_pct"),
            "ath_pln": coin.get("ath_pln"),
            "ath_change_pct": coin.get("ath_change_pct"),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Budowanie 3 strategii
# ---------------------------------------------------------------------------

def _build_strategy(scored_coins: list[dict], strategy_type: str) -> dict:
    """
    Buduje portfel dla danej strategii z limitami pozycji.
    Max alokacja na 1 coin: konserwatywna 40%, zbalansowana 30%, agresywna 25%.
    """
    configs = {
        "konserwatywna": {
            "count": 3,
            "filter": lambda c: c["market_cap_rank"] <= 10,
            "horizon": "1 tydzien",
            "description": "Niskoryzykowna, krotkoterminowa (7 dni). Tylko top coiny z silnym TA.",
            "sl_mult": 0.95,
            "tp_mult": 1.10,
            "max_pct": 0.40,
        },
        "zbalansowana": {
            "count": 5,
            "filter": lambda c: True,
            "horizon": "1 miesiac",
            "description": "Zrownowazony risk/reward, srednioterminowa (30 dni). Mix duzych i srednich.",
            "sl_mult": 0.90,
            "tp_mult": 1.20,
            "max_pct": 0.30,
        },
        "agresywna": {
            "count": 7,
            "filter": lambda c: True,
            "horizon": "1 miesiac",
            "description": "Wysoki potencjal zysku, wysze ryzyko (30 dni). Wiecej altcoinow.",
            "sl_mult": 0.85,
            "tp_mult": 1.35,
            "max_pct": 0.25,
        },
    }

    cfg = configs[strategy_type]
    candidates = [c for c in scored_coins if cfg["filter"](c)]
    selected = candidates[:cfg["count"]]

    if not selected:
        return {"name": strategy_type, "coins": [], "error": "brak kandydatow"}

    max_alloc = round(BUDGET_PLN * cfg["max_pct"])
    min_alloc = 200

    # Alokacja proporcjonalna do score z clamp do max_pct
    raw_scores = [max(c["score"] + 5, 1) for c in selected]
    total_raw = sum(raw_scores)

    raw_allocs = []
    for rs in raw_scores:
        alloc = round(BUDGET_PLN * rs / total_raw)
        alloc = min(alloc, max_alloc)
        alloc = max(alloc, min_alloc)
        raw_allocs.append(alloc)

    # Normalizuj aby suma == BUDGET_PLN
    diff = BUDGET_PLN - sum(raw_allocs)
    if diff != 0:
        raw_allocs[-1] += diff

    remaining = BUDGET_PLN
    allocations = []

    for i, coin in enumerate(selected):
        if i < len(selected) - 1:
            alloc = raw_allocs[i]
            remaining -= alloc
        else:
            alloc = remaining

        price = coin["price_pln"]
        units = alloc / price

        sl_pln = round(price * cfg["sl_mult"], 2)
        sl_pct = round((cfg["sl_mult"] - 1) * 100, 1)
        tp_pln = round(price * cfg["tp_mult"], 2)
        tp_pct = round((cfg["tp_mult"] - 1) * 100, 1)

        if coin.get("stop_loss_pct") and coin["stop_loss_pct"] < sl_pct:
            sl_pln = coin["stop_loss_pln"]
            sl_pct = coin["stop_loss_pct"]
        if coin.get("take_profit_pct") and coin["take_profit_pct"] > tp_pct:
            tp_pln = coin["take_profit_pln"]
            tp_pct = coin["take_profit_pct"]

        allocations.append({
            **coin,
            "alloc_pln": alloc,
            "alloc_pct": round(alloc / BUDGET_PLN * 100, 1),
            "units": units,
            "strategy_sl_pln": sl_pln,
            "strategy_sl_pct": sl_pct,
            "strategy_tp_pln": tp_pln,
            "strategy_tp_pct": tp_pct,
        })

    return {
        "name": strategy_type,
        "description": cfg["description"],
        "horizon": cfg["horizon"],
        "coin_count": len(allocations),
        "max_position_pct": cfg["max_pct"] * 100,
        "coins": allocations,
    }


# ---------------------------------------------------------------------------
# Pobieranie newsow per-coin (bez limitu 3)
# ---------------------------------------------------------------------------

def _get_coin_news(symbol: str) -> list[str]:
    """Pobiera WSZYSTKIE naglowki newsow dotyczacych danego coina."""
    news = load_json("news_digest.json")
    if not news:
        return []
    results = []
    for a in news.get("articles", []):
        mentioned = a.get("mentioned_coins", [])
        if symbol in mentioned:
            results.append(f"[{a.get('source', '?')}] {a.get('title', '')}")
    return results


# ---------------------------------------------------------------------------
# Formatowanie danych
# ---------------------------------------------------------------------------

def _fmt_pct(val) -> str:
    if val is None:
        return "?"
    return f"{val:+.1f}%"


def _compute_confidence(scored_coins: list[dict]) -> tuple[str, float]:
    """Oblicza poziom pewnosci na podstawie sredniego score."""
    all_scores = [c["score"] for c in scored_coins if c["score"] is not None]
    if not all_scores:
        return "niska", 0.0
    avg = sum(all_scores) / len(all_scores)
    if avg > 4:
        return "wysoka", avg
    elif avg >= 2:
        return "srednia", avg
    return "niska", avg


def _compute_scenarios(strategy: dict) -> dict:
    """Oblicza scenariusze w Pythonie na podstawie TP/SL i zmian historycznych."""
    coins = strategy.get("coins", [])
    if not coins:
        return {"optymistyczny": BUDGET_PLN, "realistyczny": BUDGET_PLN, "pesymistyczny": BUDGET_PLN}

    opt_val, real_val, pess_val = 0, 0, 0
    for c in coins:
        alloc = c["alloc_pln"]
        tp_pct = abs(c["strategy_tp_pct"]) / 100
        sl_pct = abs(c["strategy_sl_pct"]) / 100
        ch_7d = (c.get("change_7d") or 0) / 100

        opt_val += alloc * (1 + tp_pct * 0.5)
        real_val += alloc * (1 + ch_7d * 0.3)
        pess_val += alloc * (1 - sl_pct * 0.5)

    return {
        "optymistyczny": round(opt_val),
        "realistyczny": round(real_val),
        "pesymistyczny": round(pess_val),
    }


# ---------------------------------------------------------------------------
# Generowanie CALEGO raportu w Pythonie (zero halucynacji)
# ---------------------------------------------------------------------------

def _generate_data_report(scored_coins: list[dict], strategies: list[dict]) -> str:
    """
    Generuje KOMPLETNY raport inwestycyjny w Pythonie.
    Wszystkie liczby, daty, tabele pochodza z danych — zero LLM.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    R = []

    # --- Naglowek ---
    R.append("# RAPORT INWESTYCYJNY KRYPTOWALUT")
    R.append(f"**Data analizy: {now}**")
    R.append(f"**Budzet inwestycyjny: {BUDGET_PLN:,} PLN**")
    R.append("")

    # --- 0. Zrodla danych ---
    R.append("## 0. ZRODLA DANYCH")
    R.append("- CoinGecko API — ceny, kapitalizacja, wolumen, zmiany procentowe, ATH")
    R.append("- Binance API — swiece (klines) 1d i 4h do analizy technicznej")
    R.append("- alternative.me — Fear & Greed Index (sentyment rynku)")
    R.append("- NBP / open.er-api.com — kursy walut (USD/PLN, EUR/PLN)")
    R.append("- RSS (CoinDesk, CoinTelegraph, The Block) — artykuly i newsy")
    R.append("- Wskazniki: RSI(14), MACD(12,26,9), SMA(7,25,50,200), EMA(50,200), Bollinger Bands(20,2)")
    R.append("- Scoring: formalny system -2/+2 per wskaznik (7 wskaznikow, zakres -10 do +10)")
    R.append("")

    # --- 1. Ocena rynku (dane z macro + scoring) ---
    R.append("## 1. OCENA RYNKU")

    macro = load_json("macro_context.json")
    if macro:
        fng = macro.get("fear_and_greed", {})
        rates = macro.get("exchange_rates", {})
        glob = macro.get("global_crypto", {})

        fng_val = fng.get("value", "?")
        fng_class = fng.get("classification", "?")
        R.append(f"**Fear & Greed Index: {fng_val} ({fng_class})**")
        if fng.get("interpretation"):
            R.append(f"Interpretacja: {fng['interpretation']}")
        if fng.get("trend"):
            R.append(f"Trend: {fng['trend']}")

        cap = glob.get("total_market_cap_usd")
        if cap:
            R.append(f"Globalna kapitalizacja: ${cap / 1e12:.2f}T")
        btc_dom = glob.get("btc_dominance_pct")
        if btc_dom:
            R.append(f"Dominacja BTC: {btc_dom}%")
        cap_ch = glob.get("market_cap_change_24h_pct")
        if cap_ch:
            R.append(f"Zmiana kapitalizacji 24h: {cap_ch:+.2f}%")

        R.append(f"Kurs USD/PLN: {rates.get('usd_pln', '?')} | EUR/PLN: {rates.get('eur_pln', '?')}")

    buy_count = sum(1 for c in scored_coins if c["decision"] == "BUY")
    hold_count = sum(1 for c in scored_coins if c["decision"] == "HOLD")
    sell_count = sum(1 for c in scored_coins if c["decision"] == "SELL")
    confidence, avg_score = _compute_confidence(scored_coins)

    R.append("")
    R.append(f"**Scoring {len(scored_coins)} kryptowalut:** BUY: {buy_count} | HOLD: {hold_count} | SELL: {sell_count}")
    R.append(f"**Sredni score: {avg_score:+.1f} | Pewnosc rekomendacji: {confidence.upper()}**")

    if avg_score >= 3:
        R.append("Wnioski scoringu: Wiekszosc koinow daje sygnaly kupna — rynek sprzyja akumulacji.")
    elif avg_score >= 0:
        R.append("Wnioski scoringu: Mieszane sygnaly — ostrozne podejscie z selektywnym kupowaniem.")
    else:
        R.append("Wnioski scoringu: Dominuja sygnaly sprzedazy — zalecana ostroznosc i ochrona kapitalu.")
    R.append("")

    # --- Pelny ranking ---
    R.append("## PELNY RANKING KRYPTOWALUT")
    R.append("")
    R.append(f"| # | Coin | Cena PLN | Score | Decyzja | RSI | 24h | 7d | Ryzyko |")
    R.append(f"|---|------|----------|-------|---------|-----|-----|-----|--------|")
    for i, c in enumerate(scored_coins, 1):
        R.append(
            f"| {i} | {c['symbol']} | {c['price_pln']:,.2f} | {c['score']:+d} | {c['decision']} | "
            f"{c.get('rsi_daily', 0):.1f} | {_fmt_pct(c.get('change_24h'))} | "
            f"{_fmt_pct(c.get('change_7d'))} | {c['risk_class']} |"
        )
    R.append("")

    # --- 3 Strategie ---
    for s in strategies:
        name = s["name"].upper()
        horizon = s.get("horizon", "?")
        desc = s.get("description", "")
        max_pos = s.get("max_position_pct", "?")
        coins = s.get("coins", [])

        R.append(f"## STRATEGIA {name} (horyzont: {horizon})")
        R.append(f"{desc}")
        R.append(f"Budzet: {BUDGET_PLN:,} PLN | Max pozycja: {max_pos}%")
        R.append("")

        # Tabela portfela
        R.append("| Coin | Score | Decyzja | Alokacja PLN | % | Jednostki | Cena PLN | Stop-loss PLN | Take-profit PLN |")
        R.append("|------|-------|---------|-------------|---|-----------|----------|---------------|-----------------|")
        total_alloc = 0
        for a in coins:
            total_alloc += a["alloc_pln"]
            R.append(
                f"| {a['symbol']} | {a['score']:+d} | {a['decision']} | "
                f"{a['alloc_pln']:,} | {a['alloc_pct']:.1f}% | "
                f"{a['units']:.6f} | {a['price_pln']:,.2f} | "
                f"{a['strategy_sl_pln']:,.2f} ({a['strategy_sl_pct']:+.1f}%) | "
                f"{a['strategy_tp_pln']:,.2f} ({a['strategy_tp_pct']:+.1f}%) |"
            )
        R.append(f"| **SUMA** | | | **{total_alloc:,}** | **100.0%** | | | | |")
        R.append("")

        # Szczegoly per-coin
        R.append(f"### Szczegoly pozycji — {name}")
        for a in coins:
            R.append(f"**{a['symbol']} ({a['name']}) — Rank #{a['market_cap_rank']} — {a['decision']}**")
            R.append(f"  SCORING: {a.get('score_text', '?')}")
            R.append(f"  Cena: {a['price_pln']:,.2f} PLN" + (f" / ${a['price_usd']:,.2f} USD" if a.get("price_usd") else ""))
            R.append(f"  Alokacja: {a['alloc_pln']:,} PLN ({a['alloc_pct']}%) = {a['units']:.6f} {a['symbol']}")
            R.append(f"  Zmiana: 1h={_fmt_pct(a.get('change_1h'))}, 24h={_fmt_pct(a.get('change_24h'))}, 7d={_fmt_pct(a.get('change_7d'))}, 30d={_fmt_pct(a.get('change_30d'))}")

            if a.get("ath_pln"):
                R.append(f"  ATH: {a['ath_pln']:,.2f} PLN ({_fmt_pct(a.get('ath_change_pct'))} od ATH)")

            R.append(f"  TA Daily: RSI={a.get('rsi_daily', '?')}, Sygnal={a['ta_signal_daily']}, MACD_hist={a.get('macd_hist_daily', '?')}")
            R.append(f"  TA 4h: RSI={a.get('rsi_4h', '?')}, Sygnal={a['ta_signal_4h']}")

            if a.get("bb_lower") and a.get("bb_upper"):
                R.append(f"  Bollinger: [{a['bb_lower']:.2f} — {a['bb_upper']:.2f}] USD")

            ma_parts = []
            for label, key in [("EMA50", "ema_50"), ("EMA200", "ema_200"), ("SMA50", "sma_50"), ("SMA200", "sma_200")]:
                if a.get(key):
                    ma_parts.append(f"{label}=${a[key]:,.2f}")
            if ma_parts:
                R.append(f"  Srednie: {', '.join(ma_parts)}")

            for sig in a.get("signals_daily", []):
                R.append(f"    -> {sig}")

            R.append(f"  Stop-loss: {a['strategy_sl_pln']:,.2f} PLN ({a['strategy_sl_pct']:+.1f}%)")
            R.append(f"  Take-profit: {a['strategy_tp_pln']:,.2f} PLN ({a['strategy_tp_pct']:+.1f}%)")

            coin_news = _get_coin_news(a["symbol"])
            if coin_news:
                R.append(f"  Powiazane newsy ({len(coin_news)}):")
                for n in coin_news[:5]:
                    R.append(f"    - {n}")
            R.append("")

        # Scenariusze (obliczone w Pythonie)
        scenarios = _compute_scenarios(s)
        horizon_label = "7-dniowy" if "tydzien" in horizon else "30-dniowy"
        R.append(f"### Scenariusze ({horizon_label}):")
        R.append(f"  Optymistyczny: {scenarios['optymistyczny']:,} PLN ({(scenarios['optymistyczny'] / BUDGET_PLN - 1) * 100:+.1f}%)")
        R.append(f"  Realistyczny:  {scenarios['realistyczny']:,} PLN ({(scenarios['realistyczny'] / BUDGET_PLN - 1) * 100:+.1f}%)")
        R.append(f"  Pesymistyczny: {scenarios['pesymistyczny']:,} PLN ({(scenarios['pesymistyczny'] / BUDGET_PLN - 1) * 100:+.1f}%)")
        R.append("")

    # --- Ostrzezenia (Python) ---
    R.append("## OSTRZEZENIA I RYZYKA")
    R.append("- Rynek kryptowalut jest wysoce zmienny — straty moga przekroczyc stop-lossy przy nagłych ruchach.")
    R.append("- Ryzyko regulacyjne — nowe przepisy moga negatywnie wplynac na ceny.")
    R.append("- Ryzyko plynnosci — altcoiny o nizszym rankingu moga miec ograniczona plynnosc.")
    R.append("- Ryzyko korelacji — w panicznych wyprzedazach wszystkie kryptowaluty spadaja jednoczesnie.")
    R.append("- Red flags do natychmiastowej sprzedazy: przelamanie stop-loss, hack gieldy, ban regulacyjny.")
    R.append("")
    R.append(f"Maksymalna strata konserwatywna: ~{BUDGET_PLN * 0.05:,.0f} PLN (5%)")
    R.append(f"Maksymalna strata zbalansowana: ~{BUDGET_PLN * 0.10:,.0f} PLN (10%)")
    R.append(f"Maksymalna strata agresywna: ~{BUDGET_PLN * 0.15:,.0f} PLN (15%)")
    R.append("")

    # --- Podsumowanie ---
    R.append("## PODSUMOWANIE")
    R.append(f"Pewnosc rekomendacji: **{confidence.upper()}** (sredni score: {avg_score:+.1f})")

    if avg_score >= 3:
        R.append("Rekomendowana strategia: **ZBALANSOWANA** — silne sygnaly kupna pozwalaja na umiarkowane ryzyko.")
    elif avg_score >= 0:
        R.append("Rekomendowana strategia: **KONSERWATYWNA** — mieszane sygnaly sugeruja ostrozne podejscie.")
    else:
        R.append("Rekomendowana strategia: **KONSERWATYWNA** lub WSTRZYMANIE — dominuja sygnaly sprzedazy.")
    R.append("")
    R.append("**WAZNE: To NIE jest porada inwestycyjna. Inwestowanie w kryptowaluty wiaze sie z wysokim ryzykiem utraty kapitalu. Przed podjęciem decyzji skonsultuj sie z licencjonowanym doradca finansowym.**")

    return "\n".join(R)


# ---------------------------------------------------------------------------
# Prompt do LLM — TYLKO komentarz jakosciowy
# ---------------------------------------------------------------------------

def _build_commentary_prompt(scored_coins: list[dict], strategies: list[dict]) -> str:
    """
    Prompt do LLM proszocy TYLKO o krotki komentarz jakosciowy.
    LLM NIE podaje ZADNYCH liczb, dat, tabel — to robi Python.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    summary_data = load_json("summary.json")
    summary_text = (summary_data.get("summary", "") if summary_data else "")[:3000]

    # Krótki kontekst per-coin dla LLM
    coin_context_parts = []
    all_symbols_in_strategies = set()
    for s in strategies:
        for c in s.get("coins", []):
            sym = c["symbol"]
            if sym in all_symbols_in_strategies:
                continue
            all_symbols_in_strategies.add(sym)

            news_lines = _get_coin_news(sym)
            news_text = "; ".join(news_lines[:3]) if news_lines else "brak newsow"

            coin_context_parts.append(
                f"{sym} ({c['name']}): score={c['score']:+d} ({c['decision']}), "
                f"RSI(d)={c.get('rsi_daily', '?')}, RSI(4h)={c.get('rsi_4h', '?')}, "
                f"MACD_hist={c.get('macd_hist_daily', '?')}, "
                f"24h={_fmt_pct(c.get('change_24h'))}, 7d={_fmt_pct(c.get('change_7d'))}, "
                f"scoring: {c.get('score_text', '?')}, "
                f"newsy: {news_text}"
            )

    coin_context = "\n".join(coin_context_parts)

    macro = load_json("macro_context.json")
    fng_text = ""
    if macro:
        fng = macro.get("fear_and_greed", {})
        fng_text = f"Fear & Greed: {fng.get('value', '?')} ({fng.get('classification', '?')})"
        if fng.get("interpretation"):
            fng_text += f" — {fng['interpretation']}"

    prompt = f"""DZISIEJSZA DATA: {now}
ROLA: Jestes analitykiem kryptowalut. Piszesz KROTKIE komentarze do gotowego raportu.

KONTEKST RYNKU:
{fng_text}
{summary_text[:1500]}

DANE PER-COIN:
{coin_context}

ZADANIE: Napisz po polsku DOKLADNIE w ponizszym formacie. ZAKAZ wymyslania danych — korzystaj TYLKO z powyzszych informacji.

OCENA_RYNKU:
[Napisz 3-5 zdan o aktualnej sytuacji rynkowej na podstawie POWYZSZYCH DANYCH. Wymien konkretne wartosci z danych (np. Fear & Greed, zmiany procentowe). NIE wymyslaj dat, cen, ani innych liczb.]

KOMENTARZ_{list(all_symbols_in_strategies)[0] if all_symbols_in_strategies else 'BTC'}:
[2-3 zdania UNIKALNE dla tego coina. Odwolaj sie do jego RSI, MACD, scoringu i newsow z POWYZSZYCH DANYCH.]

"""
    # Dodaj per-coin sections
    for sym in list(all_symbols_in_strategies)[1:]:
        prompt += f"KOMENTARZ_{sym}:\n[2-3 zdania UNIKALNE dla {sym}. Uzyj TYLKO danych podanych wyzej.]\n\n"

    prompt += """ZASADY (KRYTYCZNE):
- NIE podawaj ZADNYCH liczb, cen, kwot, jednostek, dat, tabel — to juz jest w raporcie.
- NIE powtarzaj tabel ani alokacji.
- Pisz WYLACZNIE komentarze jakosciowe — dlaczego dany coin, co przemawia ZA/PRZECIW.
- Kazdy coin MUSI miec INNE, unikalne uzasadnienie.
- Korzystaj WYLACZNIE z danych podanych powyzej — NIE wymyslaj informacji.
- Odpowiadaj WYLACZNIE po polsku."""

    return prompt


# ---------------------------------------------------------------------------
# Uruchomienie agenta
# ---------------------------------------------------------------------------

def _parse_llm_commentary(raw: str) -> dict[str, str]:
    """Parsuje odpowiedz LLM na slownik: klucz -> tekst komentarza."""
    result = {}
    current_key = None
    current_lines = []

    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("OCENA_RYNKU:"):
            if current_key:
                result[current_key] = "\n".join(current_lines).strip()
            current_key = "OCENA_RYNKU"
            rest = stripped[len("OCENA_RYNKU:"):].strip()
            current_lines = [rest] if rest else []
        elif stripped.startswith("KOMENTARZ_"):
            if current_key:
                result[current_key] = "\n".join(current_lines).strip()
            key_part = stripped.split(":")[0]
            sym = key_part.replace("KOMENTARZ_", "")
            current_key = sym
            rest = stripped[len(key_part) + 1:].strip()
            current_lines = [rest] if rest else []
        else:
            if current_key:
                current_lines.append(line)

    if current_key:
        result[current_key] = "\n".join(current_lines).strip()

    return result


def _inject_commentary(data_report: str, commentary: dict[str, str]) -> str:
    """Wstrzykuje komentarze LLM do raportu Python."""
    lines = data_report.split("\n")
    output = []

    market_injected = False
    for line in lines:
        output.append(line)

        if line.startswith("## 1. OCENA RYNKU") and not market_injected:
            market_comment = commentary.get("OCENA_RYNKU", "")
            if market_comment:
                output.append("")
                output.append("**Komentarz analityka:**")
                output.append(market_comment)
            market_injected = True

        # Wstrzyknij komentarz po linii SCORING danego coina
        for sym, comment in commentary.items():
            if sym == "OCENA_RYNKU":
                continue
            if line.strip().startswith(f"**{sym} (") and f"— {sym}" not in line:
                continue
            if line.strip().startswith(f"  SCORING:") and comment:
                # Sprawdz czy poprzednia linia to naglowek tego coina
                prev_line = output[-2] if len(output) >= 2 else ""
                if f"**{sym} (" in prev_line:
                    output.append(f"  Komentarz: {comment}")
                    commentary[sym] = ""  # unikaj duplikatow

    return "\n".join(output)


def run() -> dict:
    """
    Uruchamia agenta decyzyjnego.
    1. Python generuje CALY raport z danymi (zero halucynacji)
    2. LLM dodaje KROTKI komentarz jakosciowy
    3. Laczy oba w finalny wynik
    """
    print("[Agent Decyzyjny] Start...")
    collected_at = datetime.now(timezone.utc).isoformat()

    scored_coins = _score_all_coins()
    if not scored_coins:
        print("[Agent Decyzyjny] Brak danych do analizy!")
        return {"meta": {"collected_at": collected_at, "error": "no_data"}, "decision": ""}

    print(f"  Przeanalizowano {len(scored_coins)} koinow. Top 5:")
    for c in scored_coins[:5]:
        print(f"    {c['symbol']}: score={c['score']:+d} ({c['decision']}), RSI={c.get('rsi_daily','?')}, {c['score_text']}")

    strategies = []
    for stype in ["konserwatywna", "zbalansowana", "agresywna"]:
        s = _build_strategy(scored_coins, stype)
        strategies.append(s)
        coins_str = ", ".join(c["symbol"] for c in s.get("coins", []))
        print(f"  Strategia {stype}: {s['coin_count']} coinow [{coins_str}]")

    # Krok 1: Python generuje CALY raport z danymi
    data_report = _generate_data_report(scored_coins, strategies)
    print(f"  Raport Python: {len(data_report)} znakow")

    # Krok 2: LLM generuje TYLKO komentarz jakosciowy
    commentary_prompt = _build_commentary_prompt(scored_coins, strategies)
    print(f"  Wysylam do Ollama ({MODEL_NAME}), prompt komentarza: {len(commentary_prompt)} znakow...")

    llm_commentary_raw = ""
    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            r = client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL_NAME,
                    "prompt": commentary_prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 2000},
                },
            )
            r.raise_for_status()
            llm_commentary_raw = r.json().get("response", "")
    except Exception as e:
        print(f"  [Ollama] Blad: {e}")
        llm_commentary_raw = ""

    # Krok 3: Laczenie raportu Python + komentarzy LLM
    if llm_commentary_raw.strip():
        commentary = _parse_llm_commentary(llm_commentary_raw)
        print(f"  Sparsowano {len(commentary)} komentarzy LLM")
        final_report = _inject_commentary(data_report, commentary)

        # Dodaj surowy komentarz LLM na koncu jako osobna sekcje
        final_report += "\n\n## KOMENTARZ ANALITYKA (AI)\n"
        final_report += llm_commentary_raw
    else:
        print("  LLM nie zwrocil komentarza — raport zawiera TYLKO dane.")
        final_report = data_report

    result = {
        "meta": {
            "collected_at": collected_at,
            "model": MODEL_NAME,
            "budget_pln": BUDGET_PLN,
            "coins_analyzed": len(scored_coins),
            "data_report_chars": len(data_report),
            "llm_commentary_chars": len(llm_commentary_raw),
        },
        "ranking": [
            {"symbol": c["symbol"], "name": c["name"],
             "score": c["score"], "decision": c["decision"],
             "score_text": c["score_text"],
             "rsi": c.get("rsi_daily"), "risk": c["risk_class"], "price_pln": c["price_pln"]}
            for c in scored_coins
        ],
        "strategies": {
            s["name"]: {
                "description": s.get("description"),
                "horizon": s.get("horizon"),
                "coins": [
                    {"symbol": c["symbol"], "name": c["name"],
                     "alloc_pln": c["alloc_pln"], "alloc_pct": c["alloc_pct"],
                     "units": c["units"], "price_pln": c["price_pln"],
                     "sl_pln": c["strategy_sl_pln"], "tp_pln": c["strategy_tp_pln"],
                     "risk": c["risk_class"]}
                    for c in s.get("coins", [])
                ],
            }
            for s in strategies
        },
        "decision": final_report,
    }

    path = save_json(result, "decision.json")
    print(f"[Agent Decyzyjny] Zapisano: {path} ({len(final_report)} znakow)")
    return result


if __name__ == "__main__":
    run()
