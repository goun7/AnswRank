import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from answrank.integrations.deployer import CMSDeployer, DeployTarget


@pytest.mark.anyio
async def test_deploy_local_export():
    with tempfile.TemporaryDirectory() as tmpdir:
        fixes = {
            "robots.txt": "User-agent: *\nAllow: /",
            "llms.txt": "# LLMs entry point",
            "schema.jsonld": '{"@context": "https://schema.org"}',
        }
        res = CMSDeployer.export_local_bundle(output_dir=tmpdir, fixes=fixes)
        assert res.success is True
        assert res.target == DeployTarget.LOCAL_EXPORT
        assert len(res.deployed_files) == 3
        assert os.path.exists(os.path.join(tmpdir, "robots.txt"))
        assert os.path.exists(os.path.join(tmpdir, "llms.txt"))
        assert os.path.exists(os.path.join(tmpdir, "schema.jsonld"))


@pytest.mark.anyio
async def test_deploy_webhook_hmac():
    fixes = {"robots.txt": "Allow: /"}
    payload = {"brand": "Test Brand", "fixes": fixes}

    # Mock httpx.AsyncClient.post
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        res = await CMSDeployer.deploy_webhook(
            webhook_url="https://hooks.zapier.com/hooks/catch/123/abc",
            secret_key="secret-hmac-key",
            payload_data=payload,
        )
        assert res.success is True
        assert res.target == DeployTarget.WEBHOOK_HMAC
        assert res.status_code == 200


@pytest.mark.anyio
async def test_deploy_webhook_hmac_signature_is_correct():
    """The X-AnswRank-Signature header must be a valid sha256 HMAC of the exact body."""
    import hmac as hmac_mod
    import hashlib
    import json as json_mod

    fixes = {"robots.txt": "Allow: /"}
    payload = {"brand": "Test Brand", "fixes": fixes}
    captured = {}

    class FakeResp:
        status_code = 200

    async def fake_post(self, url, content=None, headers=None, **kwargs):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        return FakeResp()

    with patch("httpx.AsyncClient.post", new=fake_post):
        res = await CMSDeployer.deploy_webhook(
            webhook_url="https://hooks.example.com/abc",
            secret_key="secret-hmac-key",
            payload_data=payload,
        )
        assert res.success is True

    # Verify HMAC
    raw_body = captured["content"]
    expected_sig = hmac_mod.new(b"secret-hmac-key", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
    assert captured["headers"]["X-AnswRank-Signature"] == f"sha256={expected_sig}"
    # Body is valid sorted-key JSON
    assert json_mod.loads(raw_body)["brand"] == "Test Brand"


@pytest.mark.anyio
async def test_deploy_wordpress_auth_failure():
    """Auth failure must return success=False with the HTTP status."""
    class FakeResp:
        status_code = 401
        text = "unauthorized"

    async def fake_get(self, url, **kwargs):
        return FakeResp()

    with patch("httpx.AsyncClient.get", new=fake_get):
        res = await CMSDeployer.deploy_wordpress(
            wp_site_url="https://example-wp.com",
            username="admin",
            app_password="badpass",
            fixes={"robots.txt": "Allow: /"},
        )
        assert res.success is False
        assert res.status_code == 401
        assert "authentication failed" in res.message.lower()


@pytest.mark.anyio
async def test_deploy_wordpress_real_page_upsert():
    """Authenticated flow: text assets must be upserted as pages with matching slugs."""
    existing_pages = {}  # slug -> page state

    class FakeResp:
        def __init__(self, status_code, data=None):
            self.status_code = status_code
            self._data = data if data is not None else {}

        def json(self):
            return self._data

    async def fake_get(self, url, params=None, auth=None, **kwargs):
        if "/pages" in url and params and params.get("slug"):
            slug = params["slug"]
            if slug in existing_pages:
                return FakeResp(200, [{"id": existing_pages[slug]["id"]}])
            return FakeResp(200, [])
        if "/users/me" in url:
            return FakeResp(200, {"id": 1, "name": "admin"})
        return FakeResp(200, {})

    page_counter = {"n": 100}

    async def fake_post(self, url, json=None, auth=None, **kwargs):
        if "/settings" in url:
            return FakeResp(200, {})  # header injection succeeds
        # page create/update
        if "/pages" in url:
            slug = json.get("slug")
            if slug and slug in existing_pages and f"/{existing_pages[slug]['id']}" in url:
                existing_pages[slug]["content"] = json["content"]
                return FakeResp(200, {"id": existing_pages[slug]["id"]})
            page_counter["n"] += 1
            existing_pages[slug] = {"id": page_counter["n"], "content": json["content"], "status": json.get("status")}
            return FakeResp(201, {"id": page_counter["n"]})
        return FakeResp(200, {})

    with patch("httpx.AsyncClient.get", new=fake_get), \
         patch("httpx.AsyncClient.post", new=fake_post):
        res = await CMSDeployer.deploy_wordpress(
            wp_site_url="https://example-wp.com",
            username="admin",
            app_password="goodpass",
            fixes={
                "robots.txt": "User-agent: *\nAllow: /",
                "llms.txt": "# Index",
                "schema.jsonld": '{"@type": "Dentist"}',
            },
        )

    assert res.success is True
    # robots.txt and llms.txt deployed as pages with matching slugs
    assert "robots.txt" in res.deployed_files
    assert "llms.txt" in res.deployed_files
    # schema injected into header (settings endpoint mocked to accept)
    assert any("schema.jsonld" in f for f in res.deployed_files)
    # The pages were actually created in the fake WP state
    assert "robots.txt" in existing_pages
    assert "llms.txt" in existing_pages


@pytest.mark.anyio
async def test_deploy_github_pushes_files():
    """GitHub deployer creates/updates files via the contents API."""

    class FakeResp:
        def __init__(self, status_code, data=None):
            self.status_code = status_code
            self._data = data or {}

        def json(self):
            return self._data

    calls = {"get": [], "put": []}

    async def fake_get(self, url, headers=None, **kwargs):
        calls["get"].append(url)
        # File does not exist yet -> 404 (no sha needed)
        return FakeResp(404, {"message": "Not Found"})

    async def fake_put(self, url, json=None, headers=None, **kwargs):
        calls["put"].append({"url": url, "json": json})
        return FakeResp(201, {"content": {"sha": "abc123"}})

    with patch("httpx.AsyncClient.get", new=fake_get), \
         patch("httpx.AsyncClient.put", new=fake_put):
        res = await CMSDeployer.deploy_github(
            repo_owner="testowner",
            repo_name="testrepo",
            branch="main",
            github_token="fake_token",
            fixes={"robots.txt": "Allow: /", "llms.txt": "# Index"},
        )

    assert res.success is True
    assert res.target == DeployTarget.GITHUB_COMMIT
    assert sorted(res.deployed_files) == ["llms.txt", "robots.txt"]
    assert len(calls["put"]) == 2
    # Content must be base64 encoded
    import base64
    for call in calls["put"]:
        assert "content" in call["json"]
        base64.b64decode(call["json"]["content"])  # must be valid base64
        assert call["json"]["branch"] == "main"


@pytest.mark.anyio
async def test_deploy_wordpress_updates_existing_page():
    """When a page with the slug already exists, the deployer must UPDATE it
    (POST to /pages/{id}) rather than create a duplicate."""
    existing_pages = {"robots.txt": {"id": 777, "content": "old"}}
    calls = {"post": []}

    class FakeResp:
        def __init__(self, status_code, data=None):
            self.status_code = status_code
            self._data = data or {}

        def json(self):
            return self._data

    async def fake_get(self, url, params=None, auth=None, **kwargs):
        if "/users/me" in url:
            return FakeResp(200, {"id": 1})
        if "/pages" in url and params and params.get("slug"):
            slug = params["slug"]
            if slug in existing_pages:
                return FakeResp(200, [{"id": existing_pages[slug]["id"]}])
            return FakeResp(200, [])
        return FakeResp(200, {})

    async def fake_post(self, url, json=None, auth=None, **kwargs):
        calls["post"].append({"url": url, "json": json})
        if "/settings" in url:
            return FakeResp(200, {})
        if "/pages/777" in url:
            return FakeResp(200, {"id": 777})  # update succeeded
        return FakeResp(201, {"id": 999})

    with patch("httpx.AsyncClient.get", new=fake_get), \
         patch("httpx.AsyncClient.post", new=fake_post):
        res = await CMSDeployer.deploy_wordpress(
            wp_site_url="https://wp-update-test.com",
            username="admin",
            app_password="pw",
            fixes={"robots.txt": "User-agent: *\nAllow: /"},
        )

    assert res.success is True
    # The update path was exercised: POST went to /pages/777 (existing id)
    assert any("/pages/777" in c["url"] for c in calls["post"])


@pytest.mark.anyio
async def test_deploy_wordpress_schema_private_page_fallback():
    """When the head_footer settings endpoint fails, the schema must be saved
    as a PRIVATE page for the webmaster to paste manually."""
    created = {"pages": []}

    class FakeResp:
        def __init__(self, status_code, data=None):
            self.status_code = status_code
            self._data = data or {}

        def json(self):
            return self._data

    async def fake_get(self, url, params=None, auth=None, **kwargs):
        if "/users/me" in url:
            return FakeResp(200, {"id": 1})
        if "/pages" in url:
            return FakeResp(200, [])
        return FakeResp(200, {})

    async def fake_post(self, url, json=None, auth=None, **kwargs):
        if "/settings" in url:
            return FakeResp(500, {"message": "no header plugin"})  # injection fails
        if "/pages" in url:
            created["pages"].append(json)
            return FakeResp(201, {"id": len(created["pages"]) + 100})
        return FakeResp(200, {})

    with patch("httpx.AsyncClient.get", new=fake_get), \
         patch("httpx.AsyncClient.post", new=fake_post):
        res = await CMSDeployer.deploy_wordpress(
            wp_site_url="https://wp-fallback-test.com",
            username="admin",
            app_password="pw",
            fixes={"robots.txt": "Allow: /", "schema.jsonld": '{"@type": "Dentist"}'},
        )

    assert res.success is True
    assert any("private page" in f for f in res.deployed_files)
    # The private schema page was actually created with status=private
    private_pages = [p for p in created["pages"] if p.get("slug") == "answrank-schema"]
    assert private_pages and private_pages[0]["status"] == "private"
    # The message tells the webmaster manual action is needed
    assert "manual" in res.message.lower() or "paste" in res.message.lower()


@pytest.mark.anyio
async def test_deploy_github_updates_existing_file_with_sha():
    """When the remote file already exists (GET 200 with sha), the update
    PUT must carry the sha parameter."""
    calls = {"get": [], "put": []}

    class FakeResp:
        def __init__(self, status_code, data=None):
            self.status_code = status_code
            self._data = data or {}

        def json(self):
            return self._data

    async def fake_get(self, url, headers=None, **kwargs):
        calls["get"].append(url)
        # File EXISTS on the remote
        return FakeResp(200, {"sha": "existing_sha_abc", "content": "old"})

    async def fake_put(self, url, json=None, headers=None, **kwargs):
        calls["put"].append({"url": url, "json": json})
        return FakeResp(200, {"content": {"sha": "new_sha"}})

    with patch("httpx.AsyncClient.get", new=fake_get), \
         patch("httpx.AsyncClient.put", new=fake_put):
        res = await CMSDeployer.deploy_github(
            repo_owner="o", repo_name="r", branch="main",
            github_token="t",
            fixes={"robots.txt": "Allow: /"},
        )

    assert res.success is True
    assert calls["put"][0]["json"]["sha"] == "existing_sha_abc"
