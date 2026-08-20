"""Small, dependency-free text utilities shared across agents/services."""
from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def extract_search_terms(text: str, max_terms: int = 5, min_len: int = 3) -> list[str]:
    """Extract clean alphanumeric tokens suitable for a tsquery AND-list.

    Uses ``re.findall`` on alphanumeric runs rather than stripping
    disallowed characters from whitespace-split words. Character-stripping
    (e.g. ``re.sub(r"[^\\w\\s\\-]", "", text)``) can still leave a token with
    a leading/trailing/standalone hyphen (e.g. "1g-" from a real batch
    fragment) which ``to_tsquery`` also rejects as a syntax error.
    ``findall(r"[A-Za-z0-9]+")`` instead pulls contiguous alphanumeric runs
    directly out of the text, so a hyphenated/slashed compound like
    "F1/QA/004" or "1g-2mg" always yields safe sub-tokens with no
    possibility of a dangling operator character reaching tsquery.

    Dedup is case-insensitive; first-seen casing is preserved.
    """
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for tok in _TOKEN_RE.findall(text):
        if len(tok) < min_len:
            continue
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tok)
        if max_terms > 0 and len(out) >= max_terms:
            break
    return out


def sanitize_for_tsquery(text: str, max_terms: int = 5, min_len: int = 3) -> str:
    """Build a safe ``term & term & ...`` string for ``to_tsquery('english', ...)``.

    Every token is pure alphanumeric, so this can never itself trigger a
    tsquery syntax error regardless of what free text is fed in.
    """
    terms = extract_search_terms(text, max_terms=max_terms, min_len=min_len)
    return " & ".join(terms)
