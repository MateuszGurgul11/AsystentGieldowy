import httpx
import json
from config import get_settings


async def ollama_chat(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    stream: bool = False,
) -> str:
    """Wywołuje Ollama API i zwraca odpowiedź jako string."""
    settings = get_settings()
    url = f"{settings.ollama_url}/api/chat"
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]


async def ollama_chat_stream(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.4,
    max_tokens: int = 2048,
):
    """Generator streamujący odpowiedź token po tokenie."""
    settings = get_settings()
    url = f"{settings.ollama_url}/api/chat"
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue


async def ollama_available() -> bool:
    """Sprawdza czy Ollama jest dostępna."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            return r.status_code == 200
    except Exception:
        return False
