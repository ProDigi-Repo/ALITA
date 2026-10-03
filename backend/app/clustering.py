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
  cluster_title / cluster_description  str  Kurztitel und Beschreibung (LLM, Namen pseudonymisiert; ohne Key leer)
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
        "names": {remap[c]: " · ".join(terms.get(c, [])) or f"Cluster {remap[c]}" for c in order},
    }


# --------------------------------------------------------------- Qdrant-Anbindung
SUMMARY_FIELDS = [
    ("purpose", "Purpose"),
    ("design_methodology_approach", "Design/methodology/approach"),
    ("findings", "Findings"),
    ("research_limitations_implications", "Research limitations/implications"),
    ("originality_value", "Originality/value"),
]
UNIT_TYPES = ("research_paper", "research_notes")


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


def select_units(docs: list[dict], projects: list[dict]) -> list[dict]:
    """Clustering-Einheiten: Paper und Notes mit Summary (ohne Duplikate) sowie Projekte mit Projekt-Summary."""
    units = []
    for d in docs:
        if d.get("doc_type") not in UNIT_TYPES or d.get("duplicate_of"):
            continue
        t = summary_text(d.get("title"), d.get("summary"))
        if t:
            units.append({"kind": "doc", "id": d["doc_id"], "text": t, "authors": d.get("authors") or []})
    for p in projects:
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


def assign(units: list[dict], res: dict, docs: list[dict], run: str) -> tuple[dict, dict]:
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
    return doc_meta, proj_meta


async def recompute(k: int | None = None, api_key: str | None = None) -> dict:
    """Clustert Paper, Notes und Projekte anhand ihrer Summary-Vektoren und schreibt die Metadaten zurück."""
    from . import store
    from .config import get_settings

    docs = store.scroll_documents()
    units = select_units(docs, store.list_projects())
    skipped = await _fill_vectors(units, api_key)
    units = [u for u in units if u.get("vec") is not None]
    if len(units) < 2:
        return {"k": 0, "documents": 0, "basis": "summary", "skipped": skipped,
                "note": "Too few documents with a structured summary and summary vector for clustering."}
    X = np.array([u["vec"] for u in units], dtype=np.float32)
    names = name_tokens([u["text"] for u in units], [a for u in units for a in u["authors"]])
    res = cluster_vectors(X, [u["text"] for u in units], k, names=names, salt=get_settings().pseudonym_salt)
    run = datetime.now(timezone.utc).isoformat(timespec="seconds")
    descs = await describe_clusters(units, res, names, api_key)
    doc_meta, proj_meta = assign(units, res, docs, run)
    for m in [*doc_meta.values(), *proj_meta.values()]:
        d = descs.get(m["cluster_id"]) or {}
        m["cluster_title"], m["cluster_description"] = d.get("title"), d.get("description")
    store.set_cluster_payload(doc_meta, run, projects=proj_meta)
    if get_settings().graph_enabled:
        try:
            from . import graph
            graph.sync_clusters(doc_meta, proj_meta, descs)
        except Exception as e:  # Graph ist optional
            log.warning("Cluster-Sync in Neo4j fehlgeschlagen: %s", e)
    log.info("Clustering: %d Einheiten, %d Dokumente in %d Clustern", len(units), len(doc_meta), res["k"])
    return {"k": res["k"], "basis": "summary", "units": len(units), "documents": len(doc_meta),
            "projects": len(proj_meta), "skipped": skipped, "run": run,
            "clusters": [{"cluster_id": c, "label": n, "size": res["labels"].count(c), **(descs.get(c) or {})}
                         for c, n in res["names"].items()]}


def cluster_prompt(cid: int, label: str, members: list[dict]) -> str:
    lines = [f"Cluster C{cid} – distinctive terms: {label}", "Members (title – purpose):"]
    for u in members[:15]:
        t = u["text"].splitlines()
        title = next((l[7:] for l in t if l.startswith("Title: ")), "")
        purpose = next((l[9:] for l in t if l.startswith("Purpose: ")), "")
        lines.append(f"- {title} – {purpose[:300]}")
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
        title: str = Field(description="Topic of the cluster in 2-5 words, US English, no person names")
        description: str = Field(description="1-2 sentences in US English: what the documents in this cluster share. No person names.")

    s = get_settings()
    agent = Agent(chat_model(s.chat_model, key), output_type=ClusterDescription,
                  instructions="You describe topic clusters of research documents for researchers. Be concrete and neutral. Never mention people.")
    out: dict[int, dict] = {}
    for c, label in res["names"].items():
        members = [u for u, l in zip(units, res["labels"]) if l == c]
        try:
            r = await agent.run(cluster_prompt(c, label, members))
            out[c] = {"title": pseudonymize_text(r.output.title, names, s.pseudonym_salt),
                      "description": pseudonymize_text(r.output.description, names, s.pseudonym_salt), "description_source": "llm"}
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
