"""Local Ollama embeddings and chat. Nothing is sent off the machine."""

import os
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv

from brain.errors import BrainError

_DEFAULT_BASE = "http://localhost:11434"
_DEFAULT_EMBED = "nomic-embed-text"
_DEFAULT_CHAT = "qwen2.5:7b"


def base_url() -> str:
    load_dotenv()
    return os.getenv("OLLAMA_BASE_URL", _DEFAULT_BASE).strip().rstrip("/") or _DEFAULT_BASE


def embed_model() -> str:
    load_dotenv()
    return os.getenv("OLLAMA_EMBED_MODEL", _DEFAULT_EMBED).strip() or _DEFAULT_EMBED


def chat_model() -> str:
    load_dotenv()
    return os.getenv("OLLAMA_CHAT_MODEL", _DEFAULT_CHAT).strip() or _DEFAULT_CHAT


class OllamaClient:
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = _post("/api/embed", {"model": embed_model(), "input": texts})
        if "embeddings" in payload:
            return [[float(item) for item in vector] for vector in payload["embeddings"]]
        if "embedding" in payload:
            return [[float(item) for item in payload["embedding"]]]
        raise BrainError("ollama_error", "Ollama returned no embeddings.")

    def chat(self, system: str, human: str) -> str:
        payload = _post(
            "/api/chat",
            {
                "model": chat_model(),
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": human},
                ],
            },
        )
        message = payload.get("message") or {}
        content = str(message.get("content") or "").strip()
        if not content:
            raise BrainError("ollama_error", "Ollama returned an empty answer.")
        return content


def embed_batched(embedder, texts: list[str], batch_size: int = 16) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(embedder.embed(texts[start : start + batch_size]))
    return vectors


def _post(path: str, payload: dict) -> dict:
    url = urljoin(base_url() + "/", path.lstrip("/"))
    try:
        response = httpx.post(url, json=payload, timeout=120)
    except httpx.HTTPError as exc:
        raise BrainError(
            "ollama_down",
            f"Ollama is not running at {base_url()}. Start it with ollama serve, then pull {embed_model()} and {chat_model()}.",
        ) from exc
    if response.status_code != 200:
        detail = response.text.strip()[:400] or f"HTTP {response.status_code}"
        raise BrainError("ollama_error", detail)
    return response.json()
