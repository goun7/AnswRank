"""Robots.txt Analyzer for the curated AI bot registry (settings.ai_bots_* tiers:
search/citation, training/indexing, and user-driven agent fetchers).
Registry last re-verified 16 Sept 2026 against knownagents.com (39 bots)."""

from typing import Optional, List, Dict
from answrank.config import settings
from answrank.models import RobotsScore

def parse_robots_rules(robots_text: str) -> Dict[str, List[Dict[str, str]]]:
    """Parses robots.txt into User-agent sections with allow/disallow directives.

    Follows robots.txt grouping (RFC 9309): consecutive User-agent lines share
    one group; a User-agent line appearing AFTER a directive starts a NEW
    group. Comments and blank lines no longer merge separate groups (the old
    parser leaked later groups' directives — e.g. a blocked scraper's
    `Disallow: /` — into every earlier group, misclassifying bots that only
    rely on the `*` fallback).
    """
    current_agents: List[str] = []
    group_is_open = False  # True once the current group received a directive
    rules: Dict[str, List[Dict[str, str]]] = {}

    for line in robots_text.splitlines():
        stripped = line.strip()

        # Comments and blank lines carry no directives; they do not merge the
        # groups around them either.
        if not stripped or stripped.startswith("#"):
            continue

        if ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip().lower()
            val = val.strip()

            if key == "user-agent":
                # RFC 9309: a User-agent line after directives opens a new group.
                if group_is_open:
                    current_agents = []
                    group_is_open = False
                agent = val.lower()
                if agent and agent not in current_agents:
                    current_agents.append(agent)
                if agent and agent not in rules:
                    rules[agent] = []
            elif key in ("allow", "disallow"):
                group_is_open = True
                for agent in current_agents:
                    rules[agent].append({"type": key, "path": val})
            elif key == "sitemap":
                group_is_open = True
                if "sitemaps" not in rules:
                    rules["sitemaps"] = []
                rules["sitemaps"].append({"type": "sitemap", "path": val})
        else:
            # A non-directive, non-comment line closes the current group.
            current_agents = []
            group_is_open = False

    return rules

def is_bot_blocked(agent_name: str, rules: Dict[str, List[Dict[str, str]]]) -> bool:
    """Checks if a specific bot or wildcard '*' has a root disallow."""
    agent_lower = agent_name.lower()
    
    # Check specific bot directive first
    if agent_lower in rules:
        for directive in rules[agent_lower]:
            if directive["type"] == "disallow" and directive["path"] in ("/", "*", ""):
                return True
            if directive["type"] == "allow" and directive["path"] in ("/", ""):
                return False

    # Fallback to wildcard '*' directive
    if "*" in rules:
        for directive in rules["*"]:
            if directive["type"] == "disallow" and directive["path"] in ("/", "*"):
                return True

    return False

class RobotsAnalyzer:
    """Evaluates robots.txt for AI Search and Citation bots."""

    def analyze(self, robots_txt: Optional[str]) -> RobotsScore:
        """İlgili kategorinin puanını ve detaylarını üretir."""
        if not robots_txt or not robots_txt.strip():
            return RobotsScore(
                score=0,
                exists=False,
                ai_search_allowed=False,
                ai_training_allowed=False,
                sitemap_declared=False,
                llms_txt_referenced=False,
                details=["robots.txt dosyası bulunamadı veya boş."],
            )

        score = 0
        details = []
        score += 3
        details.append("robots.txt dosyası mevcut (+3 puan).")

        rules = parse_robots_rules(robots_txt)

        # 1. Search bots check (Max 8 pts)
        blocked_search = []
        allowed_search = []
        for bot in settings.ai_bots_search:
            if is_bot_blocked(bot, rules):
                blocked_search.append(bot)
            else:
                allowed_search.append(bot)

        if not blocked_search:
            score += 8
            details.append(f"Tüm kritik AI Arama Botları ({', '.join(settings.ai_bots_search)}) serbest bırakılmış (+8 puan).")
        else:
            pts = max(0, 8 - len(blocked_search) * 2)
            score += pts
            details.append(f"Bazı AI Arama Botları engellenmiş: {', '.join(blocked_search)} (+{pts}/8 puan).")

        # 2. Training bots check (Max 3 pts)
        blocked_training = []
        allowed_training = []
        for bot in settings.ai_bots_training:
            if is_bot_blocked(bot, rules):
                blocked_training.append(bot)
            else:
                allowed_training.append(bot)

        if len(blocked_training) <= 2:
            score += 3
            details.append("AI eğitim ve endeksleme botlarına büyük oranda izin verilmiş (+3 puan).")
        else:
            score += 1
            details.append(f"AI eğitim botlarının çoğu engellenmiş: {', '.join(blocked_training[:3])} (+1/3 puan).")

        # 3. Sitemap presence (Max 2 pts)
        has_sitemap = bool(rules.get("sitemaps")) or "sitemap:" in robots_txt.lower()
        if has_sitemap:
            score += 2
            details.append("Sitemap bildirimi robots.txt içinde mevcut (+2 puan).")
        else:
            details.append("Sitemap robots.txt içinde bildirilmemiş (0/2 puan).")

        # 4. llms.txt reference (Max 2 pts)
        has_llms_ref = "llms.txt" in robots_txt.lower()
        if has_llms_ref:
            score += 2
            details.append("llms.txt keşif bağlantısı robots.txt içinde tanımlanmış (+2 puan).")
        else:
            details.append("robots.txt içinde llms.txt dosyasına referans verilmemiş (0/2 puan).")

        return RobotsScore(
            score=min(18, score),
            exists=True,
            ai_search_allowed=len(blocked_search) == 0,
            ai_training_allowed=len(blocked_training) <= 2,
            sitemap_declared=has_sitemap,
            llms_txt_referenced=has_llms_ref,
            blocked_ai_bots=blocked_search + blocked_training,
            allowed_ai_bots=allowed_search + allowed_training,
            details=details,
        )
