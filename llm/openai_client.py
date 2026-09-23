"""OpenAI: chat_json() для structured output. Все вызовы кэшируются."""
import json, os
from dotenv import load_dotenv
from . import cache

load_dotenv()
_client = None


def client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def chat_json(prompt: str, system: str = "Отвечай только валидным JSON.", strong: bool = False) -> dict:
    model = os.getenv("OPENAI_MODEL_STRONG" if strong else "OPENAI_MODEL_FAST")
    if not model:
        raise RuntimeError("Не задана модель в .env (OPENAI_MODEL_FAST / OPENAI_MODEL_STRONG)")
    payload = {"model": model, "system": system, "prompt": prompt}
    hit = cache.get("chat", payload)
    if hit is not None:
        return hit
    r = client().chat.completions.create(
        model=model, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
    text = r.choices[0].message.content.strip().removeprefix("```json").removesuffix("```").strip()
    return cache.put("chat", payload, json.loads(text))
