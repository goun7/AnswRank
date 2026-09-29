"""Validation of persisted evidence used in DM drafts (not provider verification)."""
import json
from datetime import datetime
from typing import Mapping, Optional

from pydantic import ValidationError

from answrank.models import CitationRunResult

# DM sınırında uydurulmamış olması gereken ham alanlar: eksik değer
# Pydantic tarafından varsayılanla doldurulmadan reddedilir.
_REQUIRED_RAW_FIELDS = (
    "run_id", "domain", "brand_name", "sector", "city", "timestamp",
    "total_runs", "brand_citations_found", "citation_rate_percentage",
    "is_fully_live", "live_items_count", "live_response_rate_percentage",
    "grounding_status", "items",
)
_REQUIRED_ITEM_FIELDS = (
    "question_id", "model", "was_simulated", "brand_mentioned", "domain_cited",
)


def visibility_from_row(row: Mapping, domain: str) -> Optional[dict]:
    """Accept a consistent, fully live run; never infer missing provenance."""
    try:
        raw = json.loads(row["raw_json"])
        if not isinstance(raw, dict) or raw.get("is_fully_live") is not True:
            return None
        # Eksik/null ham alan: varsayılan değil, geçersiz kanıt.
        if any(raw.get(f) is None for f in _REQUIRED_RAW_FIELDS):
            return None
        items = raw.get("items")
        if not isinstance(items, list) or not items:
            return None
        if any(not isinstance(it, dict)
               or any(it.get(f) is None for f in _REQUIRED_ITEM_FIELDS)
               for it in items):
            return None
        run = CitationRunResult.model_validate(raw)
        total = len(run.items)
        if total == 0 or any(item.get("was_simulated") is not False
                             for item in items):
            return None
        hits = sum(item.brand_mentioned or item.domain_cited for item in run.items)
        rate = round(100 * hits / total, 1)
        if not (run.domain == domain == row["domain"]
                and run.run_id == row["run_id"]
                and run.total_runs == row["total_runs"] == total
                and run.live_items_count == total
                and run.live_response_rate_percentage == 100.0
                and run.brand_citations_found == row["citations_found"] == hits
                and run.citation_rate_percentage == row["citation_rate"] == rate
                and run.timestamp == datetime.fromisoformat(row["created_at"])):
            return None
        modes = {item.model: run.grounding_status.get(item.model) for item in run.items}
        if any(mode not in ("search-grounded", "model-recall") for mode in modes.values()):
            return None
    except (ValueError, TypeError, KeyError, AttributeError, ValidationError):
        return None
    return {"hits": hits, "total": total, "rate": rate,
            "engine": "LLM soru bankası yanıt testi", "is_fully_live": True,
            "domain": domain, "run_id": run.run_id,
            "created_at": row["created_at"], "grounding_status": modes}
