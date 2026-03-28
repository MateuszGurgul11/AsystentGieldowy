import asyncio
import logging
from config import get_settings
from database import get_supabase
from services.alert_service import notify_user

logger = logging.getLogger(__name__)


async def market_monitor():
    """Background task: zapisuje snapshoty rynkowe co 1h i sprawdza alerty RSI/cena."""
    settings = get_settings()
    logger.info("Market monitor uruchomiony")

    while True:
        try:
            await _take_snapshot()
            await _check_alerts()
        except Exception as e:
            logger.error(f"Market monitor error: {e}")

        await asyncio.sleep(settings.market_snapshot_interval)


async def _take_snapshot():
    """Pobiera aktualne dane rynkowe i zapisuje snapshot do Supabase."""
    import asyncio
    from agents.agent_market import run as run_market
    from agents.agent_technical import run as run_technical

    logger.info("Pobieranie snapshotu rynkowego...")

    # Uruchom agenty synchronicznie w thread pool
    loop = asyncio.get_event_loop()
    market_data = await loop.run_in_executor(None, run_market)
    technical_data = await loop.run_in_executor(None, run_technical)

    db = get_supabase()

    coins = market_data.get("coins", [])
    tech = technical_data.get("analysis", {})
    fear_greed = market_data.get("global", {}).get("fear_greed_index")

    rows = []
    for coin in coins:
        symbol = coin.get("symbol", "").upper()
        tech_daily = tech.get(symbol, {}).get("1d", {})

        rows.append({
            "symbol": symbol,
            "price_pln": coin.get("price_pln"),
            "price_usd": coin.get("price_usd"),
            "price_change_24h": coin.get("price_change_percentage_24h"),
            "volume_24h": coin.get("volume_24h"),
            "market_cap": coin.get("market_cap"),
            "rsi_14": tech_daily.get("rsi"),
            "macd_signal": tech_daily.get("signal"),
            "fear_greed_index": fear_greed,
        })

    if rows:
        db.table("market_snapshots").insert(rows).execute()
        logger.info(f"Zapisano snapshot dla {len(rows)} symboli")


async def _check_alerts():
    """Sprawdza czy RSI lub cena przekroczyły progi alertów użytkowników."""
    db = get_supabase()

    # Pobierz wszystkie ustawienia alertów
    settings_result = db.table("alert_settings").select("*").execute()
    if not settings_result.data:
        return

    for user_settings in settings_result.data:
        user_id = user_settings["user_id"]
        monitored = user_settings.get("monitored_symbols", [])

        for symbol in monitored:
            # Ostatni snapshot
            snap = (
                db.table("market_snapshots")
                .select("price_pln, rsi_14, price_change_24h")
                .eq("symbol", symbol)
                .order("snapshot_at", desc=True)
                .limit(1)
                .execute()
            )
            if not snap.data:
                continue

            data = snap.data[0]
            rsi = data.get("rsi_14")
            change_24h = data.get("price_change_24h", 0) or 0
            price = data.get("price_pln", 0) or 0

            # Alert RSI
            if user_settings.get("rsi_alert") and rsi is not None:
                oversold_threshold = user_settings.get("rsi_threshold_oversold", 30)
                overbought_threshold = user_settings.get("rsi_threshold_overbought", 70)

                if rsi < oversold_threshold:
                    await notify_user(
                        user_id=user_id,
                        title=f"RSI Alert: {symbol} wyprzedany",
                        body=f"{symbol} RSI={rsi:.1f} (poniżej {oversold_threshold}) - potencjalna okazja do zakupu. Cena: {price:.2f} PLN",
                        alert_type="rsi_signal",
                        priority="medium",
                    )
                elif rsi > overbought_threshold:
                    await notify_user(
                        user_id=user_id,
                        title=f"RSI Alert: {symbol} wykupiony",
                        body=f"{symbol} RSI={rsi:.1f} (powyżej {overbought_threshold}) - możliwa korekta. Cena: {price:.2f} PLN",
                        alert_type="rsi_signal",
                        priority="medium",
                    )

            # Alert zmiany ceny
            if user_settings.get("price_change_alert"):
                threshold = user_settings.get("price_change_threshold", 5.0) or 5.0
                if abs(change_24h) >= threshold:
                    direction = "wzrost" if change_24h > 0 else "spadek"
                    priority = "high" if abs(change_24h) >= threshold * 2 else "medium"
                    await notify_user(
                        user_id=user_id,
                        title=f"Alert ceny: {symbol} {direction} {abs(change_24h):.1f}%",
                        body=f"{symbol} zmienił cenę o {change_24h:+.1f}% w 24h. Aktualna cena: {price:.2f} PLN",
                        alert_type="price_alert",
                        priority=priority,
                    )
