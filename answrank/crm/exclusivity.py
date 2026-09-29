"""Territory and Niche Exclusivity Engine for AnswRank.

Solves the LLM Citation Cannibalization dilemma:
Prevents multiple clients in the same geographic territory and niche from
cannibalizing each other's LLM answer slots, protecting Article 7 performance guarantees.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class TerritoryLock(BaseModel):
    """Represents an active exclusivity lock for a given territory and niche."""
    lock_id: str
    country: str
    city: str
    niche: str
    client_domain: str
    brand_name: str
    tier: str = "EXCLUSIVE"
    agency_domain: Optional[str] = None  # E2: kilidi taşıyan ajans (beyaz etiket kanalı)  # "EXCLUSIVE" or "SUB_NICHE_PARTITIONED"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    contract_id: Optional[str] = None


class ConflictCheckResult(BaseModel):
    """Result of territory conflict analysis."""
    has_conflict: bool
    existing_lock: Optional[TerritoryLock] = None
    action_recommended: str  # "PROCEED", "REJECT_CONFLICT", "PARTITION_SUB_NICHE"
    suggested_sub_niches: List[str] = Field(default_factory=list)
    conflict_reason: Optional[str] = None


class ExclusivityManager:
    """Manages geographic and sectoral exclusivity locks across client swarms."""

    # Default sub-niche taxonomy for partitioning when general niche is locked
    SUB_NICHE_TAXONOMY: Dict[str, List[str]] = {
        "dental": [
            "all_on_4_implants",
            "cosmetic_veneers",
            "invisalign_orthodontics",
            "pediatric_dentistry",
            "emergency_endodontics",
        ],
        "aesthetics": [
            "rhinoplasty_specialist",
            "hair_transplantation",
            "body_contouring_liposuction",
            "facial_rejuvenation_botox",
            "breast_augmentation",
        ],
        "legal": [
            "commercial_litigation",
            "mergers_and_acquisitions",
            "immigration_law",
            "intellectual_property",
            "high_net_worth_divorce",
        ],
        "wealth_management": [
            "family_office_advisory",
            "cross_border_tax_structuring",
            "private_equity_placement",
            "crypto_asset_custody",
        ],
    }

    def __init__(self):
        self._locks: Dict[str, TerritoryLock] = {}

    @staticmethod
    def _make_key(country: str, city: str, niche: str) -> str:
        return f"{country.strip().upper()}:{city.strip().lower()}:{niche.strip().lower()}"

    def check_conflict(
        self,
        country: str,
        city: str,
        niche: str,
        candidate_domain: str,
        agency_domain: Optional[str] = None,
    ) -> ConflictCheckResult:
        """Check if candidate territory/niche is already locked by an active client."""
        clean_key = self._make_key(country, city, niche)
        existing = self._locks.get(clean_key)

        if existing:
            if existing.client_domain.lower() == candidate_domain.lower():
                return ConflictCheckResult(
                    has_conflict=False,
                    existing_lock=existing,
                    action_recommended="PROCEED",
                    conflict_reason="Existing lock belongs to this client.",
                )

            # Conflict found: provide sub-niche partitioning alternatives
            sub_niches = self.get_available_sub_niches(country, city, niche)
            return ConflictCheckResult(
                has_conflict=True,
                existing_lock=existing,
                action_recommended="PARTITION_SUB_NICHE" if sub_niches else "REJECT_CONFLICT",
                suggested_sub_niches=sub_niches,
                conflict_reason=(
                    f"Territory '{city.title()}, {country.upper()}' for niche '{niche}' "
                    f"is exclusively locked by '{existing.brand_name}' ({existing.client_domain}). "
                    f"Protecting Article 7 Citation Guarantee against cannibalization."
                ),
            )

        # E2 (D-16.09-M/1): ajans kanalında kıtlık = MÜŞTERİ BAŞINA SEKTÖR KOTASI.
        # Aynı ajans portföyü bir sektörde yalnız TEK müşteri kilidi taşır; şehir
        # farkı kota ihlalini affetmez (yamyamlık koruması Madde-7'ye bağlıdır).
        if agency_domain:
            ag = agency_domain.strip().lower()
            for lk in self._locks.values():
                if lk.agency_domain and lk.agency_domain.strip().lower() == ag \
                        and lk.niche == niche.lower():
                    return ConflictCheckResult(
                        has_conflict=True,
                        action_recommended="REJECT_AGENCY_QUOTA",
                        conflict_reason=(
                            f"Ajans kota kuralı — '{ag}' portföyünde '{niche}' sektöründe tek "
                            f"müşteri kilidi vardır ({lk.brand_name}/{lk.client_domain}); aynı "
                            f"sektörde ikinci müşteri alınamaz. Farklı sektör portföye açıktır."
                        ),
                    )
        return ConflictCheckResult(
            has_conflict=False,
            action_recommended="PROCEED",
            conflict_reason=None,
        )

    def lock_territory(
        self,
        country: str,
        city: str,
        niche: str,
        client_domain: str,
        brand_name: str,
        tier: str = "EXCLUSIVE",
        contract_id: Optional[str] = None,
        agency_domain: Optional[str] = None,
    ) -> TerritoryLock:
        """Lock territory for a client to guarantee zero cannibalization."""
        key = self._make_key(country, city, niche)
        lock = TerritoryLock(
            lock_id=f"LOCK-{len(self._locks) + 1:04d}",
            country=country.upper(),
            city=city.lower(),
            niche=niche.lower(),
            client_domain=client_domain.lower(),
            brand_name=brand_name,
            tier=tier,
            contract_id=contract_id,
            agency_domain=agency_domain.strip().lower() if agency_domain else None,
        )
        self._locks[key] = lock
        return lock

    def release_lock(self, country: str, city: str, niche: str) -> bool:
        """Release a territory lock upon contract termination."""
        key = self._make_key(country, city, niche)
        if key in self._locks:
            del self._locks[key]
            return True
        return False

    def get_available_sub_niches(self, country: str, city: str, parent_niche: str) -> List[str]:
        """Find non-conflicting sub-niches for the given territory."""
        all_subs = self.SUB_NICHE_TAXONOMY.get(parent_niche.lower(), [])
        available = []
        for sub in all_subs:
            sub_key = self._make_key(country, city, sub)
            if sub_key not in self._locks:
                available.append(sub)
        return available

    def agency_portfolio(self, agency_domain: str) -> set:
        """E2: ajansın kota tüketmiş sektörleri (portföy kıtlığının tek kaynağı)."""
        ag = agency_domain.strip().lower()
        return {lk.niche for lk in self._locks.values()
                if lk.agency_domain and lk.agency_domain.strip().lower() == ag}

    def list_active_locks(self) -> List[TerritoryLock]:
        """Return all active territory locks."""
        return list(self._locks.values())
