"""
Orkiestrator — uruchamia agentow zbierajacych rownolegla, potem sumaryzujacy i decyzyjny.

Uzycie:
  python -m backend.agents.run_all          (z katalogu projektu)
  python run_all.py                         (z katalogu backend/agents/)
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Dodaj sciezke backendu do sys.path przy uruchamianiu bezposrednim
_this_dir = Path(__file__).resolve().parent
_backend_dir = _this_dir.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_backend_dir.parent) not in sys.path:
    sys.path.insert(0, str(_backend_dir.parent))


def _import_agents():
    from backend.agents import agent_market
    from backend.agents import agent_technical
    from backend.agents import agent_news
    from backend.agents import agent_social
    from backend.agents import agent_macro
    from backend.agents import agent_summarizer
    from backend.agents import agent_decision
    return agent_market, agent_technical, agent_news, agent_social, agent_macro, agent_summarizer, agent_decision


def run_collectors_parallel(log_callback=None):
    """Uruchamia 5 agentow zbierajacych rownolegle."""
    agent_market, agent_technical, agent_news, agent_social, agent_macro, _, _ = _import_agents()

    collectors = {
        "Rynkowy": agent_market.run,
        "Techniczny": agent_technical.run,
        "Newsowy": agent_news.run,
        "Social": agent_social.run,
        "Makro": agent_macro.run,
    }

    results = {}
    errors = {}

    def _log(msg):
        print(msg)
        if log_callback:
            log_callback(msg)

    _log("=" * 60)
    _log("FAZA 1: Agenci zbierajacy (rownolegle)")
    _log("=" * 60)

    start = time.time()
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for name, func in collectors.items():
            futures[executor.submit(func)] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
                _log(f"  [OK] Agent {name} zakonczony")
            except Exception as e:
                errors[name] = str(e)
                _log(f"  [BLAD] Agent {name}: {e}")

    elapsed = time.time() - start
    _log(f"Faza 1 zakonczona w {elapsed:.1f}s ({len(results)} OK, {len(errors)} bledow)")
    return results, errors


def run_summarizer(log_callback=None):
    """Uruchamia agenta sumaryzujacego."""
    _, _, _, _, _, agent_summarizer, _ = _import_agents()

    def _log(msg):
        print(msg)
        if log_callback:
            log_callback(msg)

    _log("\n" + "=" * 60)
    _log("FAZA 2: Agent Sumaryzujacy")
    _log("=" * 60)

    start = time.time()
    result = agent_summarizer.run()
    elapsed = time.time() - start
    _log(f"Faza 2 zakonczona w {elapsed:.1f}s")
    return result


def run_decision(log_callback=None):
    """Uruchamia agenta decyzyjnego."""
    _, _, _, _, _, _, agent_decision = _import_agents()

    def _log(msg):
        print(msg)
        if log_callback:
            log_callback(msg)

    _log("\n" + "=" * 60)
    _log("FAZA 3: Agent Decyzyjny")
    _log("=" * 60)

    start = time.time()
    result = agent_decision.run()
    elapsed = time.time() - start
    _log(f"Faza 3 zakonczona w {elapsed:.1f}s")
    return result


def run_full_pipeline(log_callback=None):
    """Pelny pipeline: zbieranie -> sumaryzacja -> decyzja."""
    total_start = time.time()

    def _log(msg):
        print(msg)
        if log_callback:
            log_callback(msg)

    _log("Uruchamiam pelny pipeline multi-agentowy...")

    # Faza 1
    collector_results, collector_errors = run_collectors_parallel(log_callback)

    # Faza 2
    summary_result = run_summarizer(log_callback)

    # Faza 3
    decision_result = run_decision(log_callback)

    total_elapsed = time.time() - total_start
    _log(f"\n{'=' * 60}")
    _log(f"PIPELINE ZAKONCZONY w {total_elapsed:.1f}s")
    _log(f"{'=' * 60}")

    return {
        "collectors": collector_results,
        "collector_errors": collector_errors,
        "summary": summary_result,
        "decision": decision_result,
        "total_time_s": round(total_elapsed, 1),
    }


if __name__ == "__main__":
    run_full_pipeline()
