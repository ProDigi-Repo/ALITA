"""Legal ontology (REQ-37/REQ-38): laws, guidelines and standards as structured, versioned norms.

Model after de Martim (2025), "An Ontology-Driven Graph RAG for Legal Norms" (SAT-Graph RAG, arXiv:2505.00039),
inspired by LRMoo and aligned with ELI (European Legislation Identifier):

  Norm (Work, eli:LegalResource)                      the law / guideline / standard as an abstract work
    └─ Component (Component Work, eli:LegalResourceSubdivision)   chapter, article/§, paragraph, point, recital,
                                                                  annex, clause, margin number – lasting identity
         └─ Temporal Version (CTV, LRMoo F2 Expression)  state of a component over a period
              └─ Language Version (CLV, eli:LegalExpression)  wording in one language  ← Text Unit (chunk)
  Action (event)      ends a CTV and creates a new one (enactment, amendment, repeal, changed start of application,
                      change in the legislative procedure); has its own embedded description text.

As in the paper, new versions of higher-level parts are **aggregations**: a new article CTV refers to the new CTV of
the amended paragraph and to the old CTVs of the unchanged paragraphs (no copies). A CTV that stays the same across
several versions is reused – and embedded only once.

Two time axes:
  * Validity: versions with entry into force (in_force) form a chain; a CTV is valid from valid_from to valid_to
    (exclusive). Query "state on day t": valid_from ≤ t < valid_to.
  * Genesis: versions without entry into force (proposal, positions, draft, consultation version) are not in force,
    they only have a stage; query "state in the Commission proposal": stage ∈ stages of the CTV.
The start of application (applicable_from) may differ per component (e.g. AI Act) and is part of the identity of
the CTV: if an act only changes the date (AI Omnibus), a new CTV with its own action is created anyway.

The functions without a leading underscore are pure (no Qdrant/Neo4j) and tested in tests/test_legal.py.

Package layout (3.13.0, REQ-81): ``common`` (constants, helpers), ``parse`` (components in the text), ``history``
(Temporal Versions and Actions), ``query`` (queries on a model, references in questions), ``units`` (Text Units).
Everything is importable from ``app.legal`` as before.
"""
from .common import *  # noqa: F401,F403
from .common import _h, _uuid  # noqa: F401
from .history import *  # noqa: F401,F403
from .parse import *  # noqa: F401,F403
from .query import *  # noqa: F401,F403
from .units import *  # noqa: F401,F403
