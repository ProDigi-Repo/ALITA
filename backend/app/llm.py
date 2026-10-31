"""OpenRouter-Anbindung über Pydantic AI (Chat-Agents und Embeddings).

Der API-Key kommt bei Anfragen ausschließlich aus dem Interface (Header `X-OpenRouter-Key`);
ein Server-Key wird dafür nie benutzt (v0.18.0). Nur das Einlese-CLI (ingest) übergibt einen Key
aus `--api-key` bzw. der Umgebungsvariable OPENROUTER_API_KEY explizit. Modelle werden pro Key gebaut.
"""
from __future__ import annotations

from functools import lru_cache

from .config import get_settings
from .usage import add_embed


class MissingApiKey(RuntimeError):
    pass


def resolve_key(request_key: str | None = None) -> str:
    key = (request_key or "").strip()
    if not key:
        raise MissingApiKey("No OpenRouter API key. Enter your key in the interface (top right).")
    return key


@lru_cache(maxsize=32)
def chat_model(model_name: str, api_key: str):
    from pydantic_ai.models.openrouter import OpenRouterModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    return OpenRouterModel(model_name, provider=OpenRouterProvider(api_key=api_key))


@lru_cache(maxsize=8)
def embedder(api_key: str):
    """OpenRouter bietet einen OpenAI-kompatiblen /embeddings-Endpunkt."""
    from pydantic_ai import Embedder
    from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
    from pydantic_ai.providers.openai import OpenAIProvider

    s = get_settings()
    model = OpenAIEmbeddingModel(
        s.embedding_model,
        provider=OpenAIProvider(base_url=s.openrouter_base_url, api_key=api_key),
    )
    return Embedder(model)


async def embed_documents(texts: list[str], api_key: str, batch: int = 64) -> list[list[float]]:
    out: list[list[float]] = []
    emb = embedder(api_key)
    for i in range(0, len(texts), batch):
        res = await emb.embed_documents(texts[i : i + batch])
        add_embed(res, texts[i : i + batch])
        out.extend([list(v) for v in res.embeddings])
    return out


async def embed_query(text: str, api_key: str) -> list[float]:
    res = await embedder(api_key).embed_query(text)
    add_embed(res, [text])
    return list(res.embeddings[0])
