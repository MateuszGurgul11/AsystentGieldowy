# =============================================================================
# Fine-tuning Llama 3.2 3B dla Asystenta Inwestycyjnego
# Uruchom w Google Colab (Runtime → Change runtime type → T4 GPU)
# =============================================================================

# --- KROK 1: Instalacja ---
# Odkomentuj i uruchom w Colab:
"""
!pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
!pip install --no-deps trl peft accelerate bitsandbytes
!pip install xformers
"""

import os
os.environ["TRANSFORMERS_NO_FLASH_ATTENTION"] = "1"

from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset

# --- KROK 2: Załaduj model bazowy ---
MODEL_NAME = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
MAX_SEQ_LENGTH = 2048

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=True,
    dtype=None,
)

# --- KROK 3: Dodaj adaptery LoRA ---
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=16,
    lora_dropout=0,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    bias="none",
    use_gradient_checkpointing="unsloth",
)

# --- KROK 4: Przygotuj dane treningowe ---
SYSTEM_PROMPT = (
    "Jesteś inteligentnym asystentem inwestycyjnym. "
    "Analizujesz wskaźniki techniczne, oceniasz portfele, "
    "analizujesz sentyment wiadomości i generujesz rekomendacje po polsku. "
    "Zawsze podawaj uzasadnienie i poziom pewności."
)

def format_example(example):
    """Formatuje dane do szablonu Llama 3.2 chat."""
    text = (
        f"<|begin_of_text|>"
        f"<|start_header_id|>system<|end_header_id|>\n\n"
        f"{SYSTEM_PROMPT}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n\n"
        f"{example['instruction']}<|eot_id|>"
        f"<|start_header_id|>assistant<|end_header_id|>\n\n"
        f"{example['output']}<|eot_id|>"
    )
    return {"text": text}

# Załaduj plik JSONL z danymi (upload do Colab lub z Google Drive)
dataset = load_dataset("json", data_files="training_data.jsonl", split="train")
dataset = dataset.map(format_example)

print(f"Liczba przykładów treningowych: {len(dataset)}")
print(f"\nPrzykład sformatowany:\n{dataset[0]['text'][:500]}...")

# --- KROK 5: Trenuj ---
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,
    dataset_num_proc=2,
    packing=False,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=5,
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=True,
        logging_steps=1,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=42,
        output_dir="outputs",
        report_to="none",
    ),
)

print("\nRozpoczynam trening...")
stats = trainer.train()
print(f"\nTrening zakończony! Czas: {stats.metrics['train_runtime']:.0f}s")

# --- KROK 6: Test modelu po treningu ---
FastLanguageModel.for_inference(model)

test_prompts = [
    "RSI dla akcji NVIDIA wynosi 25, MACD jest ujemny. Co sugerujesz?",
    "Mam portfel: 90% kryptowaluty, 10% gotówka. Oceń ryzyko.",
    "Przeanalizuj sentyment: 'Apple ogłosił buyback akcji za 100 miliardów dolarów.'",
]

for prompt in test_prompts:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    inputs = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
    ).to("cuda")

    outputs = model.generate(input_ids=inputs, max_new_tokens=256, temperature=0.3)
    response = tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
    print(f"\n{'='*60}")
    print(f"PYTANIE: {prompt}")
    print(f"ODPOWIEDŹ: {response}")

# --- KROK 7: Eksport do GGUF (do Ollama) ---
print("\nEksportuję model do formatu GGUF...")
model.save_pretrained_gguf(
    "invest-assistant-gguf",
    tokenizer,
    quantization_method="q4_k_m",
)
print("Gotowe! Plik GGUF zapisany w: invest-assistant-gguf/")
print("Pobierz plik .gguf i przenieś na PC → Ollama")

# --- KROK 8 (opcjonalnie): Zapisz też adapter LoRA ---
model.save_pretrained("invest-assistant-lora")
tokenizer.save_pretrained("invest-assistant-lora")
print("Adapter LoRA zapisany w: invest-assistant-lora/")
