from answrank.audit.crawler import HeadlessRenderer

def test_is_spa_stub_detection():
    # React root stub
    react_html = "<html><head><title>App</title></head><body><div id='root'></div><script src='/bundle.js'></script><script src='/vendor.js'></script></body></html>"
    assert HeadlessRenderer.is_spa_stub(react_html) is True

    # Next.js stub
    next_html = "<html><head><title>App</title></head><body><div id='__next'></div></body></html>"
    assert HeadlessRenderer.is_spa_stub(next_html) is True

    # Rich static HTML (Not a stub)
    rich_html = (
        "<html><head><title>Dental Clinic</title></head><body>"
        "<h1>Leading Dental Implants in London</h1>"
        "<p>We offer specialized All-on-4 dental implant restorations with over 20 years of accredited clinical excellence in Harley Street.</p>"
        "<p>Transparent fee structures, zero hidden costs, and comprehensive patient warranties are guaranteed.</p>"
        "</body></html>"
    )
    assert HeadlessRenderer.is_spa_stub(rich_html) is False

def test_hydrate_ssr_fallback():
    html_with_next_data = """
    <html>
    <body>
        <div id="__next"></div>
        <script id="__NEXT_DATA__" type="application/json">
        {
            "props": {
                "pageProps": {
                    "clinicTitle": "Harley Street Specialized Dental Implants",
                    "description": "Comprehensive restorative dental procedures with 98% success rate."
                }
            }
        }
        </script>
    </body>
    </html>
    """
    hydrated = HeadlessRenderer.hydrate_ssr_fallback(html_with_next_data)
    assert "Harley Street Specialized Dental Implants" in hydrated
    assert "answrank-hydrated-content" in hydrated
