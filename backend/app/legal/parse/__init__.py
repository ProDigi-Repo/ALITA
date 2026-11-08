"""Legal ontology – recognising components (title, chapter, article, paragraph, point, recital, annex, clause …)
in the text of a law, guideline, standard or FAQ, their labels and their document order.

REQ-105: ``patterns`` (component class, line patterns, cleaning, outline helpers), ``faq`` (questions and answers),
``components`` (laws, guidelines, standards), ``order`` (labels, document order, partial versions).
"""
from .components import parse_components  # noqa: F401
from .faq import _FAQ_FOOTER, _Q_START, _SENT_END, parse_faq  # noqa: F401
from .order import _ROMAN_V, _TOP_RANK, _roman, _seg_key, ancestors, component_label, doc_order_key, merge_partial  # noqa: F401
from .patterns import (  # noqa: F401
    _ANNEX,
    _ANNEX_CLAUSE,
    _ANNEX_STATUS,
    _ARTICLE,
    _BACK_MATTER,
    _BARE_NUM,
    _CA,
    _CHAPTER,
    _CLAUSE,
    _DEF_EN,
    _ENACTING,
    _FN_LINE,
    _FOOTNOTE,
    _LINE_SKIP,
    _MARGIN,
    _MARGIN_P,
    _NUM_DE,
    _OJ_FOOTER,
    _PAGE_OF,
    _PARA_DE,
    _PARA_EN,
    _PARA_SIGN,
    _POINT_DE,
    _POINT_EN,
    _RECITAL,
    _ROMAN,
    _ROMAN_SEC,
    _SECTION,
    _SUPPLEMENT,
    _TITLE,
    _TOC_LEADER,
    CA_MARK,
    Component,
    _is_reference,
    _next_in_outline,
    clean_lines,
    detect_style,
)
