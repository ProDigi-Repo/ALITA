"""Discourse Elements Ontology (DEO) und Document Components Ontology (DoCO) – SPAR-Ontologien.

DEO beschreibt die *rhetorische* Rolle eines Textteils (Methods, Results, …), DoCO die *Struktur*
(Section, Paragraph, …). Quelle: Constantin et al., The Document Components Ontology (DoCO),
Semantic Web 7 (2016) 167–181; Ontologien unter http://purl.org/spar/deo und http://purl.org/spar/doco.

Dieses Modul ist ohne Abhängigkeiten nutzbar (Ingestion, Qdrant-Filter, Neo4j-Graph, Tests):
- DEO_CLASSES: die 31 Klassen mit kurzer Definition
- deo_for_heading(): Überschrift (EN/DE) -> DEO-Klassen
- detect_heading(): erkennt Abschnittsüberschriften in Fließtext (PDF-Zeilen)
- SUMMARY_DEO: Felder der Structured Summary -> DEO-Klassen
- deo_for_question(): welche DEO-Klassen eine Frage anspricht (Graph RAG)
"""
from __future__ import annotations

import re

DEO_NS = "http://purl.org/spar/deo/"
DOCO_NS = "http://purl.org/spar/doco/"

# Die 31 Klassen der DEO (Wurzel deo:DiscourseElement); Definitionen gekürzt.
DEO_CLASSES: dict[str, str] = {
    "DiscourseElement": "An element of a document that carries out a rhetorical function.",
    "Acknowledgements": "Thanks to people and organizations that helped with the work.",
    "AuthorContribution": "Description of the roles played by each author.",
    "Background": "Background knowledge that sets the scene for the work.",
    "BibliographicReference": "A reference to another publication (journal article, book, website …).",
    "Biography": "Information about the life of the author(s).",
    "Caption": "Text accompanying another item, such as a figure or table.",
    "Conclusion": "A reflection on the preceding text, summarizing the evidence and arguments.",
    "Contribution": "Statement of the contribution of the work to the field.",
    "Data": "A textual description of the data used in the work.",
    "DatasetDescription": "Information describing a dataset.",
    "Dedication": "Text naming the person(s) the work is dedicated to.",
    "Discussion": "Interpretation and discussion of the results, including limitations and implications.",
    "Epilogue": "A concluding piece at the end of a literary work.",
    "Evaluation": "A consideration of the value, meaning and significance of the results.",
    "ExternalResourceDescription": "Description of an external resource, e.g. a website or software.",
    "FutureWork": "A proposal for new investigations to continue and advance the work.",
    "Introduction": "The initial description that states the purpose and goals of the text.",
    "Legend": "Informative text explaining the symbols of a figure, map or chart.",
    "Materials": "Documentation of the specific materials used in the work.",
    "Methods": "Documentation of the methods used in the work.",
    "Model": "A description of a model used or produced by the work.",
    "Motivation": "A description of the motivation for the work.",
    "Postscript": "Text added after the main body, e.g. at the end of a letter.",
    "ProblemStatement": "A concise description of the issues the work addresses.",
    "Prologue": "A separate introductory section at the beginning of a work.",
    "Reference": "A reference to a part of the same document or to another publication.",
    "RelatedWork": "A critical review of related works and the current state of knowledge.",
    "Results": "A report of the specific findings of an investigation.",
    "Scenario": "A presentation of a use case or test, based on a real or hypothetical situation.",
    "SupplementaryInformationDescription": "A description of supplementary information, e.g. an appendix.",
}

# Überschrift -> DEO (Reihenfolge: spezifisch vor allgemein). Englisch und Deutsch.
_HEADING_RULES: list[tuple[str, list[str]]] = [
    (r"materials? (and|&|und) methods?|material (und|&) methode", ["Materials", "Methods"]),
    (r"data (and|&) methods?|daten (und|&) method", ["Data", "Methods"]),
    (r"results? (and|&) discussion|ergebnisse (und|&) diskussion", ["Results", "Discussion"]),
    (r"limitations?|limitationen|grenzen der (studie|untersuchung)|implications?|implikationen", ["Discussion"]),
    (r"future (work|research)|outlook|ausblick|weitere forschung", ["FutureWork"]),
    (r"related (work|research)|literature review|prior (work|research)|forschungsstand|stand der forschung|literaturüberblick", ["RelatedWork"]),
    (r"theoretical (background|framework)|theoretischer (hintergrund|rahmen)|background|hintergrund|theor(y|ie)", ["Background"]),
    (r"problem statement|problemstellung|research questions?|forschungsfragen?", ["ProblemStatement"]),
    (r"motivation", ["Motivation"]),
    (r"hypothes[ei]s|research model|conceptual model|forschungsmodell|\bmodel(l)?\b", ["Model"]),
    (r"method(s|ology)?|methodik|methoden?|research design|study design|forschungsdesign|procedure|vorgehen(sweise)?|empirical (approach|study)|measures?|messung", ["Methods"]),
    (r"participants?|sample|stichprobe|teilnehmer|materials?", ["Materials"]),
    (r"\bdata\b|daten(satz|basis)?|dataset", ["Data"]),
    (r"results?|findings|ergebnisse|befunde", ["Results"]),
    (r"evaluation|evaluierung|robustness|robustheit", ["Evaluation"]),
    (r"discussion|diskussion", ["Discussion"]),
    (r"conclusions?|concluding remarks|fazit|schluss(folgerung|betrachtung)?|zusammenfassung und ausblick", ["Conclusion"]),
    (r"contributions?|beitrag", ["Contribution"]),
    (r"introduction|einleitung|einführung", ["Introduction"]),
    (r"acknowledge?ments?|danksagung", ["Acknowledgements"]),
    (r"author contributions?|credit author statement", ["AuthorContribution"]),
    (r"references|bibliography|literatur(verzeichnis)?|quellen(verzeichnis)?|works cited", ["BibliographicReference"]),
    (r"appendix|anhang|supplementary|supplemental", ["SupplementaryInformationDescription"]),
    (r"scenarios?|use cases?|anwendungsfall", ["Scenario"]),
]
_HEADING_RULES_RX = [(re.compile(rf"^(?:{rx})\b", re.I), cls) for rx, cls in _HEADING_RULES]
ABSTRACT_RX = re.compile(r"^(abstract|summary|kurzfassung|zusammenfassung)$", re.I)
_NUMBERING = re.compile(r"^\s*(?:[IVX]+\.|\d+(?:\.\d+)*\.?|[A-Z]\.)\s+")


def clean_heading(text: str) -> str:
    return _NUMBERING.sub("", (text or "").strip()).strip(" .:-–\t")


def deo_for_heading(heading: str | None) -> list[str]:
    """DEO-Klassen für eine Abschnittsüberschrift ([] = unbekannt). 'Abstract' ist SALT (sro:Abstract), kein DEO."""
    h = clean_heading(heading or "").lower()
    if not h or ABSTRACT_RX.match(h):
        return []
    for rx, classes in _HEADING_RULES_RX:
        if rx.search(h):
            return list(classes)
    return []


def detect_heading(line: str) -> str | None:
    """Ist eine Textzeile (z. B. aus einem PDF) eine Abschnittsüberschrift? Liefert die bereinigte Überschrift.
    Kurz, ohne Satzende, entweder nummeriert oder ein bekannter Abschnittsname (auch in GROSSBUCHSTABEN)."""
    raw = (line or "").strip()
    if not raw or len(raw) > 80 or raw.endswith((".", ",", ";")) and not _NUMBERING.match(raw):
        return None
    text = clean_heading(raw)
    if not text or len(text.split()) > 8 or not text[0].isalpha():
        return None
    known = bool(deo_for_heading(text)) or bool(ABSTRACT_RX.match(text))
    numbered = bool(_NUMBERING.match(raw)) and text[0].isupper() and len(text.split()) <= 6
    if known and (numbered or text.isupper() or text.istitle() or len(text.split()) <= 4):
        return text
    if numbered and not text.endswith((".", ":")) and sum(c.isdigit() for c in text) < 3:
        return text
    return None


# Structured Summary (Emerald-Schema) -> DEO
SUMMARY_DEO: dict[str, list[str]] = {
    "purpose": ["Motivation", "ProblemStatement"],
    "design_methodology_approach": ["Methods"],
    "findings": ["Results"],
    "research_limitations_implications": ["Discussion", "FutureWork"],
    "originality_value": ["Contribution"],
    "practical_implications": ["Discussion"],
}

# Frage -> DEO (Graph RAG): welche Art von Textteil beantwortet sie am ehesten?
_QUESTION_RULES: list[tuple[str, list[str]]] = [
    (r"\bmethod|methodolog|design|approach|how (was|were|did).*(measur|stud|analy|collect)|sample|participants|survey|experiment|interview|regression|methode|vorgehen|stichprobe", ["Methods", "Materials"]),
    (r"\bdata\b|dataset|daten", ["Data", "DatasetDescription"]),
    (r"result|finding|effect|outcome|show(s|ed)?|evidence|ergebnis|befund|wirkung", ["Results", "Evaluation"]),
    (r"limitation|weakness|bias|caveat|threat|grenze|schwäche|einschränkung", ["Discussion"]),
    (r"implication|meaning|interpret|discuss|bedeutung|diskussion", ["Discussion", "Conclusion"]),
    (r"future|next step|open question|outlook|ausblick|zukunft|weiter", ["FutureWork"]),
    (r"\bwhy\b|motivat|purpose|goal|aim|problem|research question|warum|ziel|zweck|forschungsfrage", ["Motivation", "ProblemStatement", "Introduction"]),
    (r"contribut|novel|original|new about|beitrag|neu", ["Contribution"]),
    (r"related work|literature|prior|state of the art|forschungsstand|literatur", ["RelatedWork", "Background"]),
    (r"conclu|takeaway|summary|fazit|zusammenfass", ["Conclusion"]),
    (r"theor|framework|model|hypothes|modell", ["Model", "Background"]),
    (r"\bcit(e|es|ed|ation)|reference|zitier|quelle", ["BibliographicReference"]),
]
_QUESTION_RX = [(re.compile(rx, re.I), cls) for rx, cls in _QUESTION_RULES]


def deo_for_question(question: str, limit: int = 4) -> list[str]:
    out: list[str] = []
    for rx, classes in _QUESTION_RX:
        if rx.search(question or ""):
            out += [c for c in classes if c not in out]
    return out[:limit]


def valid(classes: list[str] | None) -> list[str]:
    """Nur bekannte DEO-Klassen, Schreibweise normalisiert (case-insensitiv)."""
    by_lower = {k.lower(): k for k in DEO_CLASSES}
    out = []
    for c in classes or []:
        k = by_lower.get(str(c).replace("deo:", "").strip().lower())
        if k and k not in out:
            out.append(k)
    return out
