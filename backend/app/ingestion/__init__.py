"""Ingestion: files and project folders -> records -> summaries -> chunks/vectors (Qdrant) and graph (Neo4j).

Modules: ``scan`` (files -> records), ``summaries`` (LLM enrichment), ``index`` (chunks, embeddings, graph sync),
``followups`` (re-cluster, citations, provisions after a run), ``pipeline`` (project/file/bulk runs) and ``cli``.
Legal texts have their own pipeline in ``app.legal_ingest`` that reuses these steps.
"""
from .options import IngestOptions, Item
from .pipeline import ingest_all, ingest_file, ingest_project

__all__ = ["IngestOptions", "Item", "ingest_all", "ingest_file", "ingest_project"]
