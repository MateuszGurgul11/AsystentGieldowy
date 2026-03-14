"""
Przykład: pytanie do modelu invest-assistant z treścią strony w kontekście.

Użycie (Ollama musi działać: ollama run invest-assistant w innym terminalu lub w tle):
  cd backend
  python market_agent/example_ask_with_url.py "https://cointelegraph.com/news/bitcoin-..." "Oceń sentyment tego artykułu dla BTC."
  python market_agent/example_ask_with_url.py "https://example.com" "Podsumuj tę stronę."
"""

import sys
import httpx

# Działa z backend jako cwd lub z repo root
try:
    from market_agent.url_content import fetch_page_text
except ImportError:
    from url_content import fetch_page_text

OLLAMA_URL = "http://localhost:11434"
MODEL = "invest-assistant"
TIMEOUT = 90


def ask_with_url(url: str, question: str) -> str:
    """Pobiera treść url, wstrzykuje do promptu i zwraca odpowiedź modelu."""
    text = fetch_page_text(url, max_chars=8000)
    if not text:
        return f"Nie udało się pobrać treści z {url} (timeout, błąd lub za mało tekstu)."
    prompt = f"""Oto treść strony z linku ({url}):

---
{text}
---

Zadanie: {question}
Odpowiedz zwięźle po polsku, na podstawie powyższej treści."""
    try:
        r = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("response", "(brak odpowiedzi)")
    except httpx.ConnectError:
        return "Błąd: nie można połączyć z Ollama (uruchom: ollama serve)."
    except Exception as e:
        return f"Błąd: {e}"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Użycie: python example_ask_with_url.py <URL> <pytanie>")
        print('Przykład: python example_ask_with_url.py "https://cointelegraph.com/..." "Oceń sentyment dla BTC."')
        sys.exit(1)
    url_arg = sys.argv[1]
    question_arg = " ".join(sys.argv[2:])
    print("Pobieram treść strony...")
    answer = ask_with_url(url_arg, question_arg)
    print("\n--- Odpowiedź modelu ---\n")
    print(answer)
