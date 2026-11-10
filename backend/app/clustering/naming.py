"""Names in clusters: person names are found and replaced by stable Pokémon pseudonyms (no author names in cluster
labels), and clusters get descriptive titles – from the language model, or from their most distinctive word pairs."""
from __future__ import annotations

import math
import re
from collections import Counter

from .numeric import STOP, _tokens

# --------------------------------------------------------------- pseudonymisation
# real names of people must not appear in cluster labels. Recognised names are
# replaced by Pokémon names, stably (same name -> same pseudonym).
POKEMON = """Pikachu Bulbasaur Charmander Squirtle Jigglypuff Meowth Psyduck Snorlax Eevee Togepi Mew Mewtwo
Vulpix Growlithe Abra Machop Geodude Ponyta Slowpoke Magnemite Gastly Onix Cubone Lapras Ditto Vaporeon Jolteon
Flareon Porygon Dratini Chikorita Cyndaquil Totodile Pichu Marill Sudowoodo Wooper Umbreon Espeon Snubbull
Teddiursa Phanpy Treecko Torchic Mudkip Ralts Mawile Aron Plusle Minun Roselia Wailmer Swablu Bagon Beldum
Turtwig Chimchar Piplup Shinx Pachirisu Buneary Riolu Snivy Tepig Oshawott Zorua Litwick Froakie Fennekin
Rowlet Litten Popplio Mimikyu Grookey Scorbunny Sobble Wooloo Yamper Sprigatito Fuecoco Quaxly""".split()


NAME_CONTEXT = re.compile(
    r"\b([A-ZÄÖÜ][a-zäöüß]{2,}(?:-[A-ZÄÖÜ][a-zäöüß]+)?)(?=,\s*[A-Z]\.|\s+et al|\s*\((?:19|20)\d{2}|\s+and\s+[A-Z][a-z]+\s*\((?:19|20)\d{2})")


# enumerations of names without a year, as they occur in summaries: "Simon, Kahneman and Tversky",
# "Parasuraman and Riley's framework". Whether they really are names is decided by the capitalisation test below.
_CAP = r"[A-ZÄÖÜ][a-zäöüß]{2,}(?:-[A-ZÄÖÜ][a-zäöüß]+)?"


NAME_LIST = re.compile(rf"\b(?:{_CAP},\s+)*{_CAP}\s+(?:and|&|und)\s+{_CAP}\b")


EMAIL_NAME = re.compile(r"\b([A-Za-z]{2,})[._]([A-Za-z][A-Za-z\-]+)\s*@")


def name_tokens(texts: list[str], known_names: list[str] | None = None) -> set[str]:
    """Person names (lower case): from author metadata and from citation patterns in the text
    ('Müller, A.', 'Meyer et al', 'Schmidt (2019)', 'Schmidt and Lee (2020)', 'Simon, Kahneman and Tversky')."""
    out: set[str] = set()
    for n in known_names or []:
        out.update(p.lower() for p in re.split(r"[\s,.-]+", n) if len(p) > 2)
    cited = Counter(m for t in texts for m in NAME_CONTEXT.findall(t))
    listed = Counter(w for t in texts for span in NAME_LIST.findall(t) for w in re.findall(_CAP, span))
    lower = Counter(w for t in texts for w in re.findall(r"\b[a-zäöüß]{3,}\b", t))
    # only words that (almost) always occur capitalised in the corpus – otherwise they are ordinary words
    out.update(w.lower() for w, c in cited.items() if lower[w.lower()] <= 0.1 * c)
    # enumerations are less certain (also titles like "Trust and Control"): there no lower-case occurrence at all
    # and not in a title (line "Title: …")
    titles = " ".join(l for t in texts for l in t.splitlines() if l.startswith("Title:"))
    out.update(w.lower() for w in listed if lower[w.lower()] == 0 and w not in titles)
    for t in texts:
        # e-mail addresses of the form firstname.lastname@… reveal names reliably
        for first, last in EMAIL_NAME.findall(t):
            out.add(first.lower())
            out.update(p.lower() for p in last.split("-") if len(p) > 2)
    return out - STOP


def pseudonym(name: str, salt: str = "") -> str:
    """Stable pseudonym (a Pokémon name) for a person name, so author names never reach cluster labels."""
    import hashlib

    h = int(hashlib.sha256((salt + name.lower()).encode()).hexdigest(), 16)
    return POKEMON[h % len(POKEMON)]


def pseudonymize_terms(terms: list[str], names: set[str], salt: str = "") -> list[str]:
    """Replace every term that is a known person name by its pseudonym."""
    return [pseudonym(t, salt) if t.lower() in names else t for t in terms]


# --------------------------------------------------------------- cluster names (REQ-04)
ACRONYMS = {"ai": "AI", "llm": "LLM", "llms": "LLMs", "pls": "PLS", "sem": "SEM", "pls-sem": "PLS-SEM", "hr": "HR", "it": "IT",
            "esg": "ESG", "csr": "CSR", "ui": "UI", "ux": "UX", "ki": "KI", "ict": "ICT", "erp": "ERP", "cnn": "CNN", "nlp": "NLP",
            "rag": "RAG", "sme": "SME", "smes": "SMEs", "iot": "IoT", "gpu": "GPU", "covid": "COVID", "covid-19": "COVID-19"}


GENERIC_TITLE = re.compile(r"^(cluster|topic|group|theme)\s*\d*$|^(misc(ellaneous)?|various|other|general|mixed)\b.*|^(research|studies|papers|documents|notes|topics)$", re.I)


def _tc(phrase: str) -> str:
    """Title case for cluster names, acronyms upper case ("ai adoption" -> "AI Adoption")."""
    return " ".join(ACRONYMS.get(w, w[:1].upper() + w[1:]) for w in phrase.split())


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


# for names exclude only function words and stock phrases (the general STOP list also drops technical words like "app")
NAME_STOP = set("""a an the and or of in on for to with by from at as is are was were be been being this that these those their its
our we us how why what which who whom whether into over under between among about than then also not no via using use used
based toward towards through within without across per can may do does more most new two three one
der die das und oder im in von zu mit für auf ein eine einer eines den dem des wie welche
study studies paper papers article research purpose approach findings results examine examines examined investigate investigates
explore explores exploring aim aims author authors present presents propose proposes show shows using""".split())


def _phrases(text: str) -> set[str]:
    """Word pairs from the title and purpose of a work (without stop words) – candidates for cluster names."""
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
    """Spelling of a word as in the text if it is special (fsQCA, PLS-SEM, COVID-19), otherwise title case."""
    forms = Counter(m for t in texts for m in re.findall(r"[A-Za-zÄÖÜäöüß0-9][\wÄÖÜäöüß\-]*", t))
    def case(w: str) -> str:
        if w in ACRONYMS:
            return ACRONYMS[w]
        cand = [f for f, _ in forms.most_common() if f.lower() == w]
        special = [f for f in cand if f != f.lower() and f != f[:1].upper() + f[1:].lower()]
        return special[0] if special and sum(forms[f] for f in special) * 2 >= sum(forms[f] for f in cand) else w[:1].upper() + w[1:]
    return lambda phrase: " ".join(case(w) for w in phrase.split())


def heuristic_titles(texts: list[str], labels: list[int], terms: dict[int, list[str]], names: set[str] | None = None) -> dict[int, str]:
    """Descriptive short name per cluster without an LLM: the most distinctive word pair (in several works of the cluster,
    rarer overall) plus the strongest further term, e.g. "Job Satisfaction and Lean"; otherwise the top terms.
    Person names do not occur."""
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
        if best:   # a three-word group that contains the word pair and occurs just as often is the more precise name
            tri = [(v, ph) for ph, v in df_c.items() if ph.count(" ") == 2 and best in ph and v >= best_v
                   and not any(w in names for w in ph.split())]
            if tri:
                best = max(tri)[1]
        tw = [w for w in terms.get(c, []) if w not in names and not w.startswith("pokemon")]
        if best:
            extra = [w for w in tw if w not in best.split() and not any(b[:4] == w[:4] for b in best.split())]   # no doubling (team/teams)
            out[c] = tc(best) + (f" and {tc(extra[0])}" if extra else "")
        elif tw:
            out[c] = _join([tc(w) for w in tw[:2]])
        else:   # no distinctive terms: the most frequent word pair or word of the cluster
            common = [p for p, _ in df_c.most_common() if p.count(" ") == 1 and not any(w in names for w in p.split())]
            words = Counter(w for i in idx for w in _tokens(texts[i]) if w not in names)
            out[c] = tc(common[0]) if common else (tc(words.most_common(1)[0][0]) if words else "Unlabeled Documents")
    return out


def unique_titles(titles: dict[int, str], terms: dict[int, list[str]]) -> dict[int, str]:
    """Tell equal names within a run apart: first by a term of their own, otherwise by a number."""
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


def name_clusters(descs: dict[int, dict], res: dict) -> dict[int, dict]:
    """REQ-04: every cluster gets a descriptive name. LLM titles take precedence; if one is missing or
    generic ("Cluster 3", "Miscellaneous", "Research"), the name formed from the terms applies. Then made unique."""
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


def pseudonymize_text(text: str, names: set[str], salt: str = "") -> str:
    """Replaces recognised person names in free text by their Pokémon pseudonyms."""
    if not text or not names:
        return text
    return re.sub(r"[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß-]+", lambda m: pseudonym(m.group(0), salt) if m.group(0).lower() in names else m.group(0), text)
