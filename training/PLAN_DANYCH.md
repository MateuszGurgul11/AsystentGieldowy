# Plan danych treningowych — konkretna rekomendacja

## Ograniczenia, które dyktują wybór

| Ograniczenie | Wpływ na decyzję |
|---|---|
| **Model 3B** (mały) | Max ~50–70K rekordów. Więcej = overfitting, gorsza generalizacja |
| **Colab free T4** (15 GB VRAM, timeout ~4h) | Trening na 50K rekordów QLoRA ≈ 1–2h. Na 200K ≈ 6–8h → nie zmieści się |
| **Jetson 8 GB RAM** | Model musi zostać 3B. Bielik 4.5B (Q4 ≈ 2.7 GB) — ciasno ale możliwe |
| **Język polski** | Kluczowy wymóg — brak gotowych polskich datasetów finansowych |
| **Analiza techniczna** | Największa luka — brak datasetu RSI/MACD/BB w formacie instrukcyjnym |

---

## Werdykt: NIE dawaj wszystkiego

500K+ rekordów w model 3B to przepis na:
- Overfitting (model zapamiętuje zamiast uczyć się)
- Rozwodnienie wiedzy (za dużo szumu)
- Timeout na Colabie (nie zdąży)

**Optymalny rozmiar: 40 000–60 000 rekordów** starannie dobranych.

---

## Rekomendowany miks danych

### Warstwa 1: Wiedza finansowa (angielski) — ~25 000 rekordów

| Dataset | Ile wziąć | Z ilu dostępnych | Dlaczego |
|---------|----------|-------------------|----------|
| **fingpt-fiqa_qa** | **Wszystkie 17 100** | 17 100 | Najwyższa jakość, prawdziwe pytania inwestorów |
| **Finance-Alpaca** | **8 000** (filtrowane) | 68 912 | Praktyczne Q&A — wybrać te o inwestowaniu, portfelach, ryzyku. Odrzucić podatki US, ubezpieczenia, hipoteki |

**Czemu nie:**
- ~~Sujet-Finance-177k~~ → nakłada się z Finance-Alpaca i FinGPT, dużo duplikatów
- ~~Finance-Instruct-500k~~ → za duży, za dużo szumu, autor sam przyznaje
- ~~Investopedia-229k~~ → licencja NC, edukacyjny ton zamiast praktycznego

### Warstwa 2: Sentyment (angielski) — ~10 000 rekordów

| Dataset | Ile wziąć | Dlaczego |
|---------|----------|----------|
| **FinGPT Sentiment** | **10 000** (z 76K) | Bezpośrednio pokrywa moduł sentymentu z założeń. Wybrać najczystsze przykłady. |

### Warstwa 3: Polski język — ~10 000 rekordów

| Źródło | Ile | Jak |
|--------|-----|-----|
| **pl_alpaca_data_cleaned** | **5 000** | Ogólne instrukcje po polsku — uczy model mówić po polsku |
| **Tłumaczenie fingpt-fiqa_qa** | **3 000** (najlepszych) | Przetłumaczyć GPT-4o / Claude → polski. Koszt: ~$5–10 |
| **MultiFin (polskie nagłówki)** | **2 000** | Przeformatować na: nagłówek → sentyment + uzasadnienie |

### Warstwa 4: Analiza techniczna (syntetyczna, polska) — ~5 000 rekordów

**To trzeba WYGENEROWAĆ** — nie istnieje gotowy dataset.

| Kategoria | Ile | Przykład formatu |
|-----------|-----|-----------------|
| RSI interpretacja | 800 | `[DANE] RSI: 28 → [ODP] Wyprzedanie...` |
| MACD interpretacja | 800 | `[DANE] MACD: -3.4, Signal: -2.1 → [ODP]...` |
| Bollinger Bands | 600 | `[DANE] Cena przy dolnym paśmie → [ODP]...` |
| Średnie kroczące (SMA/EMA) | 600 | `[DANE] Golden cross SMA50/200 → [ODP]...` |
| Łączenie wskaźników | 800 | `[DANE] RSI + MACD + BB razem → [ODP]...` |
| Alerty z danych | 600 | `[ALERT] Typ: cena_spadek → [ODP]...` |
| Ocena portfela z danych | 500 | `[PORTFEL] Tech 60%, krypto 25% → [ODP]...` |
| Ocena ryzyka z metryk | 400 | `[RYZYKO] Sharpe: 0.3, DD: -45% → [ODP]...` |

**Jak wygenerować:** Skrypt Pythona z szablonami + losowe wartości wskaźników → prompt do GPT-4o/Claude → odpowiedź. Koszt: ~$15–30 za 5K rekordów.

### Warstwa 5: Własne ręczne przykłady — ~500 rekordów

To co już mamy (32) + dopisane ręcznie. Format produkcyjny (strukturalne dane z backendu). Najważniejsza warstwa — bo to DOKŁADNIE format jaki model zobaczy w aplikacji.

---

## Podsumowanie miksu

```
┌─────────────────────────────────────────────────┐
│         MIKS TRENINGOWY: ~50 000 rekordów        │
│                                                  │
│  ████████████████████  25K  Ang. wiedza finans.  │
│  ██████████           10K  Ang. sentyment        │
│  ██████████           10K  Polski język          │
│  █████                 5K  Analiza tech. (synt.) │
│  █                     0.5K Własne (produkcyjne) │
└─────────────────────────────────────────────────┘

Język:  ~55% angielski, ~45% polski
```

Model uczy się wiedzy finansowej z angielskiego (bo tam są dane), a polskiego z warstwy 3 + 4. W praktyce Llama 3.2 3B dobrze transferuje wiedzę między językami.

---

## A co z Bielikiem?

| Cecha | Llama 3.2 3B | Bielik v3 1.5B | Bielik v3 4.5B |
|-------|-------------|----------------|----------------|
| Rozmiar (Q4) | ~2.0 GB | ~1.0 GB | ~2.7 GB |
| Polski natywnie | Średni | Bardzo dobry | Bardzo dobry |
| Wiedza finansowa | Lepsza (większy pretraining) | Gorsza (mniej parametrów) | Porównywalna |
| Prędkość na Jetsonie | ~52 tok/s | ~100 tok/s | ~35 tok/s |
| Ekosystem (Ollama, Unsloth) | Pełne wsparcie | Mniejsze wsparcie | Mniejsze wsparcie |
| Fine-tuning Unsloth | ✅ Oficjalnie | ⚠️ Wymaga konfiguracji | ⚠️ Wymaga konfiguracji |

**Rekomendacja:** Zostań przy **Llama 3.2 3B**. Powody:
1. Już działa u Ciebie w Ollama
2. Pełne wsparcie Unsloth + Ollama + Jetson
3. Oficjalne benchmarki NVIDIA na Jetsonie
4. 3B > 1.5B w jakości odpowiedzi
5. Brak polskiego łatasz tłumaczeniem danych (łatwiej niż portowanie Bielika)

**Ale:** Warto potem przetestować Bielik 4.5B jako porównanie w pracy inżynierskiej (fajny rozdział: "Porównanie Llama 3.2 3B vs Bielik 4.5B na zadaniach finansowych po polsku").

---

## Kolejność działań — co robić TERAZ

### Etap A: Szybki test (1 dzień, koszt: $0)
1. Pobierz `fingpt-fiqa_qa` (17K) z HuggingFace
2. Skonwertuj do formatu Llama 3.2
3. Fine-tuning na Colabie (~30 min)
4. Test: czy model lepiej odpowiada na pytania finansowe?

### Etap B: Pełny angielski (2–3 dni, koszt: $0)
5. Dodaj 8K z Finance-Alpaca (filtrowane)
6. Dodaj 10K z FinGPT Sentiment
7. Dodaj nasze 32 ręczne przykłady
8. Fine-tuning na ~35K rekordów

### Etap C: Polskojęzyczny (3–5 dni, koszt: ~$20–40)
9. Przetłumacz 3K najlepszych z fingpt-fiqa_qa na polski
10. Dodaj 5K z pl_alpaca_data_cleaned
11. Wygeneruj 2–3K syntetycznych par o analizie technicznej (po polsku)
12. Fine-tuning na pełnym miksie ~50K

### Etap D: Dopracowanie (ciągły)
13. Dopisuj własne przykłady w formacie produkcyjnym
14. Testuj, poprawiaj, iteruj

---

## Skrypt do pobrania i konwersji datasetów

Użyj tego w Google Colab lub lokalnie:

```python
from datasets import load_dataset

# 1. fingpt-fiqa_qa — najlepszy jakościowo
fiqa = load_dataset("FinGPT/fingpt-fiqa_qa", split="train")
print(f"FinGPT FiQA: {len(fiqa)} rekordów")
# Kolumny: instruction, input, output → gotowe

# 2. Finance-Alpaca — filtrujemy
alpaca = load_dataset("gbharti/finance-alpaca", split="train")
print(f"Finance-Alpaca: {len(alpaca)} rekordów")
# Kolumny: instruction, input, output → gotowe
# Filtruj: odrzuć rekordy o US tax, insurance, mortgage

# 3. FinGPT Sentiment
sentiment = load_dataset("FinGPT/fingpt-sentiment-train", split="train")
print(f"FinGPT Sentiment: {len(sentiment)} rekordów")

# 4. pl_alpaca_data_cleaned
pl_alpaca = load_dataset("mmosiolek/pl_alpaca_data_cleaned", split="train")
print(f"Polish Alpaca: {len(pl_alpaca)} rekordów")

# 5. MultiFin — tylko polskie rekordy
multifin = load_dataset("awinml/MultiFin", split="train")
pl_multifin = multifin.filter(lambda x: x["language"] == "pl")
print(f"MultiFin (PL): {len(pl_multifin)} rekordów")
```
