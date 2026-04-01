import time
import httpx

SUPPORTED_CURRENCIES = ["PLN", "USD", "EUR", "GBP", "CHF", "CZK", "JPY", "CAD", "NOK", "SEK"]

# Cache kursów - odświeżany co godzinę
_cache: dict = {"rates": {}, "updated_at": 0.0}


def get_rates(base: str = "USD") -> dict[str, float]:
    """
    Pobiera kursy walut z open.er-api.com (baza USD).
    Wynik cachowany na 1 godzinę.
    """
    now = time.time()
    if now - _cache["updated_at"] < 3600 and _cache["rates"]:
        return _cache["rates"]

    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"https://open.er-api.com/v6/latest/{base}")
            r.raise_for_status()
            rates = r.json().get("rates", {})
            _cache["rates"] = rates
            _cache["updated_at"] = now
            return rates
    except Exception:
        # Fallback - zwróć cache lub twarde wartości
        return _cache["rates"] or {
            "PLN": 4.05, "USD": 1.0, "EUR": 0.92,
            "GBP": 0.79, "CHF": 0.89, "CZK": 22.5,
            "JPY": 149.0, "CAD": 1.36, "NOK": 10.5, "SEK": 10.4,
        }


def convert(amount: float, from_currency: str, to_currency: str) -> float:
    """Przelicza kwotę z jednej waluty na inną przez USD jako bazę."""
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    if from_currency == to_currency:
        return amount

    rates = get_rates("USD")
    from_rate = rates.get(from_currency, 1.0)
    to_rate = rates.get(to_currency, 1.0)

    # from_currency → USD → to_currency
    amount_usd = amount / from_rate
    return amount_usd * to_rate


def get_all_rates_for_display() -> dict:
    """Zwraca kursy wszystkich obsługiwanych walut względem USD."""
    rates = get_rates("USD")
    return {
        currency: round(rates[currency], 4)
        for currency in SUPPORTED_CURRENCIES
        if currency in rates
    }
