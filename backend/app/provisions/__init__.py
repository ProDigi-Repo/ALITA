"""REQ-68: edges in the knowledge graph from papers to the provisions they discuss (REQ-105: split into a package).

A paper cites "Art. 33(4) AI Act" – meaning the numbering of the version the authors had in front of them
(e.g. the Commission proposal of 2021). ALITA
  1. finds the references in the text (``refs``: articles, paragraphs, letters, annexes, recitals; references to other
     acts such as the GDPR, the TFEU or the Charter are skipped),
  2. assigns them to a law of the collection (``refs.pick_norm``: name of the law nearby or in the whole paper),
  3. determines the version the paper refers to and maps the provision to the current numbering (``resolve.Resolver``:
     text comparison, Art. 33 of the proposal -> Art. 31 today),
  4. stores the links and rebuilds them for the whole index (``link``), and gives the chats and the document details
     what they need (``chat``).

Result: document payload `discusses`, chunk payload `provisions` (["eu-ai-act#art_31", …], current numbers) and in
the graph (:Document)-[:DISCUSSES]->(:Component), (:Chunk)-[:REFERS_TO]->(:Component). No LLM, no embeddings.
"""
from .chat import LAW_PASSAGES, MAX_LINES, PAPER_PASSAGES, asked_articles, chat_passages, chat_scope, discussed_in  # noqa: F401
from .link import _doc_date, _quote_near, by_article, describe, laws_of, link_document, links, rebuild  # noqa: F401
from .refs import (  # noqa: F401
    _ANX_RX,
    _ART_RX,
    _ITEM,
    _NUM,
    _OTHER_AFTER,
    _OTHER_BEFORE,
    _PAR,
    _PARA_WORD,
    _REC_RX,
    _ROMAN,
    BIB,
    LEGAL_TYPES,
    _cid_variants,
    _items,
    _other_act,
    _tokens,
    aliases,
    find_refs,
    label,
    log,
    pick_norm,
)
from .resolve import Resolver, _jac, _norm, _shingles  # noqa: F401
