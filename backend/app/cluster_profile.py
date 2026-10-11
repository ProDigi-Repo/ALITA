"""Profil eines Clusters für die Hover-Karte: zentrale Erkenntnisse, verwendete Analysen, Theorien.

Zwei Quellen, die sich ergänzen:
- LLM (beim Clustern mit API-Key): cluster_insights / cluster_analyses / cluster_theories am Dokument
- Heuristik aus den Structured Summaries (immer verfügbar): Methoden-IDs, Analyse- und Theorie-Begriffe,
  erster Satz der Findings der typischsten Dokumente
Das Frontend hat dieselbe Heuristik für die Demo ohne Backend (index.html, clusterProfileLocal).
"""
from __future__ import annotations

import re
from collections import Counter

ANALYSES: list[tuple[str, str]] = [
    (r"pls[- ]?sem|smart ?pls|partial least squares", "PLS-SEM"),
    (r"structural equation|\bsem\b|strukturgleichung", "Structural equation modeling"),
    (r"multi-?level|hierarchical linear|mehrebenen", "Multilevel analysis"),
    (r"regression", "Regression analysis"),
    (r"(confirmatory|exploratory) factor|factor analysis|faktorenanalyse", "Factor analysis"),
    (r"\banova\b|\bmanova\b|varianzanalyse|t-test", "ANOVA / t-tests"),
    (r"meta-?analys", "Meta-analysis"),
    (r"systematic (literature )?review|literature review|literaturanalyse|semi-systematic", "Literature review"),
    (r"vignette", "Vignette study"),
    (r"experiment", "Experiment"),
    (r"survey|questionnaire|fragebogen|umfrage", "Survey"),
    (r"interview", "Interviews"),
    (r"focus group|fokusgruppe", "Focus groups"),
    (r"case stud|fallstudie", "Case study"),
    (r"delphi", "Delphi study"),
    (r"grounded theory", "Grounded theory"),
    (r"thematic analysis|qualitative content analysis|inhaltsanalyse|coding", "Qualitative content analysis"),
    (r"eye[- ]?tracking", "Eye tracking"),
    (r"simulation|system dynamics model", "Simulation"),
    (r"process mining|event log", "Process mining"),
    (r"design science", "Design science"),
    (r"action research|aktionsforschung", "Action research"),
    (r"mixed[- ]method", "Mixed methods"),
    (r"field study|feldstudie", "Field study"),
    (r"text mining|topic model|clustering|embedding", "Text mining / clustering"),
    (r"conceptual|konzeptionell", "Conceptual analysis"),
]

THEORIES: list[tuple[str, str]] = [
    (r"signal(l)?ing theory|signaling perspective", "Signaling theory"),
    (r"status quo bias", "Status quo bias"),
    (r"technology acceptance model|\btam\b", "Technology acceptance model"),
    (r"\butaut\b|unified theory of acceptance", "UTAUT"),
    (r"diffusion of innovation", "Diffusion of innovations"),
    (r"cognitive load", "Cognitive load theory"),
    (r"cognitive fit", "Cognitive fit theory"),
    (r"need for (cognitive )?closure", "Need for closure"),
    (r"mental models?|shared mental model|team mental model", "Mental models"),
    (r"system dynamics|stock[- ]and[- ]flow|stock-flow", "System dynamics"),
    (r"organi[sz]ational learning", "Organizational learning"),
    (r"knowledge management|wissensmanagement", "Knowledge management"),
    (r"job characteristics model|hackman", "Job characteristics model"),
    (r"job demands[- ]resources", "Job demands-resources model"),
    (r"self-determination", "Self-determination theory"),
    (r"(procedural|organi[sz]ational) justice|justice theory", "Organizational justice"),
    (r"instrumental-symbolic", "Instrumental-symbolic framework"),
    (r"ability,? benevolence,? (and )?integrity|trust factors|integrative model of (organizational )?trust", "Trust model (ability, benevolence, integrity)"),
    (r"anthropomorphi", "Anthropomorphism"),
    (r"socio-?technical", "Sociotechnical systems"),
    (r"institutional theory", "Institutional theory"),
    (r"resource-based view", "Resource-based view"),
    (r"dynamic capabilit", "Dynamic capabilities"),
    (r"lean (management|production|principles)|\blean\b", "Lean management"),
    (r"\bagile\b|agilit", "Agile"),
    (r"theory of planned behavio", "Theory of planned behavior"),
    (r"affective events", "Affective events theory"),
    (r"emotion", "Emotion theories"),
    (r"routine", "Organizational routines"),
    (r"stakeholder theory", "Stakeholder theory"),
    (r"legitimacy", "Legitimacy theory"),
    (r"sustainab|nachhaltig", "Sustainability management"),
    (r"gamification", "Gamification"),
    (r"bounded rationality|heuristics and biases", "Bounded rationality"),
]
_GENERIC = re.compile(r"\b([A-Z][\w-]+(?:[ -][A-Za-z][\w-]+){0,2})\s+(theory|theorie)\b")
_STOP = {"the", "a", "an", "this", "our", "grounded", "new", "existing"}


def _text(d: dict) -> str:
    su = d.get("summary") if isinstance(d.get("summary"), dict) else {}
    return " ".join(str(su.get(k) or "") for k in ("purpose", "design_methodology_approach", "findings",
                                                    "research_limitations_implications", "originality_value"))


def first_sentence(t: str, n: int = 170) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    s = m.group(1) if m else t
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def heuristic(members: list[dict], method_labels: dict[str, str] | None = None) -> dict:
    method_labels = method_labels or {}
    an, th = Counter(), Counter()
    for d in members:
        txt = _text(d)
        low = txt.lower()
        design = str((d.get("summary") or {}).get("design_methodology_approach") or "").lower()
        found = {label for rx, label in ANALYSES if re.search(rx, design or low)}
        for m in d.get("method_ids") or []:
            m = m.get("id") if isinstance(m, dict) else (m[0] if isinstance(m, (list, tuple)) else m)
            if m:
                found.add(method_labels.get(str(m), str(m).replace("_", " ").capitalize()))
        an.update(found)
        theo = {label for rx, label in THEORIES if re.search(rx, low)}
        for m in _GENERIC.finditer(txt):
            words = m.group(1).split()
            if words[0].lower() not in _STOP:
                theo.add(f"{m.group(1)} theory")
        th.update(theo)
    typical, seen = [], set()
    for d in sorted([d for d in members if isinstance(d.get("summary"), dict) and d["summary"].get("findings")],
                    key=lambda d: -(d.get("cluster_score") or 0)):
        k = first_sentence(str(d["summary"]["findings"]))
        if k not in seen:
            seen.add(k)
            typical.append(d)
    typical = typical[:3]
    insights = [{"text": first_sentence(str(d["summary"]["findings"])), "title": d.get("title"), "doc_id": d.get("doc_id")} for d in typical]
    return {"analyses": [{"name": k, "n": v} for k, v in an.most_common(6)],
            "theories": [{"name": k, "n": v} for k, v in th.most_common(6)],
            "insights": insights, "documents": len(members), "source": "summaries"}


def profile(members: list[dict], llm: dict | None = None, method_labels: dict[str, str] | None = None) -> dict:
    """Heuristik + (falls vorhanden) LLM-Aussagen. LLM-Erkenntnisse stehen vorn, Analysen/Theorien werden vereinigt."""
    p = heuristic(members, method_labels)
    llm = llm or {}
    if llm.get("insights"):
        p["insights"] = [{"text": t, "title": None, "doc_id": None} for t in llm["insights"]] + p["insights"][:2]
        p["source"] = "llm+summaries"
    for key in ("analyses", "theories"):
        have = {x["name"].lower() for x in p[key]}
        p[key] = [{"name": n, "n": None} for n in (llm.get(key) or []) if n.lower() not in have] + p[key]
        p[key] = p[key][:7]
    years = [d["year"] for d in members if isinstance(d.get("year"), int)]
    p["years"] = [min(years), max(years)] if years else None
    return p
