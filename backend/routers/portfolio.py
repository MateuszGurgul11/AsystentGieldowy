from fastapi import APIRouter, HTTPException, Depends, status
from database import get_supabase
from models.portfolio import PositionCreate, PositionUpdate, PortfolioResponse, PnLResponse
from services.auth_service import get_current_user
from services.portfolio_service import build_portfolio_response, enrich_position

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _get_user_portfolio(user_id: str) -> dict:
    db = get_supabase()
    result = db.table("portfolios").select("*").eq("user_id", user_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Portfel nie istnieje")
    return result.data[0]


@router.get("", response_model=PortfolioResponse)
def get_portfolio(
    currency: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Zwraca portfel z P&L. currency=USD/EUR/PLN - nadpisuje preferred_currency profilu."""
    display_currency = (currency or current_user.get("preferred_currency", "PLN")).upper()
    portfolio = _get_user_portfolio(current_user["id"])
    return build_portfolio_response(portfolio, display_currency)


@router.get("/pnl", response_model=PnLResponse)
def get_pnl(
    currency: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    display_currency = (currency or current_user.get("preferred_currency", "PLN")).upper()
    portfolio = _get_user_portfolio(current_user["id"])
    full = build_portfolio_response(portfolio, display_currency)
    return PnLResponse(
        total_value=full.total_value,
        total_invested=full.total_invested,
        total_pnl=full.total_pnl,
        total_pnl_pct=full.total_pnl_pct,
        display_currency=display_currency,
        positions=full.positions,
    )


@router.post("/position", status_code=status.HTTP_201_CREATED)
def add_position(data: PositionCreate, current_user: dict = Depends(get_current_user)):
    db = get_supabase()
    portfolio = _get_user_portfolio(current_user["id"])

    row = {
        "portfolio_id": portfolio["id"],
        "symbol": data.symbol.upper(),
        "asset_type": data.asset_type,
        "quantity": data.quantity,
        "avg_buy_price": data.avg_buy_price,
        "currency": data.currency.upper(),
        "bought_at": data.bought_at.isoformat() if data.bought_at else None,
    }
    result = db.table("portfolio_positions").insert(row).execute()
    display_currency = current_user.get("preferred_currency", "PLN")
    return enrich_position(result.data[0], display_currency)


@router.put("/position/{position_id}")
def update_position(
    position_id: str,
    data: PositionUpdate,
    current_user: dict = Depends(get_current_user),
):
    db = get_supabase()
    portfolio = _get_user_portfolio(current_user["id"])

    existing = (
        db.table("portfolio_positions")
        .select("*")
        .eq("id", position_id)
        .eq("portfolio_id", portfolio["id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Pozycja nie istnieje")

    updates = data.model_dump(exclude_none=True)
    if data.bought_at:
        updates["bought_at"] = data.bought_at.isoformat()
    if data.currency:
        updates["currency"] = data.currency.upper()

    result = db.table("portfolio_positions").update(updates).eq("id", position_id).execute()
    display_currency = current_user.get("preferred_currency", "PLN")
    return enrich_position(result.data[0], display_currency)


@router.delete("/position/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(position_id: str, current_user: dict = Depends(get_current_user)):
    db = get_supabase()
    portfolio = _get_user_portfolio(current_user["id"])

    existing = (
        db.table("portfolio_positions")
        .select("id")
        .eq("id", position_id)
        .eq("portfolio_id", portfolio["id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Pozycja nie istnieje")

    db.table("portfolio_positions").delete().eq("id", position_id).execute()
