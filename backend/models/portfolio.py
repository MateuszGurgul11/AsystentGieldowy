from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class PositionCreate(BaseModel):
    symbol: str
    asset_type: Literal["crypto", "stock", "etf"] = "crypto"
    quantity: float
    avg_buy_price_pln: float
    bought_at: datetime | None = None


class PositionUpdate(BaseModel):
    quantity: float | None = None
    avg_buy_price_pln: float | None = None
    bought_at: datetime | None = None


class PositionResponse(BaseModel):
    id: str
    portfolio_id: str
    symbol: str
    asset_type: str
    quantity: float
    avg_buy_price_pln: float
    bought_at: datetime | None
    updated_at: datetime
    # Obliczane on-the-fly
    current_price_pln: float | None = None
    current_value_pln: float | None = None
    cost_basis_pln: float | None = None
    pnl_pln: float | None = None
    pnl_pct: float | None = None


class PortfolioResponse(BaseModel):
    id: str
    user_id: str
    name: str
    broker: str
    created_at: datetime
    positions: list[PositionResponse] = []
    total_value_pln: float = 0.0
    total_invested_pln: float = 0.0
    total_pnl_pln: float = 0.0
    total_pnl_pct: float = 0.0


class PnLResponse(BaseModel):
    total_value_pln: float
    total_invested_pln: float
    total_pnl_pln: float
    total_pnl_pct: float
    positions: list[PositionResponse]
