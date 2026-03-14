# Jak model LLM wpisuje się w założenia projektu

## Zasada nr 1: LLM NIE robi matematyki

```
BACKEND (Python/pandas)          LLM (Llama 3.2 3B)
─────────────────────           ───────────────────
Liczy RSI, MACD, SMA        →  Interpretuje: "RSI 28 = wyprzedanie"
Liczy wartość portfela       →  Komentuje: "Portfel za mocno w tech"
Liczy Sharpe, drawdown       →  Ocenia: "Ryzyko: wysokie, bo..."
Pobiera newsy z API          →  Klasyfikuje sentyment
Symuluje DCA/buy&hold        →  Podsumowuje wynik symulacji
```

LLM to **warstwa języka**, nie kalkulator. Backend liczy liczby, LLM je interpretuje.

---

## Mapowanie: każde założenie → kto co robi

### 1. Analiza portfela użytkownika

| Funkcja | Kto robi | Jak |
|---------|----------|-----|
| Aktualna wartość portfela | **Backend** | Yahoo Finance API → cena × ilość |
| Zysk / strata | **Backend** | (wartość_obecna - wartość_zakupu) / wartość_zakupu |
| Alokacja aktywów | **Backend** | udział % każdego typu |
| Wykres wartości w czasie | **Backend** → **Flutter** | dane historyczne → fl_chart |
| Dywersyfikacja | **Backend** liczy → **LLM** interpretuje | Backend: liczba sektorów, korelacje. LLM: "za dużo tech" |

**Co LLM musi umieć:** Dostaje JSON z danymi portfela → generuje czytelne podsumowanie.

**Przykład promptu w produkcji:**
```
[DANE PORTFELA]
Wartość: 45 230 PLN
Zmiana 7d: -3.2%
Zmiana 30d: +8.1%
Alokacja: tech 65%, krypto 20%, obligacje 10%, gotówka 5%
Liczba pozycji: 7
Najlepsza: NVIDIA (+45%)
Najgorsza: Bitcoin (-12%)

[ZADANIE] Podsumuj stan portfela i oceń dywersyfikację.
```

### 2. Alerty inwestycyjne

| Funkcja | Kto robi | Jak |
|---------|----------|-----|
| Sprawdzanie reguł (cena ±X%) | **Backend** | cron job co 5 min, porównanie cen |
| Sprawdzanie RSI | **Backend** | obliczenie RSI, porównanie z progami |
| Sprawdzanie wolumenu | **Backend** | wolumen vs średnia |
| Generowanie treści alertu | **LLM** | "Akcje Apple spadły o 6% – możliwa okazja" |

**Co LLM musi umieć:** Dostaje typ alertu + dane → generuje ludzki komunikat.

**Przykład promptu w produkcji:**
```
[ALERT]
Typ: cena_spadek
Symbol: AAPL
Zmiana: -6.2% (dziś)
RSI: 31
Wolumen: 2.3x średnia
Cena: $178.50

[ZADANIE] Wygeneruj alert dla użytkownika (1-2 zdania).
```

### 3. Analiza techniczna

| Funkcja | Kto robi | Jak |
|---------|----------|-----|
| Obliczanie RSI | **Backend** | pandas: rsi = ta.RSI(close, 14) |
| Obliczanie MACD | **Backend** | pandas: macd, signal, hist |
| Obliczanie SMA/EMA | **Backend** | pandas: rolling mean |
| Bollinger Bands | **Backend** | SMA ± 2*std |
| Interpretacja wskaźników | **LLM** | "RSI 28 + MACD ujemny = wyprzedanie" |

**Co LLM musi umieć:** Dostaje WSZYSTKIE wskaźniki jako liczby → łączy je w spójną interpretację.

**Przykład promptu w produkcji:**
```
[WSKAŹNIKI TECHNICZNE]
Symbol: TSLA
Cena: $245.30
RSI(14): 28
MACD: -3.45
MACD Signal: -2.10
MACD Histogram: -1.35
SMA 50: $262.00
SMA 200: $248.50
Bollinger Upper: $275.00
Bollinger Lower: $240.00
Wolumen: 1.8x średnia

[ZADANIE] Zinterpretuj sygnały techniczne. Podaj rekomendację i poziom pewności.
```

### 4. Rekomendacje inwestycyjne (AI) ← GŁÓWNA ROLA LLM

| Funkcja | Kto robi | Jak |
|---------|----------|-----|
| Zbieranie danych | **Backend** | portfel + wskaźniki + sentyment + ryzyko |
| Łączenie wszystkiego w rekomendację | **LLM** | analiza kontekstu → "sprzedaj/kupuj/trzymaj + dlaczego" |

**Co LLM musi umieć:** Dostaje KOMPLET danych → generuje spersonalizowaną rekomendację.

**Przykład promptu w produkcji:**
```
[PORTFEL UŻYTKOWNIKA]
Wartość: 45 230 PLN
Alokacja: tech 65%, krypto 20%, obligacje 10%, gotówka 5%
Sharpe ratio: 0.4
Max drawdown: -35%
Zmienność: 22%

[WSKAŹNIKI - NVIDIA]
RSI: 72, MACD: pozytywny, cena > SMA200

[WSKAŹNIKI - BITCOIN]
RSI: 35, MACD: ujemny, cena < SMA50

[SENTYMENT WIADOMOŚCI]
NVIDIA: pozytywny (3/5 artykułów pozytywnych)
Bitcoin: negatywny (regulacje w EU)

[ZADANIE] Wygeneruj 2-3 rekomendacje dla tego portfela.
```

### 5. Symulator inwestowania

| Funkcja | Kto robi | Jak |
|---------|----------|-----|
| Symulacja DCA | **Backend** | pętla: co miesiąc kup za X zł, oblicz wynik |
| Symulacja buy & hold | **Backend** | kup raz, trzymaj, oblicz wynik |
| Symulacja momentum | **Backend** | kupuj rosnące, sprzedawaj spadające |
| Podsumowanie wyników | **LLM** | "DCA dałoby +32%, buy&hold +28%..." |

**Przykład promptu w produkcji:**
```
[WYNIKI SYMULACJI]
Kwota: 10 000 PLN
Okres: 2023-01 do 2025-12 (3 lata)
Instrument: S&P 500 ETF

DCA (500 PLN/mies.): końcowa wartość 13 200 PLN (+32%)
Buy & Hold: końcowa wartość 12 800 PLN (+28%)
Momentum: końcowa wartość 14 100 PLN (+41%)

[ZADANIE] Porównaj strategie i zasugeruj najlepszą dla początkującego inwestora.
```

### 6. Analiza sentymentu wiadomości ← LLM ROBI BEZPOŚREDNIO

| Funkcja | Kto robi | Jak |
|---------|----------|-----|
| Pobieranie newsów | **Backend** | Yahoo/Alpha Vantage/NewsAPI |
| Klasyfikacja sentymentu | **LLM** | czyta nagłówek → pozytywny/neutralny/negatywny |
| Agregacja | **Backend** | liczy % pozytywnych/negatywnych |

**To jedyne zadanie gdzie LLM działa „sam"** — czyta tekst i klasyfikuje.

**Przykład promptu w produkcji:**
```
[WIADOMOŚCI - TESLA]
1. "Tesla odnotowała rekordową sprzedaż w Q4"
2. "Elon Musk sprzedał akcje Tesli za 2 mld USD"
3. "Tesla otwiera nową fabrykę w Meksyku"
4. "Analitycy obniżają cenę docelową Tesli o 15%"
5. "Tesla wygrywa kontrakt rządowy na 500 pojazdów"

[ZADANIE] Dla każdej wiadomości podaj: sentyment (POZYTYWNY/NEUTRALNY/NEGATYWNY) i krótkie uzasadnienie. Na końcu podaj ogólny sentyment.
```

### 7. Dashboard inwestora

| Funkcja | Kto robi |
|---------|----------|
| Wartość portfela | **Backend** → **Flutter** (karta z liczbą) |
| Najlepsze/najgorsze aktywo | **Backend** → **Flutter** (lista) |
| Wykresy | **Backend** (dane) → **Flutter** (fl_chart) |
| Rekomendacje | **Backend** → **LLM** → **Flutter** (tekst) |

LLM generuje teksty rekomendacji, reszta to dane + UI.

### 8. Ocena ryzyka portfela

| Funkcja | Kto robi | Jak |
|---------|----------|-----|
| Zmienność (std dev) | **Backend** | numpy: np.std(returns) * sqrt(252) |
| Sharpe ratio | **Backend** | (mean_return - rf) / std_return |
| Max drawdown | **Backend** | max(peak - trough) / peak |
| Korelacje | **Backend** | pandas: df.corr() |
| Ocena słowna | **LLM** | "Ryzyko: wysokie, bo drawdown -45%..." |

**Przykład promptu w produkcji:**
```
[METRYKI RYZYKA]
Zmienność roczna: 25%
Sharpe ratio: 0.35
Max drawdown: -42%
Korelacja tech-krypto: 0.85
Beta portfela: 1.3

[ZADANIE] Oceń ryzyko portfela (niskie/średnie/wysokie). Wyjaśnij dlaczego i co zmienić.
```

---

## Wniosek: czego LLM musi się nauczyć

Model NIE musi znać cen akcji ani liczyć RSI. Musi umieć:

### Typ 1: Interpretacja danych strukturalnych
Dostaje JSON/tekst z liczbami z backendu → generuje ludzki komentarz.

### Typ 2: Klasyfikacja sentymentu
Dostaje tekst wiadomości → klasyfikuje: pozytywny/neutralny/negatywny.

### Typ 3: Generowanie rekomendacji
Dostaje komplet danych (portfel + wskaźniki + sentyment + ryzyko) → generuje spersonalizowaną radę.

### Typ 4: Podsumowania
Dostaje wyniki obliczeń (symulacja, ryzyko) → generuje czytelne podsumowanie.

---

## Jak to zmienia dane treningowe?

Obecne dane w `training_data.jsonl` to prosty format:
```
użytkownik pyta → model odpowiada
```

Ale w produkcji model będzie dostawał **strukturalne dane z backendu**. Dane treningowe powinny to odzwierciedlać:

```json
{
  "instruction": "[WSKAŹNIKI]\nSymbol: AAPL\nRSI: 28\nMACD: -3.45\nSMA50: $192\nSMA200: $188\nBollinger: cena przy dolnym paśmie\nWolumen: 1.5x średnia\n\n[ZADANIE] Zinterpretuj sygnały techniczne.",
  "output": "Akcje Apple wykazują sygnały wyprzedania. RSI 28 (poniżej 30) to klasyczny próg wyprzedania. MACD ujemny (-3.45) potwierdza spadkowe momentum. Cena przy dolnym paśmie Bollingera i powyżej SMA 200 ($188) sugeruje, że długoterminowy trend jest nadal wzrostowy mimo krótkoterminowej słabości. Wolumen 1.5x powyżej średniej wskazuje na zwiększone zainteresowanie. Łącznie: potencjalna okazja zakupowa z stop-lossem poniżej SMA 200. Poziom pewności: średni."
}
```

### Kategorie danych treningowych (docelowo):

| Kategoria | Typ zadania | Min. przykładów |
|-----------|------------|----------------:|
| Interpretacja wskaźników (dane struct.) | Typ 1 | 50 |
| Ocena portfela (dane struct.) | Typ 1 + 3 | 40 |
| Sentyment wiadomości | Typ 2 | 40 |
| Rekomendacje (komplet danych) | Typ 3 | 40 |
| Podsumowanie symulacji | Typ 4 | 20 |
| Ocena ryzyka (dane struct.) | Typ 1 | 20 |
| Generowanie alertów | Typ 1 | 20 |
| **SUMA** | | **~230** |
