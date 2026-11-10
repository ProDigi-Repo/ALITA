"""OpenRouter access via Pydantic AI (chat agents and embeddings).

For requests the API key comes only from the interface (header `X-OpenRouter-Key`);
a server key is never used for that (v0.18.0). Only the ingestion CLI passes a key from
`--api-key` or the environment variable OPENROUTER_API_KEY explicitly. Models are built per key.
"""
from __future__ import annotations

import asyncio
import weakref

from .config import get_settings
from .usage import add_embed


class MissingApiKey(RuntimeError):
    """Raised when a request needs the language model but no OpenRouter key was given."""
    pass


def resolve_key(request_key: str | None = None) -> str:
    """The OpenRouter key sent with the request; raises MissingApiKey when empty."""
    key = (request_key or "").strip()
    if not key:
        raise MissingApiKey("No OpenRouter API key. Enter your key in the interface (top right).")
    return key


# Every chat runs on its own event loop in a worker thread (concurrency.py). An HTTP client belongs to the loop it was
# first used on; reused on the next chat's loop it fails with "Event loop is closed". So clients and the models built
# on them are kept per loop and closed with it (close_loop_clients).
_PER_LOOP: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _loop_cache() -> dict:
    """Cache of the running event loop (a plain dict when called outside a loop)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return {}
    return _PER_LOOP.setdefault(loop, {})


def http_client():
    """The HTTP client of the running event loop."""
    from pydantic_ai.models import create_async_httpx2_client

    cache = _loop_cache()
    c = cache.get("http")
    if c is None or c.is_closed:
        c = cache["http"] = create_async_httpx2_client()
    return c


async def close_loop_clients() -> None:
    """Close the HTTP client of the running loop (called when a chat's own loop ends)."""
    cache = _PER_LOOP.pop(asyncio.get_running_loop(), None) or {}
    c = cache.get("http")
    if c is not None and not c.is_closed:
        await c.aclose()


def chat_model(model_name: str, api_key: str):
    """pydantic-ai chat model for an OpenRouter model name and key (one per event loop)."""
    from pydantic_ai.models.openrouter import OpenRouterModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    cache = _loop_cache()
    key = ("chat", model_name, api_key)
    if key not in cache:
        cache[key] = OpenRouterModel(model_name, provider=OpenRouterProvider(api_key=api_key, http_client=http_client()))
    return cache[key]


def embedder(api_key: str):
    """OpenRouter offers an OpenAI-compatible /embeddings endpoint (one embedder per event loop)."""
    from pydantic_ai import Embedder
    from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
    from pydantic_ai.providers.openai import OpenAIProvider

    cache = _loop_cache()
    key = ("embed", api_key)
    if key not in cache:
        s = get_settings()
        model = OpenAIEmbeddingModel(
            s.embedding_model,
            provider=OpenAIProvider(base_url=s.openrouter_base_url, api_key=api_key, http_client=http_client()),
        )
        cache[key] = Embedder(model)
    return cache[key]


async def embed_documents(texts: list[str], api_key: str, batch: int = 64) -> list[list[float]]:
    """Embeddings for a list of texts, in batches; usage is recorded."""
    out: list[list[float]] = []
    emb = embedder(api_key)
    for i in range(0, len(texts), batch):
        res = await emb.embed_documents(texts[i : i + batch])
        add_embed(res, texts[i : i + batch])
        out.extend([list(v) for v in res.embeddings])
    return out


async def embed_query(text: str, api_key: str) -> list[float]:
    """Embedding of one search query; usage is recorded."""
    res = await embedder(api_key).embed_query(text)
    add_embed(res, [text])
    return list(res.embeddings[0])
