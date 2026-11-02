# Golden comparisons for refactoring

Scripts that run the **same** inputs through two versions of ALITA (e.g. `main` and a refactoring branch) and record
what they produce, so a refactor can be shown to change nothing. Used for REQ-61/74 and REQ-81; not part of CI.

| Script | What it records |
|---|---|
| `chats.py <backend dir> <out.json>` | 28 chat scenarios (Graph Chat branches: named clusters, cluster comparison, project, overview, citations, progress, history, DEO filter; Document Chat streamed and not): every event and what the language model receives (prompt, instructions, history). LLM, embeddings, Qdrant and Neo4j are stubbed. |
| `legal_ingest.py <backend dir> <out.json>` | Legal ingestion of a small law (proposal, adopted, partial amendment, white paper) and a guideline: models, Text Units, documents, project, graph calls. |
| `fake_api.py <backend dir> <port>` | The API on an in-memory index (no Qdrant/Neo4j) for browser checks; `fake_api_accounts.py <backend dir> <port> <data dir>` adds test accounts (not real ones). |
| `ui_clicks.js <port> <tag>`, `ui_login.js <port>`, `ui_tour.js <port>` | Headless browser (Playwright): UI state after a fixed click sequence (password gate, databases, clusters, Compare), the login flow, the guided tour. Screenshots go to `$OUT_DIR`. |

```bash
git worktree add /tmp/base main                      # the version to compare against
python tools/golden/chats.py /tmp/base/backend old.json && python tools/golden/chats.py backend new.json && cmp old.json new.json
python tools/golden/legal_ingest.py /tmp/base/backend old_l.json && python tools/golden/legal_ingest.py backend new_l.json && cmp old_l.json new_l.json
python tools/golden/fake_api.py /tmp/base/backend 8701 & python tools/golden/fake_api.py backend 8702 &
node tools/golden/ui_clicks.js 8701 old > ui_old.json; node tools/golden/ui_clicks.js 8702 new > ui_new.json   # compare the "out" states
```
