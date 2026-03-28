from database import get_supabase
from models.portfolio import PositionResponse, PortfolioResponse


def get_latest_price(symbol: str) -> float | None:
    """Pobiera ostatnią cenę PLN z market_snapshots."""
    db = get_supabase()
    result = (
        db.table("market_snapshots")
        .select("price_pln")
        .eq("symbol", symbol.upper())
        .order("snapshot_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return float(result.data[0]["price_pln"])
    return None


def enrich_position(position: dict) -> PositionResponse:
    """Dodaje P&L do pozycji na podstawie ostatniej ceny."""
    symbol = position["symbol"].upper()
    quantity = float(position["quantity"])
    avg_price = float(position["avg_buy_price_pln"])
    cost_basis = quantity * avg_price

    current_price = get_latest_price(symbol)
    if current_price is not None:
        current_value = quantity * current_price
        pnl_pln = current_value - cost_basis
        pnl_pct = (pnl_pln / cost_basis * 100) if cost_basis > 0 else 0.0
    else:
        current_value = pnl_pln = pnl_pct = None

    return PositionResponse(
        id=position["id"],
        portfolio_id=position["portfolio_id"],
        symbol=symbol,
        asset_type=position["asset_type"],
        quantity=quantity,
        avg_buy_price_pln=avg_price,
        bought_at=position.get("bought_at"),
        updated_at=position["updated_at"],
        current_price_pln=current_price,
        current_value_pln=round(current_value, 2) if current_value is not None else None,
        cost_basis_pln=round(cost_basis, 2),
        pnl_pln=round(pnl_pln, 2) if pnl_pln is not None else None,
        pnl_pct=round(pnl_pct, 2) if pnl_pct is not None else None,
    )


def build_portfolio_response(portfolio: dict) -> PortfolioResponse:
    """Buduje pełną odpowiedź portfela z P&L."""
    db = get_supabase()
    positions_raw = (
        db.table("portfolio_positions")
        .select("*")
        .eq("portfolio_id", portfolio["id"])
        .execute()
    ).data or []

    positions = [enrich_position(p) for p in positions_raw]

    total_value = sum(p.current_value_pln for p in positions if p.current_value_pln is not None)
    total_invested = sum(p.cost_basis_pln for p in positions if p.cost_basis_pln is not None)
    total_pnl = total_value - total_invested if total_value and total_invested else 0.0
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    return PortfolioResponse(
        id=portfolio["id"],
        user_id=portfolio["user_id"],
        name=portfolio["name"],
        broker=portfolio["broker"],
        created_at=portfolio["created_at"],
        positions=positions,
        total_value_pln=round(total_value, 2),
        total_invested_pln=round(total_invested, 2),
        total_pnl_pln=round(total_pnl, 2),
        total_pnl_pct=round(total_pnl_pct, 2),
    )
