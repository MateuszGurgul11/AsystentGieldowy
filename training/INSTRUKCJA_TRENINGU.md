# Jak wytrenować model – instrukcja krok po kroku

## Schemat procesu

```
PC (Windows, AMD GPU)           Google Colab (darmowe T4 GPU)
┌──────────────────┐            ┌──────────────────────────┐
│ 1. Napisz dane   │            │                          │
│    treningowe     │ ──upload──→│ 2. Uruchom finetune_colab│
│    (JSONL)       │            │    ~10-15 min            │
│                  │            │                          │
│ 4. ollama create │ ←download──│ 3. Pobierz plik .gguf    │
│    invest-assist │            │    (~2 GB)               │
└──────────────────┘            └──────────────────────────┘
```

---

## Etap 1: Dane treningowe (na PC)

Plik `training_data.jsonl` już istnieje z 20 przykładami.
Każda linia to JSON z polami `instruction` i `output`:

```json
{"instruction": "pytanie / dane wejściowe", "output": "odpowiedź asystenta"}
```

### Jak dodać więcej danych?

Otwórz `training_data.jsonl` i dopisuj nowe linie. Kategorie do pokrycia:

| Kategoria | Przykładów docelowo | Już jest |
|-----------|--------------------:|--------:|
| Wskaźniki techniczne (RSI, MACD, BB, SMA) | 50+ | 8 |
| Ocena portfela / dywersyfikacja | 30+ | 4 |
| Sentyment wiadomości | 30+ | 4 |
| Ryzyko (Sharpe, drawdown, zmienność) | 20+ | 4 |
| Strategie (DCA, B&H, momentum) | 15+ | 2 |
| Symulacje ("co gdybym...") | 10+ | 1 |
| **SUMA** | **~150–200** | **23** |

Im więcej danych → lepszy model. Minimum 200 par dla przyzwoitych wyników.

### Zasady pisania danych:
- Odpowiedzi po polsku
- Zawsze podawaj uzasadnienie
- Dodawaj "Poziom pewności: wysoki/średni/niski"
- Odpowiedzi 2–5 zdań (zwięzłe ale treściwe)
- Nie obiecuj zysków, dodawaj zastrzeżenia

---

## Etap 2: Fine-tuning na Google Colab

### Krok po kroku:

1. **Otwórz Google Colab:** https://colab.research.google.com

2. **Utwórz nowy notebook** (File → New notebook)

3. **Zmień runtime na GPU:**
   - Runtime → Change runtime type → **T4 GPU** → Save

4. **W pierwszej komórce** – instalacja (skopiuj i uruchom):
   ```python
   !pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
   !pip install --no-deps trl peft accelerate bitsandbytes
   !pip install xformers
   ```

5. **Upload danych treningowych:**
   - W panelu bocznym Colab (ikona folderu) kliknij "Upload"
   - Wgraj plik `training_data.jsonl`

6. **W kolejnych komórkach** – skopiuj kod z `finetune_colab.py`:
   - Podziel na komórki po komentarzach "KROK 1", "KROK 2" itd.
   - Uruchom po kolei

7. **Trening potrwa ~10–15 minut** na T4 GPU (przy 20–200 przykładach)

8. **Po treningu** – model automatycznie się przetestuje i wyeksportuje do GGUF

---

## Etap 3: Pobranie pliku .gguf

Po zakończeniu kroku 7 w skrypcie, w folderze `invest-assistant-gguf/` pojawi się plik `.gguf`.

**W Colab:**
```python
# Sprawdź jaki plik powstał:
!ls -la invest-assistant-gguf/

# Pobierz na dysk:
from google.colab import files
files.download('invest-assistant-gguf/unsloth.Q4_K_M.gguf')
```

Plik waży ~2 GB – pobieranie może potrwać chwilę.

---

## Etap 4: Wczytanie do Ollama (na PC)

### 4.1 Przenieś plik .gguf

Przenieś pobrany plik do folderu projektu:
```
d:\Programowanie\Asystent giełdowy - praca inżynierska\training\models\
```

### 4.2 Utwórz Modelfile

Utwórz plik `Modelfile` (bez rozszerzenia) w folderze `training\`:

```
FROM ./models/unsloth.Q4_K_M.gguf

SYSTEM """Jesteś inteligentnym asystentem inwestycyjnym. Analizujesz wskaźniki techniczne (RSI, MACD, Bollinger Bands, średnie kroczące), oceniasz portfele pod kątem dywersyfikacji i ryzyka, analizujesz sentyment wiadomości finansowych i generujesz rekomendacje w języku polskim. Zawsze podawaj uzasadnienie i poziom pewności."""

PARAMETER temperature 0.3
PARAMETER num_ctx 2048
PARAMETER stop "<|eot_id|>"
```

### 4.3 Zarejestruj model w Ollama

```powershell
cd "d:\Programowanie\Asystent giełdowy - praca inżynierska\training"
ollama create invest-assistant -f Modelfile
```

### 4.4 Testuj!

```powershell
ollama run invest-assistant
```

```
>>> RSI Tesli = 22, MACD przechodzi przez linię sygnału od dołu. Co robić?
```

### 4.5 Sprawdź że nowy model jest na liście

```powershell
ollama list
```

Powinno pokazać:
```
NAME                ID         SIZE     MODIFIED
invest-assistant    abc123     2.0 GB   Just now
llama3.2:3b         a80c4f17   2.0 GB   ...
```

---

## Szybka alternatywa: Modelfile BEZ treningu

Jeśli chcesz natychmiast mieć "asystenta inwestycyjnego" bez fine-tuningu:

```powershell
ollama create invest-assistant -f - <<EOF
FROM llama3.2:3b

SYSTEM """Jesteś inteligentnym asystentem inwestycyjnym. Analizujesz wskaźniki techniczne (RSI, MACD, Bollinger Bands, średnie kroczące), oceniasz portfele pod kątem dywersyfikacji i ryzyka, analizujesz sentyment wiadomości finansowych i generujesz rekomendacje w języku polskim. Zawsze podawaj uzasadnienie i poziom pewności: wysoki/średni/niski. Nigdy nie gwarantuj zysków."""

PARAMETER temperature 0.3
PARAMETER num_ctx 2048
EOF
```

To tworzy model z system promptem ale BEZ fine-tuningu. Działa od razu.

---

## Iteracja: jak polepszać model

```
     Testuj model
          ↓
   Znajdź słabe odpowiedzi
          ↓
   Dopisz lepsze przykłady do training_data.jsonl
          ↓
   Ponownie fine-tuning na Colab
          ↓
   Nowy .gguf → ollama create
          ↓
     Testuj model (powtórz)
```

Każda iteracja: ~20 min (upload + trening + download + ollama create).
