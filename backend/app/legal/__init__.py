"""Legal-Ontologie (REQ-37/REQ-38): Gesetze, Leitlinien und Standards als strukturierte, versionierte Normen.

Modell nach de Martim (2025), "An Ontology-Driven Graph RAG for Legal Norms" (SAT-Graph RAG, arXiv:2505.00039),
LRMoo-inspiriert und an ELI (European Legislation Identifier) ausgerichtet:

  Norm (Work, eli:LegalResource)                      das Gesetz / die Leitlinie / der Standard als abstraktes Werk
    └─ Component (Component Work, eli:LegalResourceSubdivision)   Kapitel, Artikel/§, Absatz, Nummer, Erwägungsgrund,
                                                                  Anhang, Clause, Randnummer – dauerhafte Identität
         └─ Temporal Version (CTV, LRMoo F2 Expression)  Stand eines Bestandteils über einen Zeitraum
              └─ Language Version (CLV, eli:LegalExpression)  Wortlaut in einer Sprache  ← Text Unit (Chunk)
  Action (Ereignis)   beendet eine CTV und erzeugt eine neue (Erlass, Änderung, Streichung, geänderter Anwendungsbeginn,
                      Änderung im Gesetzgebungsverfahren); hat einen eigenen, eingebetteten Beschreibungstext.

Wie im Paper sind neue Fassungen übergeordneter Teile **Aggregationen**: eine neue Artikel-CTV verweist auf die neue CTV
des geänderten Absatzes und auf die alten CTVs der unveränderten Absätze (keine Kopien). Eine CTV, die über mehrere
Fassungen gleich bleibt, wird wiederverwendet – sie wird auch nur einmal eingebettet.

Zwei Zeitachsen:
  * Geltung: Fassungen mit Inkrafttreten (in_force) bilden eine Kette; eine CTV gilt von valid_from bis valid_to
    (ausschließlich). Abfrage „Stand am Tag t“: valid_from ≤ t < valid_to.
  * Entstehung: Fassungen ohne Inkrafttreten (Vorschlag, Positionen, Entwurf, Konsultationsfassung) haben keine Geltung,
    nur eine Stufe (stage); Abfrage „Stand im Kommissionsvorschlag“: stage ∈ stages der CTV.
Der Anwendungsbeginn (applicable_from) kann je Bestandteil abweichen (z. B. KI-Verordnung) und gehört zur Identität
der CTV: ändert ein Rechtsakt nur das Datum (AI Omnibus), entsteht trotzdem eine neue CTV mit eigener Action.

Die Funktionen ohne Unterstrich sind rein (kein Qdrant/Neo4j) und in tests/test_legal.py getestet.

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
