"""
Agent Decyzyjny — plan inwestycyjny na podstawie summary + cen.
Wynik koncowy: rozbudowany plan inwestycyjny.
"""

from datetime import datetime, timezone

import httpx

from .config import (
    OLLAMA_URL, MODEL_NAME, OLLAMA_TIMEOUT, BUDGET_PLN,
    load_json, save_json,
)


def _build_decision_prompt() -> str:
    """Buduje prompt decyzyjny z summary + aktualnych cen."""
    parts = []

    # Streszczenie od agenta sumaryzujacego
    summary_data = load_json("summary.json")
    summary_text = ""
    if summary_data:
        summary_text = summary_data.get("summary", "")
    if summary_text:
        parts.append(f"=== STRESZCZENIE ANALITYCZNE ===\n{summary_text}")

    # Dokladne ceny (nie streszczone)
    market = load_json("market_prices.json")
    if market:
        usd_pln = market.get("meta", {}).get("usd_pln_rate", 4.0)
        lines = [f"Kurs USD/PLN: {usd_pln}"]
        for c in market.get("coins", []):
            lines.append(
                f"  {c['symbol']} ({c['name']}): "
                f"{c.get('price_pln')} PLN / ${c.get('price_usd', '?')} USD | "
                f"MCap rank: #{c.get('market_cap_rank', '?')} | "
                f"1h: {c.get('price_change_1h_pct', '?')}% | "
                f"24h: {c.get('price_change_24h_pct', '?')}% | "
                f"7d: {c.get('price_change_7d_pct', '?')}% | "
                f"30d: {c.get('price_change_30d_pct', '?')}% | "
                f"ATH: {c.get('ath_pln', '?')} PLN ({c.get('ath_change_pct', '?')}% od ATH)"
            )
        parts.append("=== AKTUALNE CENY ===\n" + "\n".join(lines))

    # Kluczowe wskazniki TA
    ta = load_json("technical_analysis.json")
    if ta:
        lines = []
        for coin_name, coin_data in ta.get("analysis", {}).items():
            daily = coin_data.get("daily", {})
            lines.append(
                f"  {coin_name}: RSI={daily.get('rsi_14','?')} "
                f"MACD_hist={daily.get('macd_histogram','?')} "
                f"Sygnal={daily.get('overall','?')} "
                f"BB: [{daily.get('bollinger_lower','?')}-{daily.get('bollinger_upper','?')}]"
            )
        parts.append("=== WSKAZNIKI TECHNICZNE ===\n" + "\n".join(lines))

    context = "\n\n".join(parts)
    return context


DECISION_PROMPT = f"""Jestes glownym agentem decyzyjnym systemu inwestycyjnego. Masz budzet {BUDGET_PLN} PLN do zainwestowania w kryptowaluty.

Na podstawie danych ponizej, przygotuj ROZBUDOWANY PLAN INWESTYCYJNY po polsku:

1. **OCENA RYNKU** (3-5 zdan):
   - Obecny trend (byk/niedzwiedz/boczny)
   - Sentyment (Fear & Greed)
   - Kluczowe czynniki

2. **TOP 5 REKOMENDACJI** — dla kazdej pozycji:
   - Nazwa i symbol kryptowaluty
   - Kwota alokacji w PLN i % budzetu
   - Ilosc jednostek do zakupu (oblicz na podstawie aktualnej ceny w PLN!)
   - Uzasadnienie (wskazniki techniczne, fundamenty, newsy)
   - Stop-loss: poziom cenowy w PLN i % straty
   - Take-profit: poziom cenowy w PLN i % zysku
   - Horyzont: krotkoterminowy (1-7 dni), srednioterminowy (1-4 tyg), dlugoterminowy (1-6 mies)
   - Poziom ryzyka: niski/sredni/wysoki

3. **PODSUMOWANIE PORTFELA**:
   - Tabela: coin | alokacja PLN | % | ilosc | cena wejscia
   - Calkowity budzet wykorzystany
   - Sredni poziom ryzyka portfela

4. **SCENARIUSZE** (prognoza 7 i 30 dni):
   - Optymistyczny: wartosc portfela i % zysku
   - Realistyczny: wartosc portfela i % zysku/straty
   - Pesymistyczny: wartosc portfela i % straty

5. **OSTRZEZENIA I RYZYKA**:
   - Czynniki mogace wplynac negatywnie
   - Maksymalna akceptowalna strata

WAZNE:
- Budzet to {BUDGET_PLN} PLN (NIE USD!). Podawaj ceny i alokacje w PLN.
- Ulamkowe jednostki krypto sa dozwolone (np. 0.003 BTC).
- Suma alokacji musi = {BUDGET_PLN} PLN.
- Opieraj sie TYLKO na dostarczonych danych. Nie wymyslaj.
- Podaj poziom pewnosci rekomendacji: wysoki/sredni/niski."""


def run() -> dict:
    """Uruchamia agenta decyzyjnego."""
    print("[Agent Decyzyjny] Start...")
    collected_at = datetime.now(timezone.utc).isoformat()

    context = _build_decision_prompt()
    if not context.strip():
        print("[Agent Decyzyjny] Brak danych!")
        return {"meta": {"collected_at": collected_at, "error": "no_data"}, "decision": ""}

    full_prompt = f"{DECISION_PROMPT}\n\n--- DANE ---\n{context}"

    print(f"  Wysylam do Ollama ({MODEL_NAME}), prompt: {len(full_prompt)} znakow...")
    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            r = client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL_NAME,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {"temperature": 0.4, "num_predict": 3000},
                },
            )
            r.raise_for_status()
            response_text = r.json().get("response", "")
    except Exception as e:
        print(f"  [Ollama] Blad: {e}")
        response_text = f"Blad komunikacji z modelem: {e}"

    result = {
        "meta": {
            "collected_at": collected_at,
            "model": MODEL_NAME,
            "budget_pln": BUDGET_PLN,
            "prompt_chars": len(full_prompt),
        },
        "decision": response_text,
    }

    path = save_json(result, "decision.json")
    print(f"[Agent Decyzyjny] Zapisano: {path} ({len(response_text)} znakow)")
    return result


if __name__ == "__main__":
    run()
