"""api.deploy_assets_api dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: CMSDeployer + FixGenerator stub — gercek ag/dosya YAPILMADI.
"""
import json

import pytest
from fastapi.testclient import TestClient

from answrank.api import app as answ_app
from answrank.integrations import deployer as dep_mod
from answrank.reporting import fix_generator as fix_mod


class _FixGen:
    calls = {"robots": [], "llms": [], "jsonld": []}

    def generate_robots_txt(self, *a, **kw):
        _FixGen.calls["robots"].append((a, kw))
        return "robots-icerik"

    def generate_llms_txt(self, *a, **kw):
        _FixGen.calls["llms"].append((a, kw))
        return "llms-icerik"

    def generate_json_ld(self, *a, **kw):
        _FixGen.calls["jsonld"].append((a, kw))
        return "{json:ld}"


def _res(target="local"):
    tg = {"local": dep_mod.DeployTarget.LOCAL_EXPORT,
          "webhook": dep_mod.DeployTarget.WEBHOOK_HMAC,
          "wordpress": dep_mod.DeployTarget.WORDPRESS_REST}[target]
    return dep_mod.DeploymentResult(
        success=True, target=tg, status_code=200,
        message="ok", deployed_files=["robots.txt"],
        remote_url="http://x")


class _CMS:
    local_kw = None
    webhook_kw = None
    wp_kw = None
    raises = None

    @classmethod
    def export_local_bundle(cls, output_dir, fixes):
        _CMS.local_kw = (output_dir, fixes)
        if _CMS.raises:
            raise _CMS.raises
        return _res("local")

    @classmethod
    async def deploy_webhook(cls, *a, **kw):
        _CMS.webhook_kw = (a, kw)
        if _CMS.raises:
            raise _CMS.raises
        return _res("webhook")

    @classmethod
    async def deploy_wordpress(cls, *a, **kw):
        _CMS.wp_kw = (a, kw)
        if _CMS.raises:
            raise _CMS.raises
        return _res("wordpress")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(fix_mod, "FixGenerator", _FixGen)
    monkeypatch.setattr(dep_mod, "CMSDeployer", _CMS)
    _FixGen.calls = {"robots": [], "llms": [], "jsonld": []}
    _CMS.local_kw = None
    _CMS.webhook_kw = None
    _CMS.wp_kw = None
    _CMS.raises = None
    return TestClient(answ_app.app)


def _body(**kw):
    b = {"brand_name": "Acme", "domain": "acme.example"}
    b.update(kw)
    return json.dumps(b)


def _post(client, **kw):
    return client.post("/api/deploy", content=_body(**kw),
                       headers={"Content-Type": "application/json"})


# -- temel ---------------------------------------------------------------------------------

def test_status_200(client):
    assert _post(client).status_code == 200


def test_returns_json(client):
    assert isinstance(_post(client).json(), dict)


def test_result_keys(client):
    assert set(_post(client).json()) >= {
        "success", "target", "status_code", "message"}


def test_success_true(client):
    assert _post(client).json()["success"] is True


def test_target_local(client):
    assert _post(client).json()["target"] == "LOCAL_EXPORT"


# -- fix generation ---------------------------------------------------------------------------------

def test_fix_generator_called_robots(client):
    _post(client)
    assert len(_FixGen.calls["robots"]) == 1


def test_fix_generator_called_llms(client):
    _post(client)
    assert len(_FixGen.calls["llms"]) == 1


def test_fix_generator_called_jsonld(client):
    _post(client)
    assert len(_FixGen.calls["jsonld"]) == 1


def test_three_fixes_generated(client):
    _post(client)
    assert _CMS.local_kw is not None
    assert len(_CMS.local_kw[1]) == 3


def test_fix_keys(client):
    _post(client)
    assert set(_CMS.local_kw[1]) == {
        "robots.txt", "llms.txt", "schema.jsonld"}


def test_fix_content_from_generator(client):
    _post(client)
    fixes = _CMS.local_kw[1]
    assert fixes["robots.txt"] == "robots-icerik"
    assert fixes["llms.txt"] == "llms-icerik"


def test_generator_receives_brand(client):
    """robots_txt sadece domain alir."""
    _post(client)
    a = _FixGen.calls["robots"][0][0]
    assert a[0] == "acme.example"
    assert len(a) == 1


def test_generator_llms_args(client):
    _post(client)
    a = _FixGen.calls["llms"][0][0]
    assert a[0] == "Acme"
    assert a[1] == "acme.example"


# -- local target ---------------------------------------------------------------------------------

def test_local_uses_output_dir(client):
    _post(client, output_dir="./xyz")
    assert _CMS.local_kw[0] == "./xyz"


def test_local_default_output_dir(client):
    _post(client)
    assert _CMS.local_kw[0] == "./dist_aeo"


def test_local_sync_call(client):
    _post(client)
    assert _CMS.webhook_kw is None
    assert _CMS.wp_kw is None


# -- webhook target ---------------------------------------------------------------------------------

def test_webhook_400_without_url(client):
    r = _post(client, target="webhook")
    assert r.status_code == 400


def test_webhook_400_message(client):
    r = _post(client, target="webhook")
    assert "webhook" in r.json()["detail"].lower()


def test_webhook_ok_with_url(client):
    r = _post(client, target="webhook",
              webhook_url="https://hook.example")
    assert r.status_code == 200
    assert r.json()["target"] == "WEBHOOK_HMAC"


def test_webhook_args(client):
    _post(client, target="webhook",
          webhook_url="https://hook.example", secret="S")
    a = _CMS.webhook_kw[0]
    assert a[0] == "https://hook.example"
    assert a[1] == "S"


def test_webhook_payload_has_brand(client):
    _post(client, target="webhook",
          webhook_url="https://hook.example")
    a = _CMS.webhook_kw[0]
    assert a[2]["brand"] == "Acme"


# -- wordpress target ---------------------------------------------------------------------------------

def test_wp_400_without_url(client):
    r = _post(client, target="wordpress",
              wp_user="u", wp_pass="p")
    assert r.status_code == 400


def test_wp_400_without_user(client):
    r = _post(client, target="wordpress",
              wp_url="https://wp.example", wp_pass="p")
    assert r.status_code == 400


def test_wp_400_without_pass(client):
    r = _post(client, target="wordpress",
              wp_url="https://wp.example", wp_user="u")
    assert r.status_code == 400


def test_wp_ok_all_fields(client):
    r = _post(client, target="wordpress",
              wp_url="https://wp.example", wp_user="u", wp_pass="p")
    assert r.status_code == 200
    assert r.json()["target"] == "WORDPRESS_REST"


def test_wp_args(client):
    _post(client, target="wordpress",
          wp_url="https://wp.example", wp_user="u", wp_pass="p")
    a = _CMS.wp_kw[0]
    assert a[0] == "https://wp.example"
    assert a[1] == "u"
    assert a[2] == "p"
    assert len(a[3]) == 3


# -- bilinmeyen target ---------------------------------------------------------------------------------

def test_unknown_target_400(client):
    r = _post(client, target="ftp")
    assert r.status_code == 400


def test_unknown_target_no_cms_call(client):
    _post(client, target="ftp")
    assert _CMS.local_kw is None
    assert _CMS.webhook_kw is None
    assert _CMS.wp_kw is None


# -- validation ---------------------------------------------------------------------------------

def test_missing_brand_422(client):
    r = client.post("/api/deploy",
                    content=json.dumps({"domain": "d"}),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_missing_domain_422(client):
    r = client.post("/api/deploy",
                    content=json.dumps({"brand_name": "b"}),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_default_target_local(client):
    r = _post(client)
    assert r.json()["target"] == "LOCAL_EXPORT"


# -- hata ---------------------------------------------------------------------------------

def test_cms_error_500(client):
    _CMS.raises = RuntimeError("disk dolu")
    with pytest.raises(RuntimeError):
        _post(client)


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(client):
    a = _post(client).json()
    b = _post(client).json()
    assert a == b
