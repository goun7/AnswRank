"""Single-owner text normalization for domains/brands (16 Eyl derin-tarama C-hijyen).

Five near-duplicate normalizers used to drift independently (entity.py,
evaluator.py, entity_grounding.py, engine.py, crm/outreach.py). They are now
thin calls here; semantics are documented per function and locked by tests.
Turkish-accifold normalization stays local to entity matching (its own scope).
"""

from urllib.parse import urlparse


def netloc(url_or_domain: str) -> str:
    """Canonical host for citation/domain matching.

    Strips a scheme if present, leading `www.`, trailing slashes; lowercases.
    (Previously evaluator.py's inline `domain.replace(...)` chain.)
    """
    s = (url_or_domain or "").strip().lower()
    if "://" in s:
        s = urlparse(s).netloc or s.split("://", 1)[1]
    if s.startswith("www."):
        s = s[4:]
    return s.rstrip("/")


def core_label(url_or_domain: str) -> str:
    """Second-level brand label used for entity-title comparison: first dot
    segment of the netloc, lowercased ('www.acibadem.com.tr' -> 'acibadem')."""
    return netloc(url_or_domain).split(".")[0]


def brand_from_domain(url_or_domain: str) -> str:
    """Display brand derived from a domain: core label, dashes/underscores
    spaced, title-cased ('acibadem-klinik' -> 'Acibadem Klinik')."""
    return core_label(url_or_domain).replace("-", " ").replace("_", " ").title()
