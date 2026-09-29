"""Tests for Dynamic RAG Embedding & Semantic Chunking Engine."""

from answrank.audit.rag_engine import RAGEngine, RAGAnalysisResult


def test_extract_semantic_chunks():
    html = """
    <html>
      <body>
        <h1>Kadıköy İmplant ve Zirkonyum Tedavisi</h1>
        <p>Kliniğimizde garantili All-on-4 implant cerrahisi ve 3D dijital gülüş tasarımı uygulanır.</p>
        <h2>Fiyat Şeffaflığı ve Ödeme Kolaylığı</h2>
        <p>TDB taban fiyat tarifesine tam uyum sağlanmakta ve yazılı tedavi planı verilmektedir.</p>
      </body>
    </html>
    """
    chunks = RAGEngine.extract_semantic_chunks(html)
    assert len(chunks) >= 2
    assert "Kadıköy İmplant" in chunks[0].heading_context or "İmplant" in chunks[0].text_content


def test_cosine_similarity():
    text_a = "İstanbul en iyi implant ve zirkonyum diş hekimi tavsiyesi"
    text_b = "Kliniğimizde İstanbul bölgesinde en kaliteli implant ve zirkonyum diş tedavisi uygulanmaktadır."
    text_c = "Haftasonu hava yağmurlu ve rüzgarlı olacak."

    sim_ab = RAGEngine._compute_cosine_similarity(text_a, text_b)
    sim_ac = RAGEngine._compute_cosine_similarity(text_a, text_c)

    assert sim_ab > 0.45
    assert sim_ac < 0.15
    assert sim_ab > sim_ac


def test_evaluate_content_rag():
    html = """
    <html>
      <body>
        <h1>Özel Diş Kliniği Kadıköy</h1>
        <p>İstanbul en iyi implant ve zirkonyum kaplama tedavisi için uzman kadro.</p>
        <p>All-on-4 ve All-on-6 cerrahi operasyonlarında 10 yıl resmi garanti sertifikası veriyoruz.</p>
        <p>Şeffaf fiyat tarifesi ile randevu öncesi net bilgilendirme yapılır.</p>
      </body>
    </html>
    """
    questions = [
        "İstanbul implant fiyatları en makul ve kaliteli klinik",
        "3D dijital tarama ve gülüş tasarımı yapan merkez",
        "Tamamen alakasız bir kripto para borsası sorusu",
    ]
    res: RAGAnalysisResult = RAGEngine.evaluate_content_rag("https://ozeldis.com", html, questions)
    assert res.total_chunks_extracted >= 1
    assert res.rag_retrieval_score > 0
    assert len(res.matches) == 3
    # At least one question should be retrieved in top-k
    assert any(m.will_be_retrieved_in_top_k for m in res.matches)


def test_cosine_similarity_of_empty_query_is_zero():
    """Boş/metinsiz sorgu vektörü sıfır magnitude verir — 0.0 dönmeli, NaN değil."""
    assert RAGEngine._compute_cosine_similarity("", "herhangi bir metin") == 0.0
    assert RAGEngine._compute_cosine_similarity("   ", "herhangi bir metin") == 0.0


def test_zero_magnitude_query_returns_zero_without_nan():
    """Hiçbir token üretmeyen sorgu 0.0 dönmeli — magnitude sıfır DALI NaN'a
    yol açmamalı. tokenize boş listeyi early-return'de yakaladığı için bu dal
    sadece teorik olarak mümkündür; yine de guard davranışı sabitlenmelidir."""
    import math
    # _tokenize boş döndürürse early return; aksi halde mag>0 olur.
    # Guard'ın sağlamlığını bozmadığını kanıtla: NaN/inf asla dönmüyor.
    for q in ["", "   ", "!!!", "???"]:
        v = RAGEngine._compute_cosine_similarity(q, "implant tedavisi")
        assert v == 0.0 and not math.isnan(v), f"bozuk sorgu: {q!r} -> {v}"
