from pydantic import BaseModel
from typing import Literal
from datetime import datetime

SUPPORTED_CURRENCIES = ["PLN", "USD", "EUR", "GBP", "CHF", "CZK", "JPY", "CAD", "NOK", "SEK"]


class PositionCreate(BaseModel):
    symbol: str
    asset_type: Literal["crypto", "stock", "etf"] = "crypto"
    quantity: float
    avg_buy_price: float
    currency: str = "PLN"          # waluta zakupu
    bought_at: datetime | None = None


class PositionUpdate(BaseModel):
    quantity: float | None = None
    avg_buy_price: float | None = None
    currency: str | None = None
    bought_at: datetime | None = None


class PositionResponse(BaseModel):
    id: str
    portfolio_id: str
    symbol: str
    asset_type: str
    quantity: float
    avg_buy_price: float
    currency: str
    bought_at: datetime | None
    updated_at: datetime
    # Obliczane on-the-fly w preferred_currency użytkownika
    current_price: float | None = None
    current_value: float | None = None
    cost_basis: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    display_currency: str = "PLN"


class PortfolioResponse(BaseModel):
    id: str
    user_id: str
    name: str
    broker: str
    created_at: datetime
    positions: list[PositionResponse] = []
    total_value: float = 0.0
    total_invested: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    display_currency: str = "PLN"


class PnLResponse(BaseModel):
    total_value: float
    total_invested: float
    total_pnl: float
    total_pnl_pct: float
    display_currency: str
    positions: list[PositionResponse]
