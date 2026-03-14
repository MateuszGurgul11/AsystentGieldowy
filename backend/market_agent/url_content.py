"""
Pobieranie treści ze strony (dla modelu LLM).

Model nie ma dostępu do sieci — backend pobiera URL, czyści HTML i zwraca tekst.
Ten tekst wstrzykujesz do promptu przed wywołaniem Ollama.

Użycie:
  from market_agent.url_content import fetch_page_text
  text = fetch_page_text("https://example.com/article")
  prompt = f"Oto treść strony:\n\n{text}\n\nUżytkownik pyta: ..."
"""

import re
from typing import Optional

import httpx

REQUEST_TIMEOUT = 15
MAX_CHARS = 12000  # żeby nie przekroczyć kontekstu modelu
USER_AGENT = "MarketAgent/1.0 (LLM context fetcher)"


def _strip_html(html: str) -> str:
    """Usuwa tagi HTML i normalizuje białe znaki."""
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    return text.strip()


def fetch_page_text(url: str, max_chars: int = MAX_CHARS) -> Optional[str]:
    """
    Pobiera URL i zwraca czysty tekst (bez HTML), ograniczony do max_chars.

    Zwraca None przy błędzie (timeout, 404, brak tekstu).
    """
    if not url or not url.strip().startswith(("http://", "https://")):
        return None
    url = url.strip()
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            html = r.text
    except Exception:
        return None

    text = _strip_html(html)
    if not text or len(text) < 50:
        return None
    return text[:max_chars]


def inject_url_into_prompt(user_message: str, fetch_urls: bool = True) -> str:
    """
    Jeśli w wiadomości użytkownika są linki (http/https), pobiera ich treść
    i zwraca rozszerzony prompt: treść stron + oryginalna wiadomość.

    Jeśli fetch_urls=False lub brak linków, zwraca user_message bez zmian.
    """
    if not fetch_urls:
        return user_message
    url_pattern = re.compile(r"https?://[^\s<>)\]]+", re.I)
    urls = url_pattern.findall(user_message)
    if not urls:
        return user_message

    parts = []
    for u in urls[:3]:  # max 3 linki
        text = fetch_page_text(u, max_chars=6000)
        if text:
            parts.append(f"[Treść strony: {u}]\n{text}\n")
    if not parts:
        return user_message
    return "\n".join(parts) + "\n\n[Pytanie użytkownika]\n" + user_message
