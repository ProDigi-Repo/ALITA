"""Which version of a law a paper means, and the current number of the provision it cites."""
from __future__ import annotations

import re


# ----------------------------------------------------------------- 3./4. determining and mapping the version
def _norm(t: str) -> str:
    return re.sub(r"[^\w]+", " ", (t or "").lower()).strip()


def _shingles(t: str, n: int = 3) -> set[str]:
    w = _norm(t).split()
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def _jac(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


class Resolver:
    """Versions and concordance of a law (cached for one run)."""

    def __init__(self, model: dict):
        from ..legal import valid_at
        self.m = model
        self.nid = model["norm"]["norm_id"]
        self.versions = sorted(model["versions"], key=lambda v: v["seq"])
        self.current = model.get("current_seq") or (self.versions[-1]["seq"] if self.versions else None)
        self._valid = {v["seq"]: valid_at(model, seq=v["seq"]) for v in self.versions}
        self._text: dict[tuple[int, str], str] = {}
        self._sh: dict[tuple[int, str], set] = {}
        self._map: dict[tuple[int, str], str | None] = {}

    def exists(self, seq: int, cid: str) -> bool:
        """True when component cid exists in version seq."""
        return cid in self._valid.get(seq, {})

    def resolve(self, seq: int, variants: list[str]) -> str | None:
        """First of the id variants that exists in version seq."""
        return next((c for c in variants if self.exists(seq, c)), None)

    def text(self, seq: int, cid: str) -> str:
        """Wording with all sub-parts (via the prefixes of the ids – independent of the aggregation)."""
        k = (seq, cid)
        if k not in self._text:
            v = self._valid.get(seq, {})
            comps = self.m["components"]
            parts = sorted((c for c in v if c == cid or c.startswith(cid + "/")), key=lambda c: comps.get(c, {}).get("order", 0))
            self._text[k] = "\n".join(v[c]["text"] for c in parts if v[c].get("text"))
        return self._text[k]

    def sh(self, seq: int, cid: str) -> set:
        """Shingles of a component's text in version seq (cached)."""
        k = (seq, cid)
        if k not in self._sh:
            self._sh[k] = _shingles(self.text(seq, cid))
        return self._sh[k]

    def title(self, seq: int, cid: str) -> str:
        """Title of a component in version seq, else its general title."""
        c = self._valid.get(seq, {}).get(cid) or {}
        return c.get("title") or self.m["components"].get(cid, {}).get("title") or ""

    def stage(self, seq: int) -> dict:
        """Version entry with sequence number seq."""
        return next((v for v in self.versions if v["seq"] == seq), {})

    def candidates(self, when: str | None) -> list[int]:
        """Sequence numbers of the versions published up to `when` (all when none match)."""
        seqs = [v["seq"] for v in self.versions if not when or not v.get("date") or v["date"] <= when]
        return seqs or [v["seq"] for v in self.versions]

    def choose(self, refs: list[dict], quotes: list[tuple[dict, str]], when: str | None) -> int | None:
        """Version the paper refers to: most of the cited components exist and cited wordings occur in them;
        on a tie the latest up to the date of the paper."""
        best, score = None, -1.0
        for seq in self.candidates(when):
            s = 0.0
            for r in refs:
                c = self.resolve(seq, r["variants"])
                s += (1.0 if c == r["variants"][0] else 0.5) if c else 0.0
            for r, q in quotes:
                c = self.resolve(seq, r["variants"])
                root = r["variants"][-1]
                if c and q in _norm(self.text(seq, root)):
                    s += 3.0
            if s >= score:
                best, score = seq, s
        return best

    def to_current(self, seq: int, cid: str) -> str | None:
        """Component of an earlier version -> component of the version in force (same number if the text fits,
        otherwise the most similar component of the same kind; sub-parts within the article found)."""
        if seq == self.current:
            return cid if self.exists(seq, cid) else None
        k = (seq, cid)
        if k in self._map:
            return self._map[k]
        root = cid.split("/")[0]
        if "/" in cid:
            r2 = self.to_current(seq, root)
            res = r2
            if r2:
                depth = cid.count("/")
                same = r2 + cid[len(root):]
                kids = [c for c in self._valid[self.current] if c.startswith(r2 + "/") and c.count("/") == depth]
                old = self.sh(seq, cid)
                scored = sorted(((_jac(old, self.sh(self.current, c)), c) for c in kids), reverse=True)
                if same in self._valid[self.current] and _jac(old, self.sh(self.current, same)) >= max(0.2, (scored[0][0] if scored else 0) - 0.05):
                    res = same
                elif scored and scored[0][0] >= 0.2:
                    res = scored[0][1]
            self._map[k] = res
            return res
        kind = root.split("_")[0]
        old = self.sh(seq, root)
        same = self._jac_cur(old, root) if self.exists(self.current, root) else 0.0
        if same >= 0.5 or not old:
            res = root if self.exists(self.current, root) else None
        else:
            pool = [c for c in self._valid[self.current] if "/" not in c and c.split("_")[0] == kind]
            sc, best = max(((self._jac_cur(old, c), c) for c in pool), default=(0.0, None))
            ot, bt = _norm(self.title(seq, root)), _norm(self.title(self.current, best)) if best else ""
            if best and (sc >= 0.12 or (ot and ot in bt and sc >= 0.06)) and sc > same + 0.03:
                res = best
            else:
                res = root if same >= 0.15 else None
        self._map[k] = res
        return res

    def _jac_cur(self, old: set, cid: str) -> float:
        return _jac(old, self.sh(self.current, cid))
