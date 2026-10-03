# Embed summaries without the backend

Creates semantic embeddings for the structured summaries via OpenRouter, for example for the offline demo.

1. Put `alita_summaries.json` next to these files. It has the format `{"items": [{"id": "...", "text": "..."}]}`.
2. Windows: double-click `RUN_ME.bat` and paste your OpenRouter key. Other systems: run `python embed_summaries.py`.
3. The result is `alita_embeddings.json`, created with the model `openai/text-embedding-3-large` (3072 dimensions).

The key is only sent to openrouter.ai and is not saved.
