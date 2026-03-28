import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from database import get_supabase
from services.auth_service import get_current_user

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/market")
def get_market(current_user: dict = Depends(get_current_user)):
    """Zwraca ostatnie snapshoty rynkowe dla top 20 symboli."""
    db = get_supabase()

    # Pobierz ostatni snapshot dla każdego symbolu
    result = (
        db.table("market_snapshots")
        .select("symbol, price_pln, price_usd, price_change_24h, volume_24h, market_cap, rsi_14, macd_signal, fear_greed_index, snapshot_at")
        .order("snapshot_at", desc=True)
        .limit(200)
        .execute()
    )

    # Deduplikuj - tylko ostatni snapshot per symbol
    seen = set()
    coins = []
    for row in (result.data or []):
        symbol = row["symbol"]
        if symbol not in seen:
            seen.add(symbol)
            coins.append(row)
        if len(coins) >= 20:
            break

    return {"coins": coins, "count": len(coins)}


@router.get("/market/refresh")
async def refresh_market(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Uruchamia natychmiastowe odświeżenie danych rynkowych (async)."""
    from monitors.market_monitor import _take_snapshot
    background_tasks.add_task(_take_snapshot)
    return {"status": "Odświeżanie danych uruchomione w tle"}


@router.get("/technical/{symbol}")
def get_technical(symbol: str, current_user: dict = Depends(get_current_user)):
    """Zwraca dane techniczne dla danego symbolu z ostatniego snapshotu."""
    db = get_supabase()
    result = (
        db.table("market_snapshots")
        .select("*")
        .eq("symbol", symbol.upper())
        .order("snapshot_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Brak danych dla {symbol}")
    return result.data[0]


@router.get("/predictions")
def get_predictions(
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
):
    """Zwraca ostatnie predykcje dla użytkownika."""
    db = get_supabase()
    result = (
        db.table("predictions")
        .select("*, events(source, author, content, url, detected_at)")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"predictions": result.data or [], "count": len(result.data or [])}


@router.get("/events")
def get_events(limit: int = 20, current_user: dict = Depends(get_current_user)):
    """Zwraca ostatnie zdarzenia rynkowe."""
    db = get_supabase()
    result = (
        db.table("events")
        .select("*")
        .order("detected_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"events": result.data or []}


@router.post("/run-pipeline")
async def run_full_pipeline(current_user: dict = Depends(get_current_user)):
    """Uruchamia pełny pipeline agentów i zwraca wyniki."""
    loop = asyncio.get_event_loop()

    def _run():
        from agents.run_all import run_full_pipeline
        return run_full_pipeline()

    result = await loop.run_in_executor(None, _run)
    return result
