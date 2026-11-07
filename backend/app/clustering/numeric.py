"""k-means with cosine distance, choice of k by silhouette, distinctive terms and the 2D layout of the cluster map.

Only numpy; used by ``app.clustering`` and usable without Qdrant (tests, demo)."""
from __future__ import annotations

import logging
import math
import re
from collections import Counter

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


# --------------------------------------------------------------- Kernalgorithmen
def _normalize(X: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(X, axis=1, keepdims=True)
    n[n == 0] = 1
    return X / n


def kmeans(X: np.ndarray, k: int, seed: int = 7, iters: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Spherical k-means (cosine) with k-means++ start. X is expected to be normalised."""
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
    """Silhouette with cosine distance, on a sample when there are many documents."""
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
    """k-means with several starts; the solution with the highest sum of centre similarities is kept."""
    best, best_score = None, -np.inf
    for seed in range(n_init):
        labels, C = kmeans(X, k, seed=seed)
        score = float(np.sum(X * C[labels]))
        if score > best_score:
            best, best_score = (labels, C), score
    return best


def choose_k(X: np.ndarray, k_min: int | None = None, k_max: int = 12) -> int:
    """Best k by silhouette; smaller accordingly for very few documents.
    From 24 units on at least 3 clusters: embeddings with many dimensions otherwise often prefer k=2,
    which shows nothing for exploration."""
    if k_min is None:
        k_min = 3 if len(X) >= 24 else 2
    k_max = max(k_min, min(k_max, len(X) // 3))
    if len(X) < 6:
        return 1
    best_k, best_s = k_min, -1.0
    for k in range(k_min, k_max + 1):
        labels, _ = kmeans_best(X, k)
        if np.bincount(labels, minlength=k).min() < 2:   # single-member clusters are not topics
            continue
        s = silhouette(X, labels)
        log.info("k=%d silhouette=%.3f", k, s)
        if s > best_s + 0.005:   # small improvements do not justify a larger k
            best_k, best_s = k, s
    return best_k


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zäöüß][a-zäöüß\-]{2,}", text.lower()) if w not in STOP and not w.isdigit()]


def top_terms(texts: list[str], labels: np.ndarray, n: int = 3) -> dict[int, list[str]]:
    """Terms that occur in many documents of a cluster and are clearly rarer overall."""
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
    """2D position per point for the cluster map: the first two principal components, scaled to -1..1."""
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
