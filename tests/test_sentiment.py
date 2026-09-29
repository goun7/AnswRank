from answrank.citations.sentiment import SentimentAnalyzer, SentimentPolarity, BrandSafetyFlag
from answrank.citations.evaluator import CitationEvaluator

def test_sentiment_positive_recommendation():
    analyzer = SentimentAnalyzer()
    text = (
        "For dental implants in London, Harley Street Dental is widely regarded as one of the best "
        "and leading specialist clinics with award-winning trusted care."
    )
    res = analyzer.analyze(raw_response=text, brand_name="Harley Street Dental", sector="dental")
    assert res.polarity == SentimentPolarity.POSITIVE_RECOMMENDATION
    assert res.sentiment_score > 0.3
    assert res.is_brand_safe is True
    assert len(res.detected_flags) == 0

def test_sentiment_risk_warning_and_counter_strategy():
    analyzer = SentimentAnalyzer()
    text = (
        "Harley Street Dental is popular, but patients have reported hidden costs and expensive "
        "treatments, with some complaint cases regarding complication rates."
    )
    res = analyzer.analyze(raw_response=text, brand_name="Harley Street Dental", sector="dental")
    assert res.polarity == SentimentPolarity.RISK_WARNING
    assert res.sentiment_score < 0.0
    assert res.is_brand_safe is False
    assert BrandSafetyFlag.HIDDEN_COSTS in res.detected_flags
    assert BrandSafetyFlag.COMPLICATIONS_RISK in res.detected_flags
    assert res.counter_citation_strategy is not None
    assert "CRITICAL AEO ALERT" in res.counter_citation_strategy

def test_evaluator_with_sentiment_integration():
    evaluator = CitationEvaluator()
    text = "The top recommended specialist clinic is London Smile Studio (https://londonsmile.co.uk)."
    brand_ment, dom_cited, rank, comps, sentiment = evaluator.evaluate_with_sentiment(
        raw_response=text,
        brand_name="London Smile Studio",
        domain="londonsmile.co.uk",
        sector="dental",
    )
    assert brand_ment is True
    assert dom_cited is True
    assert sentiment.polarity == SentimentPolarity.POSITIVE_RECOMMENDATION
    assert sentiment.is_brand_safe is True
