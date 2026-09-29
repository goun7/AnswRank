"""Tests for DeltaEngine and Contractual Performance Guarantee."""

import asyncio
from answrank.audit.delta import DeltaEngine
from answrank.audit.engine import AuditEngine
from answrank.audit.crawler import CrawlData

def test_delta_engine_guarantee_met():
    engine = AuditEngine()
    delta_eng = DeltaEngine()

    crawl = CrawlData(url="https://test.com", domain="test.com", html_content="<p>Test</p>", status_code=200, headers={})
    b_audit = engine.audit_crawl_data(crawl)
    b_audit.overall_score = 15

    c_audit = engine.audit_crawl_data(crawl)
    c_audit.overall_score = 35

    delta_log = delta_eng.calculate_delta(b_audit, c_audit, days_elapsed=30)
    assert delta_log.score_delta == 20
    assert delta_log.is_guarantee_met is True  # 20 >= 12
    assert delta_log.percentage_change > 100.0

    # Save to db test
    asyncio.run(delta_eng.record_delta(delta_log))

def test_delta_engine_guarantee_failed():
    engine = AuditEngine()
    delta_eng = DeltaEngine()

    crawl = CrawlData(url="https://test.com", domain="test.com", html_content="<p>Test</p>", status_code=200, headers={})
    b_audit = engine.audit_crawl_data(crawl)
    b_audit.overall_score = 20

    c_audit = engine.audit_crawl_data(crawl)
    c_audit.overall_score = 28  # delta is 8 (< 12)

    delta_log = delta_eng.calculate_delta(b_audit, c_audit, days_elapsed=30)
    assert delta_log.score_delta == 8
    assert delta_log.is_guarantee_met is False  # Trigger 0 TL free month
