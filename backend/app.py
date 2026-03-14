"""
Gradio UI: Asystent Gieldowy — multi-agent system.

Pipeline:
  Faza 1: 5 agentow zbierajacych (rownolegle) -> JSON
  Faza 2: Agent sumaryzujacy (LLM) -> summary.json
  Faza 3: Agent decyzyjny (LLM) -> plan inwestycyjny
"""

import json
import sys
import time
import threading
from pathlib import Path
from datetime import datetime

import gradio as gr

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.agents.config import DATA_DIR, MODEL_NAME, BUDGET_PLN, load_json
from backend.agents.run_all import (
    run_collectors_parallel,
    run_summarizer,
    run_decision,
)


def _read_agent_json(filename: str) -> str:
    """Wczytuje JSON agenta i formatuje do wyswietlenia."""
    data = load_json(filename)
    if data is None:
        return "(brak danych — uruchom analize)"
    return json.dumps(data, ensure_ascii=False, indent=2)


def _format_market_preview() -> str:
    """Formatuje podglad danych rynkowych."""
    data = load_json("market_prices.json")
    if not data:
        return "(brak danych)"
    lines = []
    meta = data.get("meta", {})
    lines.append(f"Zebrano: {meta.get('collected_at', '?')}")
    lines.append(f"Kurs USD/PLN: {meta.get('usd_pln_rate', '?')}\n")
    for c in data.get("coins", [])[:15]:
        ch24 = c.get("price_change_24h_pct")
        ch24s = f"{ch24:+.1f}%" if ch24 is not None else "?"
        ch7d = c.get("price_change_7d_pct")
        ch7ds = f"{ch7d:+.1f}%" if ch7d is not None else "?"
        lines.append(
            f"{c.get('symbol')}: {c.get('price_pln', '?')} PLN "
            f"(${c.get('price_usd', '?')})  24h: {ch24s}  7d: {ch7ds}  "
            f"rank #{c.get('market_cap_rank', '?')}"
        )
    glob = data.get("global", {})
    if glob:
        cap = glob.get("total_market_cap_usd")
        cap_s = f"${cap/1e12:.2f}T" if cap else "?"
        lines.append(f"\nGlobalna kapitalizacja: {cap_s}")
        lines.append(f"Dominacja BTC: {glob.get('market_cap_percentage_btc', '?')}%")
    return "\n".join(lines)


def _format_ta_preview() -> str:
    """Formatuje podglad analizy technicznej."""
    data = load_json("technical_analysis.json")
    if not data:
        return "(brak danych)"
    lines = [f"Zebrano: {data.get('meta', {}).get('collected_at', '?')}\n"]
    for coin_name, coin_data in data.get("analysis", {}).items():
        daily = coin_data.get("daily", {})
        h4 = coin_data.get("4h", {})
        lines.append(f"--- {coin_name} ---")
        lines.append(f"  Daily: RSI={daily.get('rsi_14','?')} | "
                      f"MACD hist={daily.get('macd_histogram','?')} | "
                      f"BB=[{daily.get('bollinger_lower','?')}-{daily.get('bollinger_upper','?')}] | "
                      f"Sygnal: {daily.get('overall','?')}")
        lines.append(f"  4h:    RSI={h4.get('rsi_14','?')} | "
                      f"MACD hist={h4.get('macd_histogram','?')} | "
                      f"Sygnal: {h4.get('overall','?')}")
        for sig in (daily.get("signals") or [])[:3]:
            lines.append(f"    -> {sig}")
    return "\n".join(lines)


def _format_news_preview() -> str:
    """Formatuje podglad newsow."""
    data = load_json("news_digest.json")
    if not data:
        return "(brak danych)"
    meta = data.get("meta", {})
    lines = [
        f"Zebrano: {meta.get('collected_at', '?')}",
        f"Artykulow: {meta.get('total_articles', 0)}, z trescia: {meta.get('articles_with_content', 0)}\n",
    ]
    for a in data.get("articles", [])[:20]:
        lines.append(f"[{a.get('source')}] {a.get('title')}")
        if a.get("published"):
            lines.append(f"  Data: {a['published'][:30]}")
        if a.get("full_content"):
            lines.append(f"  Tresc: {a['full_content'][:200]}...")
        lines.append("")
    return "\n".join(lines)


def _format_social_preview() -> str:
    """Formatuje podglad social media."""
    data = load_json("social_sentiment.json")
    if not data:
        return "(brak danych)"
    meta = data.get("meta", {})
    lines = [
        f"Zebrano: {meta.get('collected_at', '?')}",
        f"Twitter: {meta.get('twitter_status', '?')}",
        f"Reddit: {meta.get('reddit_status', '?')}\n",
    ]
    tw = data.get("twitter", [])
    if tw:
        for t in tw[:10]:
            lines.append(f"@{t.get('author')}: {t.get('text', '')[:200]}")
            lines.append(f"  {t.get('created_at', '')} | L:{t.get('likes',0)} RT:{t.get('retweets',0)}")
            lines.append("")
    else:
        lines.append("Brak postow z Twittera (brak tokena lub brak danych)")

    rd = data.get("reddit", [])
    if rd:
        for r in rd[:5]:
            lines.append(f"[Reddit] {r}")
    else:
        lines.append("Reddit: placeholder (brak danych)")
    return "\n".join(lines)


def _format_macro_preview() -> str:
    """Formatuje podglad danych makro."""
    data = load_json("macro_context.json")
    if not data:
        return "(brak danych)"
    lines = [f"Zebrano: {data.get('meta', {}).get('collected_at', '?')}\n"]

    fng = data.get("fear_and_greed", {})
    lines.append(f"Fear & Greed Index: {fng.get('value')} ({fng.get('classification')})")
    hist = fng.get("history", [])
    if hist:
        vals = [str(h["value"]) for h in hist]
        lines.append(f"  Historia 7d: {', '.join(vals)}")

    rates = data.get("exchange_rates", {})
    lines.append(f"\nKurs USD/PLN: {rates.get('usd_pln')}")
    lines.append(f"Kurs EUR/PLN: {rates.get('eur_pln')}")

    glob = data.get("global_crypto", {})
    cap = glob.get("total_market_cap_usd")
    lines.append(f"\nGlobalna kapitalizacja: ${cap/1e12:.2f}T" if cap else "Kapitalizacja: ?")
    lines.append(f"Dominacja BTC: {glob.get('btc_dominance_pct', '?')}%")
    lines.append(f"Zmiana 24h: {glob.get('market_cap_change_24h_pct', '?')}%")
    return "\n".join(lines)


def _format_summary_preview() -> str:
    """Formatuje podglad streszczenia."""
    data = load_json("summary.json")
    if not data:
        return "(brak danych — uruchom pelna analize)"
    meta = data.get("meta", {})
    header = f"Model: {meta.get('model', '?')} | Kontekst: {meta.get('context_chars', '?')} znakow\n\n"
    return header + data.get("summary", "(puste streszczenie)")


def run_full_analysis():
    """Uruchamia pelny pipeline multi-agentowy z logami w czasie rzeczywistym."""
    log_lines = []
    lock = threading.Lock()

    def log_cb(msg):
        with lock:
            log_lines.append(msg)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_cb(f"[{timestamp}] Uruchamiam system multi-agentowy...\n")

    # Faza 1
    yield "\n".join(log_lines), "*Faza 1: Zbieranie danych (5 agentow rownolegle)...*"
    collector_results, collector_errors = run_collectors_parallel(log_cb)

    if collector_errors:
        for name, err in collector_errors.items():
            log_cb(f"  BLAD agenta {name}: {err}")

    # Faza 2
    log_cb("")
    yield "\n".join(log_lines), "*Faza 2: Agent sumaryzujacy analizuje dane...*"
    summary_result = run_summarizer(log_cb)

    # Faza 3
    log_cb("")
    yield "\n".join(log_lines), "*Faza 3: Agent decyzyjny przygotowuje plan...*"
    decision_result = run_decision(log_cb)

    log_cb(f"\n[{datetime.now().strftime('%H:%M:%S')}] Pipeline zakonczony!")

    decision_text = decision_result.get("decision", "(brak odpowiedzi)")
    yield "\n".join(log_lines), decision_text


def refresh_all_previews():
    """Odswierza podglad danych wszystkich agentow."""
    return (
        _format_market_preview(),
        _format_ta_preview(),
        _format_news_preview(),
        _format_social_preview(),
        _format_macro_preview(),
        _format_summary_preview(),
    )


# --- Gradio UI ---
with gr.Blocks(title="Asystent Gieldowy — Multi-Agent") as app:
    gr.Markdown("# Asystent Gieldowy — System Multi-Agentowy")
    gr.Markdown(
        f"**Architektura:** 5 agentow zbierajacych → Agent Sumaryzujacy → Agent Decyzyjny → "
        f"Plan inwestycyjny ({BUDGET_PLN} PLN) | Model: `{MODEL_NAME}`"
    )

    with gr.Tabs():
        # --- Tab 1: Pelna analiza ---
        with gr.TabItem("Pelna Analiza"):
            gr.Markdown("### Uruchom pelny pipeline multi-agentowy")
            gr.Markdown(
                "Pipeline: zbiera dane z 5 zrodel rownolegle, sumaryzuje przez LLM, "
                "generuje plan inwestycyjny."
            )
            run_btn = gr.Button(
                "Uruchom pelna analize",
                variant="primary",
                size="lg",
            )
            with gr.Row():
                with gr.Column(scale=1):
                    logs_box = gr.Textbox(
                        label="Logi pipeline",
                        lines=30,
                        interactive=False,
                    )
                with gr.Column(scale=2):
                    result_box = gr.Markdown(
                        label="Plan inwestycyjny",
                        value="*Kliknij 'Uruchom pelna analize' aby rozpoczac...*",
                    )
            run_btn.click(
                fn=run_full_analysis,
                inputs=[],
                outputs=[logs_box, result_box],
            )

        # --- Tab 2: Podglad agentow ---
        with gr.TabItem("Dane Agentow"):
            gr.Markdown("### Podglad danych zebranych przez agentow")
            gr.Markdown("Dane sa zapisywane w `backend/data/`. Odswierz po zakonczeniu analizy.")
            refresh_btn = gr.Button("Odswierz podglad", variant="secondary")

            with gr.Tabs():
                with gr.TabItem("Rynek (ceny)"):
                    market_box = gr.Textbox(
                        label="Agent Rynkowy — market_prices.json",
                        value=_format_market_preview(),
                        lines=25, interactive=False,
                    )
                with gr.TabItem("Analiza Techniczna"):
                    ta_box = gr.Textbox(
                        label="Agent Techniczny — technical_analysis.json",
                        value=_format_ta_preview(),
                        lines=25, interactive=False,
                    )
                with gr.TabItem("Newsy"):
                    news_box = gr.Textbox(
                        label="Agent Newsowy — news_digest.json",
                        value=_format_news_preview(),
                        lines=25, interactive=False,
                    )
                with gr.TabItem("Social Media"):
                    social_box = gr.Textbox(
                        label="Agent Social — social_sentiment.json",
                        value=_format_social_preview(),
                        lines=25, interactive=False,
                    )
                with gr.TabItem("Makro"):
                    macro_box = gr.Textbox(
                        label="Agent Makro — macro_context.json",
                        value=_format_macro_preview(),
                        lines=25, interactive=False,
                    )
                with gr.TabItem("Streszczenie"):
                    summary_box = gr.Textbox(
                        label="Agent Sumaryzujacy — summary.json",
                        value=_format_summary_preview(),
                        lines=25, interactive=False,
                    )

            refresh_btn.click(
                fn=refresh_all_previews,
                inputs=[],
                outputs=[market_box, ta_box, news_box, social_box, macro_box, summary_box],
            )

        # --- Tab 3: Surowe JSON ---
        with gr.TabItem("Surowe JSON"):
            gr.Markdown("### Surowe dane JSON z agentow")
            json_selector = gr.Dropdown(
                label="Wybierz plik JSON",
                choices=[
                    "market_prices.json",
                    "technical_analysis.json",
                    "news_digest.json",
                    "social_sentiment.json",
                    "macro_context.json",
                    "summary.json",
                    "decision.json",
                ],
                value="market_prices.json",
            )
            json_display = gr.Code(
                label="Zawartosc JSON",
                language="json",
                lines=30,
            )
            json_selector.change(
                fn=_read_agent_json,
                inputs=[json_selector],
                outputs=[json_display],
            )

    gr.Markdown(
        "---\n"
        "*System multi-agentowy | Zrodla: CoinGecko, Binance, RSS (CoinDesk, CoinTelegraph, The Block), "
        "Twitter (opcjonalnie), Alternative.me, NBP*"
    )


if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", server_port=7860, theme=gr.themes.Soft())
