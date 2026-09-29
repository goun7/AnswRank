"""Regression tests for the robots.txt parser (RFC 9309 grouping).

BUG FOUND via E2E (9h improvement run): the old parser merged User-agent
groups across comments/blank lines, so a blocked scraper's `Disallow: /`
leaked into the `*` group and bots relying on the wildcard fallback
(Bingbot, Applebot-Extended, Amazonbot, YouBot...) were misclassified as
BLOCKED even though `User-agent: * / Allow: /` was present.
"""

from answrank.audit.analyzers.robots import parse_robots_rules, is_bot_blocked


REAL_WORLD_ROBOTS = """# Sample robots.txt with comments between groups
User-agent: *
Allow: /
Disallow: /private/

# Priority AI search bots
User-agent: OAI-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

# Training
User-agent: GPTBot
Allow: /

# Block scraper
User-agent: Bytespider
Disallow: /
"""


def test_parser_groups_do_not_leak_across_comments():
    """A blocked scraper's Disallow:/ must NOT appear in the * group."""
    rules = parse_robots_rules(REAL_WORLD_ROBOTS)
    star_directives = rules["*"]
    disallow_paths = [d["path"] for d in star_directives if d["type"] == "disallow"]
    assert "/" not in disallow_paths, "Bytespider root disallow leaked into * group"


def test_wildcard_fallback_bots_are_not_blocked():
    """Bots with no explicit entry inherit * → Allow /, so must be allowed."""
    rules = parse_robots_rules(REAL_WORLD_ROBOTS)
    for bot in ["Bingbot", "Applebot-Extended", "Amazonbot", "YouBot", "CCBot"]:
        assert is_bot_blocked(bot, rules) is False, f"{bot} wrongly blocked via * leak"


def test_explicitly_blocked_bot_still_blocked():
    rules = parse_robots_rules(REAL_WORLD_ROBOTS)
    assert is_bot_blocked("Bytespider", rules) is True


def test_explicitly_allowed_bot_still_allowed():
    rules = parse_robots_rules(REAL_WORLD_ROBOTS)
    assert is_bot_blocked("OAI-SearchBot", rules) is False
    assert is_bot_blocked("GPTBot", rules) is False


def test_consecutive_user_agent_lines_share_group():
    """RFC 9309: consecutive UA lines before any directive form one group."""
    robots = """User-agent: A
User-agent: B
Disallow: /

User-agent: *
Allow: /
"""
    rules = parse_robots_rules(robots)
    assert rules["a"] == [{"type": "disallow", "path": "/"}]
    assert rules["b"] == [{"type": "disallow", "path": "/"}]
    assert rules["*"] == [{"type": "allow", "path": "/"}]


def test_directive_after_new_user_agent_starts_new_group():
    """UA line appearing after a directive must not append to the old group."""
    robots = """User-agent: A
Disallow: /tmp
User-agent: B
Allow: /
"""
    rules = parse_robots_rules(robots)
    assert rules["a"] == [{"type": "disallow", "path": "/tmp"}]
    assert rules["b"] == [{"type": "allow", "path": "/"}]


def test_empty_robots_returns_no_rules():
    rules = parse_robots_rules("")
    assert rules == {}


def test_sitemap_directive_collected():
    robots = "User-agent: *\nAllow: /\nSitemap: https://x.com/sitemap.xml\n"
    rules = parse_robots_rules(robots)
    assert rules["sitemaps"][0]["path"] == "https://x.com/sitemap.xml"
