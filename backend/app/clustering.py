"""Automatisches Clustering auf Basis der Structured Summaries (Vektor "summary" in Qdrant).

Datenpunkte (eine Einheit je Werk, nicht je Datei):
  - jedes research paper und jede research note mit Summary,
  - jedes research project als Ganzes (Projekt-Summary, Vektor "summary" in {prefix}projects).
Dateien eines Projekts (Daten, Versionen, Korrespondenz …) werden nicht selbst geclustert, sie
erben den Cluster ihres Projekts (cluster_basis = "project", cluster_score = None).

Der Vektor ist das Embedding von Titel + Purpose, Design/Methodology/Approach, Findings,
Research limitations/implications, Originality/value. Fehlende oder veraltete Vektoren
(Payload summary_key ≠ Hash des Textes) werden beim Lauf nachberechnet, sofern ein API-Key da ist.
Qdrant selbst clustert nicht: wir lesen die Vektoren, clustern mit k-means (Cosinus) und schreiben:

  cluster_id     int   (stabil nur innerhalb eines Laufs)
  cluster_label  str   die prägnantesten Begriffe des Clusters (c-TF-IDF)
  cluster_score  float Cosinus-Ähnlichkeit zum Cluster-Zentrum (0..1, höher = typischer)
  cluster_k      int   Anzahl Cluster im Lauf
  cluster_run    str   Zeitpunkt des Laufs (ISO)
  cluster_basis  str   "summary" (eigener Punkt, Embedding) oder "project" (geerbt)
Geclustert wird ausschließlich auf Embeddings (semantisch). Wortstatistik dient nur dazu, Cluster-Namen aus
prägnanten Begriffen zu bilden; die inhaltliche Beschreibung schreibt das LLM.
  cluster_x/_y   float 2D-Position für die Cluster-Karte (PCA der Summary-Vektoren, -1..1)
  cluster_title  str  beschreibender Kurzname, immer gesetzt (REQ-04): vom LLM, sonst aus den prägnantesten Wortpaaren
                      der Titel/Purposes gebildet (cluster_title_source "llm" | "terms"); innerhalb eines Laufs eindeutig
  cluster_description  str  1–2 Sätze Beschreibung (LLM, Namen pseudonymisiert; ohne Key leer)
  cluster_alt_id int   zweitnächster Cluster (Brücke; Kanten im Cluster-Graphen), cluster_alt_score dessen Ähnlichkeit

Nur numpy, keine weitere Abhängigkeit. Die Funktionen sind auch ohne Qdrant nutzbar (Tests, Demo).
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from datetime import datetime, timezone

import numpy as np

from .usage import add_run

log = logging.getLogger("clustering")

STOP = set("""
a an and are as at be been but by can could do does for from had has have how if in into is it its may
more most not of on or our should so such than that the their them then there these they this those to
under was we were what when where which while who will with within without would you your also using use
used based between both each other one two three new study paper results research data approach
der die das und oder nicht mit ist für auf den dem des ein eine einer eines zu von im in als auch wie bei
sich sind wird werden kann können zur zum über durch nach aus noch nur so dass es sie wir ihr
story stories repost medium member members share listen unsplash photo footer beta follow written responses
get unlimited access less week become open app okay got way easy promote work start building book podcast
website newsletter place create once apply click recommended followers http https www doi org com pdf von
read min according dann einen german english also
title purpose design methodology originality value findings limitations implications practical
argue argues argued series blog post posts article articles element elements case cases level levels studies things
thing structure increase increases decreases key provides provide shows show explains explain discusses discuss describes
describe overview outlines several various many first small sample author authors part paper's note notes showing through abstract drawing draws drawn sharing samples
""".split())


# --------------------------------------------------------------- Pseudonymisierung
# Klarnamen von Personen dürfen in Cluster-Bezeichnungen nicht auftauchen. Erkannte Namen werden
# stabil (gleicher Name -> gleiches Pseudonym) durch Pokémon-Namen ersetzt.
POKEMON = """Pikachu Bulbasaur Charmander Squirtle Jigglypuff Meowth Psyduck Snorlax Eevee Togepi Mew Mewtwo
Vulpix Growlithe Abra Machop Geodude Ponyta Slowpoke Magnemite Gastly Onix Cubone Lapras Ditto Vaporeon Jolteon
Flareon Porygon Dratini Chikorita Cyndaquil Totodile Pichu Marill Sudowoodo Wooper Umbreon Espeon Snubbull
Teddiursa Phanpy Treecko Torchic Mudkip Ralts Mawile Aron Plusle Minun Roselia Wailmer Swablu Bagon Beldum
Turtwig Chimchar Piplup Shinx Pachirisu Buneary Riolu Snivy Tepig Oshawott Zorua Litwick Froakie Fennekin
Rowlet Litten Popplio Mimikyu Grookey Scorbunny Sobble Wooloo Yamper Sprigatito Fuecoco Quaxly""".split()

NAME_CONTEXT = re.compile(
    r"\b([A-ZÄÖÜ][a-zäöüß]{2,}(?:-[A-ZÄÖÜ][a-zäöüß]+)?)(?=,\s*[A-Z]\.|\s+et al|\s*\((?:19|20)\d{2}|\s+and\s+[A-Z][a-z]+\s*\((?:19|20)\d{2})")


# Aufzählungen von Namen ohne Jahreszahl, wie sie in Summaries vorkommen: "Simon, Kahneman and Tversky",
# "Parasuraman and Riley's framework". Ob es wirklich Namen sind, entscheidet der Großschreibungs-Test unten.
_CAP = r"[A-ZÄÖÜ][a-zäöüß]{2,}(?:-[A-ZÄÖÜ][a-zäöüß]+)?"
NAME_LIST = re.compile(rf"\b(?:{_CAP},\s+)*{_CAP}\s+(?:and|&|und)\s+{_CAP}\b")


EMAIL_NAME = re.compile(r"\b([A-Za-z]{2,})[._]([A-Za-z][A-Za-z\-]+)\s*@")


def name_tokens(texts: list[str], known_names: list[str] | None = None) -> set[str]:
    """Personennamen (klein geschrieben): aus Autor:innen-Metadaten und aus Zitiermustern im Text
    ('Müller, A.', 'Meyer et al', 'Schmidt (2019)', 'Schmidt and Lee (2020)', 'Simon, Kahneman and Tversky')."""
    out: set[str] = set()
    for n in known_names or []:
        out.update(p.lower() for p in re.split(r"[\s,.-]+", n) if len(p) > 2)
    cited = Counter(m for t in texts for m in NAME_CONTEXT.findall(t))
    listed = Counter(w for t in texts for span in NAME_LIST.findall(t) for w in re.findall(_CAP, span))
    lower = Counter(w for t in texts for w in re.findall(r"\b[a-zäöüß]{3,}\b", t))
    # nur Wörter, die im Korpus (fast) immer großgeschrieben vorkommen – sonst sind es normale Wörter
    out.update(w.lower() for w, c in cited.items() if lower[w.lower()] <= 0.1 * c)
    # Aufzählungen sind unsicherer (auch Titel wie "Trust and Control"): dort gar kein Kleinschreib-Vorkommen
    # und nicht in einem Titel (Zeile "Title: …")
    titles = " ".join(l for t in texts for l in t.splitlines() if l.startswith("Title:"))
    out.update(w.lower() for w in listed if lower[w.lower()] == 0 and w not in titles)
    for t in texts:
        # E-Mail-Adressen der Form vorname.nachname@… verraten Namen zuverlässig
        for first, last in EMAIL_NAME.findall(t):
            out.add(first.lower())
            out.update(p.lower() for p in last.split("-") if len(p) > 2)
    return out - STOP


def pseudonym(name: str, salt: str = "") -> str:
    import hashlib

    h = int(hashlib.sha256((salt + name.lower()).encode()).hexdigest(), 16)
    return POKEMON[h % len(POKEMON)]


def pseudonymize_terms(terms: list[str], names: set[str], salt: str = "") -> list[str]:
    return [pseudonym(t, salt) if t.lower() in names else t for t in terms]


# --------------------------------------------------------------- Kernalgorithmen
def _normalize(X: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(X, axis=1, keepdims=True)
    n[n == 0] = 1
    return X / n


def kmeans(X: np.ndarray, k: int, seed: int = 7, iters: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Sphärisches k-means (Cosinus) mit k-means++-Start. X wird normalisiert erwartet."""
    rng = np.random.default_rng(seed)
    n = len(X)
    centers = [X[rng.integers(n)]]
    for _ in range(1, k):
        d = 1 - np.max(X @ np.array(centers).T, axis=1)
        d = np.clip(d, 0, None) ** 2
        p = d / d.sum() if d.sum() > 0 else None
        centers.append(X[rng.choice(n, p=p)])
    C = np.array(centers)
    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        new = np.argmax(X @ C.T, axis=1)
        if _ > 0 and np.array_equal(new, labels):
            break
        labels = new
        for j in range(k):
            members = X[labels == j]
            C[j] = members.mean(axis=0) if len(members) else X[rng.integers(n)]
        C = _normalize(C)
    return labels, C


def silhouette(X: np.ndarray, labels: np.ndarray, sample: int = 800, seed: int = 7) -> float:
    """Silhouette mit Cosinus-Distanz, bei vielen Dokumenten auf einer Stichprobe."""
    idx = np.arange(len(X))
    if len(X) > sample:
        idx = np.random.default_rng(seed).choice(len(X), sample, replace=False)
    Xs, ls = X[idx], labels[idx]
    D = 1 - Xs @ Xs.T
    scores = []
    for i in range(len(Xs)):
        same = ls == ls[i]
        if same.sum() <= 1:
            scores.append(0.0)
            continue
        a = D[i, same].sum() / (same.sum() - 1)
        b = min((D[i, ls == c].mean() for c in set(ls.tolist()) if c != ls[i]), default=0.0)
        scores.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return float(np.mean(scores))


def kmeans_best(X: np.ndarray, k: int, n_init: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """k-means mit mehreren Starts; behalten wird die Lösung mit der höchsten Summe der Zentrums-Ähnlichkeiten."""
    best, best_score = None, -np.inf
    for seed in range(n_init):
        labels, C = kmeans(X, k, seed=seed)
        score = float(np.sum(X * C[labels]))
        if score > best_score:
            best, best_score = (labels, C), score
    return best


def choose_k(X: np.ndarray, k_min: int | None = None, k_max: int = 12) -> int:
    """Bestes k nach Silhouette; bei sehr wenigen Dokumenten entsprechend kleiner.
    Ab 24 Einheiten mindestens 3 Cluster: Embeddings mit vielen Dimensionen bevorzugen sonst oft k=2,
    was für die Exploration nichts zeigt."""
    if k_min is None:
        k_min = 3 if len(X) >= 24 else 2
    k_max = max(k_min, min(k_max, len(X) // 3))
    if len(X) < 6:
        return 1
    best_k, best_s = k_min, -1.0
    for k in range(k_min, k_max + 1):
        labels, _ = kmeans_best(X, k)
        if np.bincount(labels, minlength=k).min() < 2:   # Einzelgänger-Cluster sind keine Themen
            continue
        s = silhouette(X, labels)
        log.info("k=%d silhouette=%.3f", k, s)
        if s > best_s + 0.005:   # kleine Verbesserungen rechtfertigen kein größeres k
            best_k, best_s = k, s
    return best_k


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zäöüß][a-zäöüß\-]{2,}", text.lower()) if w not in STOP and not w.isdigit()]


def top_terms(texts: list[str], labels: np.ndarray, n: int = 3) -> dict[int, list[str]]:
    """Begriffe, die in vielen Dokumenten eines Clusters vorkommen und insgesamt deutlich seltener sind."""
    sets = [set(_tokens(t)) for t in texts]
    N = len(sets)
    df_all = Counter(w for s_ in sets for w in s_)
    out = {}
    for c in set(labels.tolist()):
        idx = [i for i, l in enumerate(labels.tolist()) if l == c]
        df_c = Counter(w for i in idx for w in sets[i])
        size = len(idx)
        scored = []
        for w, v in df_c.items():
            p_c, p_all = v / size, df_all[w] / N
            if p_c >= (0.3 if size >= 4 else 0.5) and p_c > p_all:
                scored.append((p_c * math.log(p_c / p_all), w))
        out[c] = [w for _, w in sorted(scored, reverse=True)[:n]]
    return out


def project_2d(X: np.ndarray) -> list[tuple[float, float]]:
    """2D-Position je Punkt für die Cluster-Karte: die ersten beiden Hauptkomponenten, auf -1..1 skaliert."""
    if len(X) < 3:
        return [(round(-0.5 + i, 3), 0.0) for i in range(len(X))]
    Xc = X - X.mean(axis=0, keepdims=True)
    _, _, vt = np.linalg.svd(Xc, full_matrices=False)
    P = Xc @ vt[:2].T
    if P.shape[1] < 2:
        P = np.hstack([P, np.zeros((len(P), 1))])
    m = np.abs(P).max(axis=0)
    m[m == 0] = 1
    P = P / m
    return [(round(float(x), 3), round(float(y), 3)) for x, y in P]


# --------------------------------------------------------------- Cluster-Namen (REQ-04)
ACRONYMS = {"ai": "AI", "llm": "LLM", "llms": "LLMs", "pls": "PLS", "sem": "SEM", "pls-sem": "PLS-SEM", "hr": "HR", "it": "IT",
            "esg": "ESG", "csr": "CSR", "ui": "UI", "ux": "UX", "ki": "KI", "ict": "ICT", "erp": "ERP", "cnn": "CNN", "nlp": "NLP",
            "rag": "RAG", "sme": "SME", "smes": "SMEs", "iot": "IoT", "gpu": "GPU", "covid": "COVID", "covid-19": "COVID-19"}
GENERIC_TITLE = re.compile(r"^(cluster|topic|group|theme)\s*\d*$|^(misc(ellaneous)?|various|other|general|mixed)\b.*|^(research|studies|papers|documents|notes|topics)$", re.I)


def _tc(phrase: str) -> str:
    """Title Case für Cluster-Namen, Akronyme groß ("ai adoption" -> "AI Adoption")."""
    return " ".join(ACRONYMS.get(w, w[:1].upper() + w[1:]) for w in phrase.split())


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


# Für Namen nur Funktionswörter und Floskeln ausschließen (die allgemeine STOP-Liste nimmt auch Fachwörter wie "app" heraus)
NAME_STOP = set("""a an the and or of in on for to with by from at as is are was were be been being this that these those their its
our we us how why what which who whom whether into over under between among about than then also not no via using use used
based toward towards through within without across per can may do does more most new two three one
der die das und oder im in von zu mit für auf ein eine einer eines den dem des wie welche
study studies paper papers article research purpose approach findings results examine examines examined investigate investigates
explore explores exploring aim aims author authors present presents propose proposes show shows using""".split())


def _phrases(text: str) -> set[str]:
    """Wortpaare aus Titel und Purpose eines Werks (ohne Stoppwörter) – Kandidaten für Cluster-Namen."""
    rows = [l.split(": ", 1)[1] for l in text.splitlines() if l.startswith(("Title: ", "Purpose: ")) and ": " in l] or [text]
    out = set()
    for r in rows:
        toks = re.findall(r"[a-zäöüß0-9][a-zäöüß0-9\-]{1,}", r.lower())
        ok = [t not in NAME_STOP and not t.isdigit() for t in toks]
        for i in range(len(toks) - 1):
            if ok[i] and ok[i + 1]:
                out.add(f"{toks[i]} {toks[i + 1]}")
                if i + 2 < len(toks) and ok[i + 2]:
                    out.add(f"{toks[i]} {toks[i + 1]} {toks[i + 2]}")
    return out


def _caser(texts: list[str]):
    """Schreibweise eines Worts wie im Text, wenn sie besonders ist (fsQCA, PLS-SEM, COVID-19), sonst Title Case."""
    forms = Counter(m for t in texts for m in re.findall(r"[A-Za-zÄÖÜäöüß0-9][\wÄÖÜäöüß\-]*", t))
    def case(w: str) -> str:
        if w in ACRONYMS:
            return ACRONYMS[w]
        cand = [f for f, _ in forms.most_common() if f.lower() == w]
        special = [f for f in cand if f != f.lower() and f != f[:1].upper() + f[1:].lower()]
        return special[0] if special and sum(forms[f] for f in special) * 2 >= sum(forms[f] for f in cand) else w[:1].upper() + w[1:]
    return lambda phrase: " ".join(case(w) for w in phrase.split())


def heuristic_titles(texts: list[str], labels: list[int], terms: dict[int, list[str]], names: set[str] | None = None) -> dict[int, str]:
    """Beschreibender Kurzname je Cluster ohne LLM: das prägnanteste Wortpaar (in mehreren Werken des Clusters,
    insgesamt seltener) plus der stärkste weitere Begriff, z. B. "Job Satisfaction and Lean"; sonst die Top-Begriffe.
    Personennamen kommen nicht vor."""
    names = names or set()
    sets = [_phrases(t) for t in texts]
    N = len(sets)
    df_all = Counter(p for s_ in sets for p in s_)
    out = {}
    for c in sorted(set(labels)):
        idx = [i for i, l in enumerate(labels) if l == c]
        size = len(idx)
        df_c = Counter(p for i in idx for p in sets[i])
        tc = _caser([texts[i] for i in idx])
        best, best_s, best_v = None, 0.0, 0
        for ph, v in df_c.items():
            if any(w in names for w in ph.split()) or ph.count(" ") > 1:
                continue
            p_c, p_all = v / size, df_all[ph] / N
            if (v >= 2 or size == 1) and p_c >= (0.2 if size >= 5 else 0.34) and p_c >= p_all:
                sc = p_c * math.log(1 + p_c / p_all) + 0.01 * v
                if sc > best_s:
                    best, best_s, best_v = ph, sc, v
        if best:   # eine Dreiwortgruppe, die das Wortpaar enthält und genauso oft vorkommt, ist der genauere Name
            tri = [(v, ph) for ph, v in df_c.items() if ph.count(" ") == 2 and best in ph and v >= best_v
                   and not any(w in names for w in ph.split())]
            if tri:
                best = max(tri)[1]
        tw = [w for w in terms.get(c, []) if w not in names and not w.startswith("pokemon")]
        if best:
            extra = [w for w in tw if w not in best.split() and not any(b[:4] == w[:4] for b in best.split())]   # keine Dopplung (team/teams)
            out[c] = tc(best) + (f" and {tc(extra[0])}" if extra else "")
        elif tw:
            out[c] = _join([tc(w) for w in tw[:2]])
        else:   # keine prägnanten Begriffe: häufigstes Wortpaar bzw. Wort des Clusters
            common = [p for p, _ in df_c.most_common() if p.count(" ") == 1 and not any(w in names for w in p.split())]
            words = Counter(w for i in idx for w in _tokens(texts[i]) if w not in names)
            out[c] = tc(common[0]) if common else (tc(words.most_common(1)[0][0]) if words else "Unlabeled Documents")
    return out


def unique_titles(titles: dict[int, str], terms: dict[int, list[str]]) -> dict[int, str]:
    """Gleiche Namen innerhalb eines Laufs unterscheiden: erst durch einen eigenen Begriff, sonst durch eine Nummer."""
    out, seen = {}, Counter(t.lower() for t in titles.values())
    used: set[str] = set()
    for c in sorted(titles):
        t = titles[c]
        if seen[t.lower()] > 1:
            extra = next((w for w in terms.get(c, []) if w.lower() not in t.lower() and f"{t} ({_tc(w)})".lower() not in used), None)
            t2 = f"{t} ({_tc(extra)})" if extra else t
            n = 2
            while t2.lower() in used:
                t2, n = f"{t} {n}", n + 1
            t = t2
        used.add(t.lower())
        out[c] = t
    return out


def cluster_vectors(X: np.ndarray, texts: list[str], k: int | None = None,
                    names: set[str] | None = None, salt: str = "") -> dict:
    """Clustert normalisierte Vektoren; Rückgabe: labels, scores, label-Texte, k."""
    X = _normalize(X)
    k = k or choose_k(X)
    if k <= 1:
        labels = np.zeros(len(X), dtype=int)
        C = _normalize(X.mean(axis=0, keepdims=True))
    else:
        labels, C = kmeans_best(X, k)
    # Cluster nach Größe sortieren, damit Cluster 1 der größte ist
    order = [c for c, _ in Counter(labels.tolist()).most_common()]
    remap = {c: i + 1 for i, c in enumerate(order)}
    terms = top_terms(texts, labels)
    names = names if names is not None else name_tokens(texts)
    terms = {c: pseudonymize_terms(t, names, salt) for c, t in terms.items()}
    titles = unique_titles(heuristic_titles(texts, labels.tolist(), terms, names), terms)
    scores = np.sum(X * C[labels], axis=1)
    sims = X @ C.T
    if len(order) > 1:
        sims_other = sims.copy()
        sims_other[np.arange(len(X)), labels] = -np.inf
        alt = np.argmax(sims_other, axis=1)
        alt_ids = [remap.get(int(a)) for a in alt]
        alt_scores = [round(float(sims[i, a]), 3) for i, a in enumerate(alt)]
    else:
        alt_ids, alt_scores = [None] * len(X), [None] * len(X)
    return {
        "k": len(order),
        "labels": [remap[c] for c in labels.tolist()],
        "scores": [round(float(s), 3) for s in scores],
        "coords": project_2d(X),
        "alt_ids": alt_ids,
        "alt_scores": alt_scores,
        "names": {remap[c]: " · ".join(terms.get(c, [])) or titles[c].lower() for c in order},
        "titles": {remap[c]: titles[c] for c in order},
    }


# --------------------------------------------------------------- Qdrant-Anbindung
SUMMARY_FIELDS = [
    ("purpose", "Purpose"),
    ("design_methodology_approach", "Design/methodology/approach"),
    ("findings", "Findings"),
    ("research_limitations_implications", "Research limitations/implications"),
    ("originality_value", "Originality/value"),
]
UNIT_TYPES = ("research_paper", "research_notes", "legal_guideline", "standard")   # + aktuelle Gesetzesfassungen (REQ-38)


def summary_text(title: str | None, summary: dict | None) -> str:
    """Text, der für den Cluster-Vektor eingebettet wird – nur Titel und Structured Summary, keine Autoren."""
    s = summary or {}
    parts = [f"{lab}: {s[k].strip()}" for k, lab in SUMMARY_FIELDS if (s.get(k) or "").strip()]
    if not parts:
        return ""
    return "\n".join(([f"Title: {title.strip()}"] if title else []) + parts)


def summary_key(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def select_units(docs: list[dict], projects: list[dict], project_files: bool = False) -> list[dict]:
    """Clustering-Einheiten: Paper und Notes mit Summary (ohne Duplikate) sowie Projekte mit Projekt-Summary.
    project_files=True: statt der Projekte als Ganzes jede aktuelle Projektdatei mit eigener Summary
    (neueste Version, nicht archiviert) – Clustering nach dem Inhalt der Dokumente im Projekt."""
    units = []
    for d in docs:
        if d.get("duplicate_of"):
            continue
        lg = d.get("legal") or {}
        if lg and not lg.get("current"):
            continue                              # REQ-38: nur die aktuelle Fassung einer Norm ist eine Einheit
        if d.get("doc_type") == "research_project":
            if not project_files or d.get("is_latest") is False or d.get("archived"):
                continue
        elif d.get("doc_type") == "legal_project" and lg.get("current"):
            pass                                  # das Gesetz selbst (aktuelle Fassung) liegt als Punkt in der Karte
        elif d.get("doc_type") not in UNIT_TYPES:
            continue
        t = summary_text(d.get("title"), d.get("summary"))
        if t:
            units.append({"kind": "doc", "id": d["doc_id"], "text": t, "authors": d.get("authors") or []})
    for p in ([] if project_files else projects):
        t = summary_text(p.get("title") or p.get("name"), p.get("summary"))
        if t:
            units.append({"kind": "project", "id": p["project_id"], "name": p["name"], "text": t,
                          "authors": p.get("authors") or []})
    return units


async def _fill_vectors(units: list[dict], api_key: str | None) -> list[str]:
    """Liest gespeicherte Summary-Vektoren; fehlende/veraltete werden eingebettet und in Qdrant abgelegt."""
    from . import store

    stored = {**store.summary_vectors("documents"), **store.summary_vectors("projects")}
    todo = []
    for u in units:
        u["key"] = summary_key(u["text"])
        vec, key = stored.get(u["id"], (None, None))
        if vec is not None and key == u["key"]:
            u["vec"] = vec
        else:
            todo.append(u)
    skipped: list[str] = []
    if todo:
        key = None
        try:
            from .llm import resolve_key
            key = resolve_key(api_key)
        except Exception:
            pass
        if key:
            from .llm import embed_documents
            vecs = await embed_documents([u["text"] for u in todo], key)
            for u, v in zip(todo, vecs):
                u["vec"] = v
                store.set_summary_vector("projects" if u["kind"] == "project" else "documents", u["id"], v, u["key"])
        else:
            skipped = [u["id"] for u in todo]
    return skipped


# Beitrag einer Projektdatei ohne eigene Summary zum Inhalt (Clustering mit project_files=True)
CONTRIBUTION = {
    "data": "data", "analysis_script": "analysis", "analysis_output": "analysis", "model_file": "analysis",
    "tables": "results", "figures": "results", "image": "results", "presentation": "presentation",
    "questionnaire": "instrument", "cover_letter": "submission", "title_page": "submission",
    "submission_pdf": "submission", "reviewer_response": "submission", "highlights": "submission",
    "reference": "literature", "manuscript": "text", "abstract": "text", "appendix": "text", "notes": "text",
}


def contribution_of(d: dict) -> str:
    """Beitragswert einer Hilfsdatei: data, analysis, results, instrument, submission, literature, version, text, other."""
    kind = CONTRIBUTION.get(d.get("role") or "", "other")
    if kind == "text" and d.get("is_latest") is False:
        return "version"
    return kind


def _folder(rel_path: str | None) -> list[str]:
    return [p for p in (rel_path or "").replace("\\", "/").split("/")[:-1] if p]


def associate_project_files(docs: list[dict], doc_meta: dict[str, dict]) -> None:
    """Projektdateien ohne eigenen Cluster übernehmen den Cluster des inhaltlich tragenden Dokuments im selben Projekt:
    das mit dem längsten gemeinsamen Ordnerpfad, bei Gleichstand das im häufigsten Cluster des Projekts.
    Dazu kommt der Beitragswert (cluster_contribution) und das Bezugsdokument (cluster_anchor)."""
    by_id = {d["doc_id"]: d for d in docs}
    anchors: dict[str, list[dict]] = {}
    for doc_id, m in doc_meta.items():
        d = by_id.get(doc_id)
        if d and d.get("doc_type") == "research_project" and m.get("cluster_basis") == "summary":
            anchors.setdefault(d.get("project_name"), []).append(d)
    for d in docs:
        if d["doc_id"] in doc_meta or d.get("doc_type") != "research_project":
            continue
        cands = anchors.get(d.get("project_name"))
        if not cands:
            continue
        freq = Counter(doc_meta[a["doc_id"]]["cluster_id"] for a in cands)
        folder = _folder(d.get("rel_path"))

        def closeness(a: dict, folder=folder, freq=freq) -> tuple:
            af, n = _folder(a.get("rel_path")), 0
            while n < min(len(af), len(folder)) and af[n] == folder[n]:
                n += 1
            m = doc_meta[a["doc_id"]]
            return n, freq[m["cluster_id"]], m.get("cluster_score") or 0

        best = max(cands, key=closeness)
        am = doc_meta[best["doc_id"]]
        doc_meta[d["doc_id"]] = {k: am[k] for k in ("cluster_id", "cluster_label", "cluster_k", "cluster_run")} | {
            "cluster_score": None, "cluster_basis": "contribution", "cluster_x": None, "cluster_y": None,
            "cluster_alt_id": None, "cluster_alt_score": None,
            "cluster_contribution": contribution_of(d), "cluster_anchor": best["doc_id"]}


def assign(units: list[dict], res: dict, docs: list[dict], run: str, project_files: bool = False) -> tuple[dict, dict]:
    """Cluster-Metadaten für Dokumente und Projekte; Projektdateien und Duplikate erben."""
    base = {"cluster_k": res["k"], "cluster_run": run}
    doc_meta, proj_meta = {}, {}
    for u, c, sc, xy, ai, asc in zip(units, res["labels"], res["scores"], res["coords"], res["alt_ids"], res["alt_scores"]):
        m = {"cluster_id": c, "cluster_label": res["names"][c], "cluster_score": sc, **base, "cluster_basis": "summary",
             "cluster_x": xy[0], "cluster_y": xy[1], "cluster_alt_id": ai, "cluster_alt_score": asc}
        if u["kind"] == "project":
            proj_meta[u["name"]] = {**m, "project_id": u["id"]}
        else:
            doc_meta[u["id"]] = m
    for d in docs:
        if d["doc_id"] in doc_meta:
            continue
        if d.get("doc_type") == "research_project" and d.get("project_name") in proj_meta:
            pm = proj_meta[d["project_name"]]
            doc_meta[d["doc_id"]] = {k: pm[k] for k in ("cluster_id", "cluster_label", "cluster_k", "cluster_run")} | \
                                    {"cluster_score": None, "cluster_basis": "project", "cluster_x": None, "cluster_y": None,
                                     "cluster_alt_id": None, "cluster_alt_score": None}
    for d in docs:   # Duplikate von Paper/Notes erben den Cluster ihres Originals
        orig = d.get("duplicate_of")
        if d["doc_id"] not in doc_meta and orig in doc_meta:
            doc_meta[d["doc_id"]] = {**doc_meta[orig], "cluster_score": None, "cluster_x": None, "cluster_y": None}
    if project_files:
        for m in doc_meta.values():
            m.setdefault("cluster_contribution", "content" if m.get("cluster_basis") == "summary" else None)
            m.setdefault("cluster_anchor", None)
        associate_project_files(docs, doc_meta)
    return doc_meta, proj_meta


def _in_dbs(row: dict, dbs: set[str]) -> bool:
    return bool(dbs & set(row.get("databases") or []))


def shift_clusters(res: dict, offset: int, prefix: str = "") -> dict:
    """Verschiebt Cluster-IDs um offset (keine Kollision mit Clustern anderer Datenbanken) und setzt ein Label-Präfix."""
    if not offset and not prefix:
        return res
    return {**res,
            "labels": [c + offset for c in res["labels"]],
            "alt_ids": [None if a is None else a + offset for a in res["alt_ids"]],
            "names": {c + offset: f"{prefix}{n}" for c, n in res["names"].items()},
            "titles": {c + offset: t for c, t in (res.get("titles") or {}).items()}}


async def recompute(k: int | None = None, api_key: str | None = None, databases: list[str] | None = None,
                    project_files: bool = False) -> dict:
    """Clustert Paper, Notes und Projekte anhand ihrer Summary-Vektoren und schreibt die Metadaten zurück.
    databases: nur Dokumente/Projekte dieser Datenbanken clustern; die Cluster aller anderen bleiben unverändert,
    die neuen Cluster-IDs schließen an die höchste bestehende ID an."""
    from . import store
    from .config import db_name, get_settings

    docs, projects = store.scroll_documents(), store.list_projects()
    dbs = set(databases or [])
    offset, prefix = 0, ""
    if dbs:
        others = [r for r in [*docs, *projects] if not _in_dbs(r, dbs) and r.get("cluster_id") is not None]
        offset = max((int(r["cluster_id"]) for r in others), default=0)
        prefix = "/".join(sorted(db_name(d) for d in dbs)) + " · "
        docs = [d for d in docs if _in_dbs(d, dbs)]
        projects = [p for p in projects if _in_dbs(p, dbs)]
    units = select_units(docs, projects, project_files=project_files)
    skipped = await _fill_vectors(units, api_key)
    units = [u for u in units if u.get("vec") is not None]
    if len(units) < 2:
        return {"k": 0, "documents": 0, "basis": "summary", "skipped": skipped,
                "note": "Too few documents with a structured summary and summary vector for clustering."}
    X = np.array([u["vec"] for u in units], dtype=np.float32)
    names = name_tokens([u["text"] for u in units], [a for u in units for a in u["authors"]])
    res = cluster_vectors(X, [u["text"] for u in units], k, names=names, salt=get_settings().pseudonym_salt)
    res = shift_clusters(res, offset, prefix)
    run = datetime.now(timezone.utc).isoformat(timespec="seconds")
    descs = name_clusters(await describe_clusters(units, res, names, api_key), res)
    doc_meta, proj_meta = assign(units, res, docs, run, project_files=project_files)
    for m in [*doc_meta.values(), *proj_meta.values()]:
        d = descs.get(m["cluster_id"]) or {}
        m["cluster_title"], m["cluster_description"] = d.get("title"), d.get("description")
        m["cluster_title_source"] = d.get("title_source")
        m["cluster_insights"], m["cluster_analyses"], m["cluster_theories"] = d.get("insights"), d.get("analyses"), d.get("theories")
    scope = ({d["doc_id"] for d in docs}, {p["name"] for p in projects}) if dbs else None
    store.set_cluster_payload(doc_meta, run, projects=proj_meta, scope=scope)
    if get_settings().graph_enabled:
        try:
            from . import graph
            graph.sync_clusters(doc_meta, proj_meta, descs, scope_docs=scope[0] if scope else None)
        except Exception as e:  # Graph ist optional
            log.warning("Cluster-Sync in Neo4j fehlgeschlagen: %s", e)
    log.info("Clustering: %d Einheiten, %d Dokumente in %d Clustern", len(units), len(doc_meta), res["k"])
    return {"k": res["k"], "basis": "summary", "databases": sorted(dbs) or "all", "unit": "project_files" if project_files else "projects", "units": len(units), "documents": len(doc_meta),
            "projects": len(proj_meta), "skipped": skipped, "run": run,
            "clusters": [{"cluster_id": c, "label": n, "size": res["labels"].count(c), **(descs.get(c) or {})}
                         for c, n in res["names"].items()]}


def name_clusters(descs: dict[int, dict], res: dict) -> dict[int, dict]:
    """REQ-04: jeder Cluster bekommt einen beschreibenden Namen. LLM-Titel haben Vorrang; fehlt einer oder ist er
    generisch ("Cluster 3", "Miscellaneous", "Research"), gilt der aus den Begriffen gebildete Name. Danach eindeutig."""
    heur = res.get("titles") or {}
    out = {c: dict(d) for c, d in descs.items()}
    for c in res["names"]:
        d = out.setdefault(c, {})
        t = (d.get("title") or "").strip().strip(".")
        if t and not GENERIC_TITLE.match(t):
            d["title"], d["title_source"] = t, d.get("title_source") or "llm"
        else:
            d["title"], d["title_source"] = heur.get(c) or _tc(res["names"][c].split(" · ")[-1]), "terms"
    terms = {c: [w for w in n.split(" · ") if w] for c, n in res["names"].items()}
    for c, t in unique_titles({c: d["title"] for c, d in out.items() if c in res["names"]}, terms).items():
        out[c]["title"] = t
    return out


def cluster_prompt(cid: int, label: str, members: list[dict]) -> str:
    lines = [f"Cluster C{cid} – distinctive terms: {label}", "Members (title – purpose | approach | findings):"]
    def field(rows: list[str], prefix: str) -> str:
        return next((r[len(prefix):] for r in rows if r.startswith(prefix)), "")

    for u in members[:15]:
        t = u["text"].splitlines()
        lines.append(f"- {field(t, 'Title: ')} – {field(t, 'Purpose: ')[:220]} | "
                     f"{field(t, 'Design/methodology/approach: ')[:220]} | {field(t, 'Findings: ')[:220]}")
    return "\n".join(lines)


def pseudonymize_text(text: str, names: set[str], salt: str = "") -> str:
    """Ersetzt erkannte Personennamen in Freitext durch ihre Pokémon-Pseudonyme."""
    if not text or not names:
        return text
    return re.sub(r"[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß-]+", lambda m: pseudonym(m.group(0), salt) if m.group(0).lower() in names else m.group(0), text)


async def describe_clusters(units: list[dict], res: dict, names: set[str], api_key: str | None) -> dict[int, dict]:
    """Kurztitel + 1–2 Sätze Beschreibung je Cluster per LLM (nur mit API-Key). Namen werden pseudonymisiert."""
    try:
        from .llm import chat_model, resolve_key
        key = resolve_key(api_key)
    except Exception:
        return {}
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent

    from .config import get_settings

    class ClusterDescription(BaseModel):
        title: str = Field(description="Descriptive name of the cluster in 2-6 words, US English, Title Case: name what these documents "
                                       "are specifically about (e.g. 'Lean and Job Satisfaction', 'Energy App Adoption'). "
                                       "No generic words alone ('Research', 'Studies', 'Topics', 'Cluster'), no person names")
        description: str = Field(description="1-2 sentences in US English: what the documents in this cluster share. No person names.")
        insights: list[str] = Field(default_factory=list, description="2-3 key insights or findings the documents reached, one short sentence each, US English, no person names")
        analyses: list[str] = Field(default_factory=list, description="Up to 5 research methods or analyses used to reach them, e.g. 'PLS-SEM', 'Interviews', 'Vignette experiment'")
        theories: list[str] = Field(default_factory=list, description="Up to 5 theories, models or frameworks the documents build on, e.g. 'Signaling theory'. Empty if none is named.")

    s = get_settings()
    agent = Agent(chat_model(s.chat_model, key), output_type=ClusterDescription,
                  instructions="You describe topic clusters of research documents for researchers. Be concrete and neutral. Never mention people.")
    out: dict[int, dict] = {}
    for c, label in res["names"].items():
        members = [u for u, l in zip(units, res["labels"]) if l == c]
        try:
            r = await agent.run(cluster_prompt(c, label, members))
            add_run(r)
            ps = lambda t: pseudonymize_text(t, names, s.pseudonym_salt)  # noqa: E731
            out[c] = {"title": ps(r.output.title), "description": ps(r.output.description), "description_source": "llm",
                      "insights": [ps(x) for x in r.output.insights[:3]], "analyses": r.output.analyses[:5], "theories": r.output.theories[:5]}
        except Exception as e:  # Beschreibung ist optional
            log.warning("Cluster-Beschreibung C%s fehlgeschlagen: %s", c, e)
    return out


def cluster_links(units: list[dict]) -> list[dict]:
    """Kanten für den Cluster-Graphen: wie viele Einheiten eines Clusters dem anderen am zweitnächsten sind."""
    acc: dict[tuple[int, int], list[float]] = {}
    for u in units:
        a, b = u.get("cluster_id"), u.get("cluster_alt_id")
        if a is None or b is None or a == b:
            continue
        acc.setdefault((min(a, b), max(a, b)), []).append(u.get("cluster_alt_score") or 0.0)
    return [{"source": a, "target": b, "bridges": len(v), "similarity": round(sum(v) / len(v), 3)}
            for (a, b), v in sorted(acc.items())]
