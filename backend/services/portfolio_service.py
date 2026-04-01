from database import get_supabase
from models.portfolio import PositionResponse, PortfolioResponse
from services.currency_service import convert


def get_latest_price_usd(symbol: str) -> float | None:
    """Pobiera ostatnią cenę USD z market_snapshots."""
    db = get_supabase()
    result = (
        db.table("market_snapshots")
        .select("price_usd")
        .eq("symbol", symbol.upper())
        .order("snapshot_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data and result.data[0].get("price_usd"):
        return float(result.data[0]["price_usd"])
    return None


def enrich_position(position: dict, display_currency: str = "PLN") -> PositionResponse:
    """
    Dodaje P&L do pozycji.
    Wszystkie wartości przeliczane do display_currency użytkownika.
    """
    symbol = position["symbol"].upper()
    quantity = float(position["quantity"])
    buy_price = float(position["avg_buy_price"])
    buy_currency = (position.get("currency") or "PLN").upper()
    display_currency = display_currency.upper()

    # Koszt zakupu w display_currency
    buy_price_display = convert(buy_price, buy_currency, display_currency)
    cost_basis = round(quantity * buy_price_display, 2)

    # Aktualna cena - pobieramy w USD i przeliczamy
    price_usd = get_latest_price_usd(symbol)
    if price_usd is not None:
        current_price = round(convert(price_usd, "USD", display_currency), 4)
        current_value = round(quantity * current_price, 2)
        pnl = round(current_value - cost_basis, 2)
        pnl_pct = round((pnl / cost_basis * 100), 2) if cost_basis > 0 else 0.0
    else:
        current_price = current_value = pnl = pnl_pct = None

    return PositionResponse(
        id=position["id"],
        portfolio_id=position["portfolio_id"],
        symbol=symbol,
        asset_type=position["asset_type"],
        quantity=quantity,
        avg_buy_price=buy_price,
        currency=buy_currency,
        bought_at=position.get("bought_at"),
        updated_at=position["updated_at"],
        current_price=current_price,
        current_value=current_value,
        cost_basis=cost_basis,
        pnl=pnl,
        pnl_pct=pnl_pct,
        display_currency=display_currency,
    )


def build_portfolio_response(portfolio: dict, display_currency: str = "PLN") -> PortfolioResponse:
    """Buduje pełną odpowiedź portfela z P&L w wybranej walucie."""
    db = get_supabase()
    positions_raw = (
        db.table("portfolio_positions")
        .select("*")
        .eq("portfolio_id", portfolio["id"])
        .execute()
    ).data or []

    positions = [enrich_position(p, display_currency) for p in positions_raw]

    total_value = sum(p.current_value for p in positions if p.current_value is not None)
    total_invested = sum(p.cost_basis for p in positions if p.cost_basis is not None)
    total_pnl = total_value - total_invested if total_value and total_invested else 0.0
    total_pnl_pct = round((total_pnl / total_invested * 100), 2) if total_invested > 0 else 0.0

    return PortfolioResponse(
        id=portfolio["id"],
        user_id=portfolio["user_id"],
        name=portfolio["name"],
        broker=portfolio["broker"],
        created_at=portfolio["created_at"],
        positions=positions,
        total_value=round(total_value, 2),
        total_invested=round(total_invested, 2),
        total_pnl=round(total_pnl, 2),
        total_pnl_pct=total_pnl_pct,
        display_currency=display_currency,
    )
