"""Guidance & FAQ pages: topics and questions (REQ-48)."""
from __future__ import annotations

import re

from .patterns import Component, clean_lines

_Q_START = re.compile(r"^(What|Which|Why|Who|Whom|Whose|How|Where|When|Is|Are|Do|Does|Did|Can|Could|Should|Shall|Will|"
                      r"Would|Has|Have|May|Might|Must|In what|In which|To what|Under what)\b")


_FAQ_FOOTER = re.compile(r"^(Source URL:|© European Union)")


_SENT_END = (".", ";", ":", "?", "!", ")", "”", "’")


def parse_faq(text: str) -> list[Component]:
    """REQ-48: guidance & FAQ (e.g. "AI Literacy – Questions & Answers" of the AI Office): topics and questions.
    A question starts with a question word at the start of a line, ends with "?" after at most three lines and follows
    the end of a sentence or a topic heading; questions listed inside answers ("a) … What is AI?") stay answer text.
    Ids counted as on the page: topic tp_2, question q_2.1 ("question 2.1" in the answers)."""
    lines = clean_lines(text)
    cut = next((i for i, ln in enumerate(lines) if _FAQ_FOOTER.match(ln)), len(lines))
    lines = lines[:cut]
    comps: list[Component] = []
    pre = Component("pre", "preamble", "", None, lines[0] if lines else "", "", 1)
    comps.append(pre)
    cur, topic, tn, qn = pre, None, 0, 0

    def ends(i: int) -> bool:
        return i < 0 or lines[i].rstrip().endswith(_SENT_END) or comps[-1].type == "topic" and comps[-1].title == lines[i]

    def question_at(i: int, after_heading: bool = False) -> int | None:
        if not _Q_START.match(lines[i]) or not (after_heading or ends(i - 1)):
            return None
        for j in range(i, min(i + 3, len(lines))):
            if lines[j].rstrip().endswith("?"):
                return j
            if lines[j].rstrip().endswith((".", ";", ":")):
                return None
        return None

    i = 1
    while i < len(lines):
        ln = lines[i]
        j = question_at(i)
        if j is not None:
            if topic is None:
                tn, qn = 1, 0
                topic = Component("tp_1", "topic", "1", None, "General", "", len(comps) + 1)
                comps.append(topic)
            if cur.type == "question" and not cur.text.strip():   # "What … future? Will the AI Office …?" = one question
                cur.title += " " + " ".join(x.strip() for x in lines[i:j + 1])
                i = j + 1
                continue
            qn += 1
            cur = Component(f"q_{tn}.{qn}", "question", f"{tn}.{qn}", topic.cid, " ".join(x.strip() for x in lines[i:j + 1]), "",
                            len(comps) + 1)
            comps.append(cur)
            i = j + 1
            continue
        if (i + 1 < len(lines) and len(ln) <= 90 and ln[:1].isupper() and not ln.rstrip().endswith(_SENT_END + (",",))
                and ends(i - 1) and question_at(i + 1, after_heading=True) is not None):
            tn, qn = tn + 1, 0
            topic = cur = Component(f"tp_{tn}", "topic", str(tn), None, ln.strip(), "", len(comps) + 1)
            comps.append(topic)
            i += 1
            continue
        cur.text = (cur.text + "\n" + ln) if cur.text else ln
        i += 1
    return comps
