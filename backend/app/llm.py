"""OpenRouter access via Pydantic AI (chat agents and embeddings).

For requests the API key comes only from the interface (header `X-OpenRouter-Key`);
a server key is never used for that (v0.18.0). Only the ingestion CLI passes a key from
`--api-key` or the environment variable OPENROUTER_API_KEY explicitly. Models are built per key.
"""
from __future__ import annotations

from functools import lru_cache

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


@lru_cache(maxsize=32)
def chat_model(model_name: str, api_key: str):
    """pydantic-ai chat model for an OpenRouter model name and key."""
    from pydantic_ai.models.openrouter import OpenRouterModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    return OpenRouterModel(model_name, provider=OpenRouterProvider(api_key=api_key))


@lru_cache(maxsize=8)
def embedder(api_key: str):
    """OpenRouter offers an OpenAI-compatible /embeddings endpoint."""
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
