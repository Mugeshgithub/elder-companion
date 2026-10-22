import re
from difflib import SequenceMatcher

FILLER = {"mm", "mmm", "mhm", "hmm", "hm", "uh", "um", "ah", "oh", "er", "erm"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def similar(a: str, b: str) -> bool:
    """True when b is a repeat, a partial, or a longer version of the same utterance."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    return na.startswith(nb) or nb.startswith(na) or SequenceMatcher(None, na, nb).ratio() >= 0.8


def is_filler(s: str) -> bool:
    toks = norm(s).split()
    return not toks or all(t in FILLER for t in toks)
