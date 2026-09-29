"""One-Click CMS & Webhook Deployment Engine for AnswRank.

Enables instant, automated deployment of generated AEO assets (robots.txt, llms.txt, JSON-LD schema):
1. WordPress REST API Connector (Application Passwords)
2. Webflow / Generic HMAC-SHA256 Webhook Dispatcher
3. GitHub Repository Direct Commit / PR Engine
4. Local Agency ZIP/Directory Bundle Exporter
"""

import hmac
import hashlib
import json
import logging
import os
import httpx
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("answrank.deployer")
from pydantic import BaseModel, Field


class DeployTarget(str, Enum):
    WORDPRESS_REST = "WORDPRESS_REST"
    WEBHOOK_HMAC = "WEBHOOK_HMAC"
    GITHUB_COMMIT = "GITHUB_COMMIT"
    LOCAL_EXPORT = "LOCAL_EXPORT"


class DeploymentResult(BaseModel):
    """Result of automated asset deployment."""
    success: bool
    target: DeployTarget
    status_code: int
    message: str
    deployed_files: List[str] = Field(default_factory=list)
    remote_url: Optional[str] = None


class CMSDeployer:
    """Manages one-click deployment of generated AEO/GEO fixes to client platforms."""

    @classmethod
    async def deploy_wordpress(
        cls,
        wp_site_url: str,
        username: str,
        app_password: str,
        fixes: Dict[str, str],
    ) -> DeploymentResult:
        """Deploys the AEO/GEO bundle to a WordPress site via REST API.

        REAL deployment (not just a connection test):
        1. Authenticates via Application Password (`/users/me`).
        2. Uploads each text asset (robots.txt, llms.txt, llms-full.txt) as a
           dedicated page with a recognizable slug so it is served at
           `/{slug}` (e.g. `https://site.com/llms.txt`).
        3. Injects the JSON-LD schema into the site header via the `head_footer`
           option when available (common header-plugin endpoint) or records it
           in a private page for the webmaster when the option is locked.
        """
        clean_url = wp_site_url.rstrip("/")
        auth = (username, app_password)

        try:
            async with httpx.AsyncClient(timeout=20.0, verify=True) as client:
                # 1. Authenticate
                verify_resp = await client.get(f"{clean_url}/wp-json/wp/v2/users/me", auth=auth)
                if verify_resp.status_code not in (200, 201):
                    return DeploymentResult(
                        success=False,
                        target=DeployTarget.WORDPRESS_REST,
                        status_code=verify_resp.status_code,
                        message=f"WordPress authentication failed (HTTP {verify_resp.status_code}). Check Application Password.",
                    )

                deployed: List[str] = []
                failed: List[str] = []

                # 2. Create/refresh one page per text asset (served at /{slug})
                #    e.g. slug "llms.txt" -> https://site.com/llms.txt
                for filename, content in fixes.items():
                    if filename.endswith(".jsonld"):
                        continue  # schema is injected into the header, not a page
                    slug = filename  # "llms.txt", "robots.txt", "llms-full.txt"

                    # Search for an existing page with the same slug to update instead of duplicating
                    search_resp = await client.get(
                        f"{clean_url}/wp-json/wp/v2/pages",
                        params={"slug": slug, "per_page": 1},
                        auth=auth,
                    )
                    page_id = None
                    if search_resp.status_code == 200:
                        results = search_resp.json()
                        if isinstance(results, list) and results:
                            page_id = results[0].get("id")

                    payload = {
                        "title": f"AnswRank {filename}",
                        "slug": slug,
                        "content": f"<pre>{content}</pre>",
                        "status": "publish",
                        "content_type": "text/plain",
                    }
                    if page_id:
                        upsert_resp = await client.post(
                            f"{clean_url}/wp-json/wp/v2/pages/{page_id}",
                            json=payload,
                            auth=auth,
                        )
                    else:
                        upsert_resp = await client.post(
                            f"{clean_url}/wp-json/wp/v2/pages",
                            json=payload,
                            auth=auth,
                        )

                    if upsert_resp.status_code in (200, 201):
                        deployed.append(filename)
                    else:
                        failed.append(f"{filename} (HTTP {upsert_resp.status_code})")

                # 3. Inject JSON-LD into the site header via head_footer option if present
                schema_content = fixes.get("schema.jsonld")
                if schema_content:
                    settings_resp = await client.post(
                        f"{clean_url}/wp-json/wp/v2/settings",
                        json={"head_footer": f"\n{schema_content}"},
                        auth=auth,
                    )
                    if settings_resp.status_code in (200, 201):
                        deployed.append("schema.jsonld (header injection)")
                    else:
                        # Fallback: store schema in a private page for the webmaster
                        schema_page = await client.post(
                            f"{clean_url}/wp-json/wp/v2/pages",
                            json={
                                "title": "AnswRank JSON-LD Schema (paste into header)",
                                "slug": "answrank-schema",
                                "content": f"<pre>{schema_content}</pre>",
                                "status": "private",
                            },
                            auth=auth,
                        )
                        if schema_page.status_code in (200, 201):
                            deployed.append("schema.jsonld (private page — manual header paste needed)")

                if deployed:
                    msg = f"Deployed {len(deployed)} asset(s) to WordPress: {', '.join(deployed)}."
                    if failed:
                        msg += f" Failed: {', '.join(failed)}."
                    if "header injection" not in " ".join(deployed) and schema_content:
                        msg += " Schema stored as private page; header injection requires a header plugin or theme edit."
                    return DeploymentResult(
                        success=True,
                        target=DeployTarget.WORDPRESS_REST,
                        status_code=200,
                        message=msg,
                        deployed_files=deployed,
                        remote_url=clean_url,
                    )
                return DeploymentResult(
                    success=False,
                    target=DeployTarget.WORDPRESS_REST,
                    status_code=500,
                    message=f"No assets deployed. Failures: {', '.join(failed) or 'unknown'}",
                )
        except Exception:
            logger.exception("WordPress deploy hatası (müşteriye iletilmedi)")
            return DeploymentResult(
                success=False,
                target=DeployTarget.WORDPRESS_REST,
                status_code=500,
                message="WordPress bağlantı hatası (ayrıntılar sunucu günlüğünde).",
            )

    @classmethod
    async def deploy_webhook(
        cls,
        webhook_url: str,
        secret_key: str,
        payload_data: Dict[str, Any],
    ) -> DeploymentResult:
        """Dispatches an HMAC-SHA256 signed webhook for Webflow, Make.com, or Zapier automation."""
        raw_body = json.dumps(payload_data, sort_keys=True)
        signature = hmac.new(
            secret_key.encode("utf-8"),
            raw_body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-AnswRank-Signature": f"sha256={signature}",
            "User-Agent": "AnswRank-Deployer/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=True) as client:
                resp = await client.post(webhook_url, content=raw_body, headers=headers)
                success = 200 <= resp.status_code < 300
                return DeploymentResult(
                    success=success,
                    target=DeployTarget.WEBHOOK_HMAC,
                    status_code=resp.status_code,
                    message="Webhook successfully dispatched" if success else f"Webhook rejected with HTTP {resp.status_code}",
                    deployed_files=list(payload_data.get("fixes", {}).keys()),
                    remote_url=webhook_url,
                )
        except Exception:
            logger.exception("Webhook deploy hatası (müşteriye iletilmedi)")
            return DeploymentResult(
                success=False,
                target=DeployTarget.WEBHOOK_HMAC,
                status_code=500,
                message="Webhook teslimi başarısız (ayrıntılar sunucu günlüğünde).",
            )

    @classmethod
    async def deploy_github(
        cls,
        repo_owner: str,
        repo_name: str,
        branch: str,
        github_token: str,
        fixes: Dict[str, str],
        commit_message: str = "chore(aeo): automate AnswRank llms.txt and schema generation",
    ) -> DeploymentResult:
        """Commits generated fixes directly to a GitHub repository via GitHub REST API."""
        api_base = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents"
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AnswRank-Deployer/1.0",
        }

        deployed = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for file_path, content in fixes.items():
                    target_endpoint = f"{api_base}/{file_path}"
                    # Check if file exists to fetch sha
                    sha = None
                    check_resp = await client.get(f"{target_endpoint}?ref={branch}", headers=headers)
                    if check_resp.status_code == 200:
                        sha = check_resp.json().get("sha")

                    import base64
                    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                    put_data = {
                        "message": commit_message,
                        "content": encoded_content,
                        "branch": branch,
                    }
                    if sha:
                        put_data["sha"] = sha

                    put_resp = await client.put(target_endpoint, json=put_data, headers=headers)
                    if put_resp.status_code in (200, 201):
                        deployed.append(file_path)

                return DeploymentResult(
                    success=len(deployed) > 0,
                    target=DeployTarget.GITHUB_COMMIT,
                    status_code=200 if deployed else 400,
                    message=f"Pushed {len(deployed)} files to {repo_owner}/{repo_name}:{branch}",
                    deployed_files=deployed,
                    remote_url=f"https://github.com/{repo_owner}/{repo_name}/tree/{branch}",
                )
        except Exception:
            logger.exception("GitHub deploy hatası (müşteriye iletilmedi)")
            return DeploymentResult(
                success=False,
                target=DeployTarget.GITHUB_COMMIT,
                status_code=500,
                message="GitHub dağıtım hatası (ayrıntılar sunucu günlüğünde).",
            )

    @classmethod
    def export_local_bundle(cls, output_dir: str, fixes: Dict[str, str]) -> DeploymentResult:
        """Exports generated files locally to an agency handoff directory."""
        try:
            os.makedirs(output_dir, exist_ok=True)
            deployed = []
            for filename, content in fixes.items():
                target_file = os.path.join(output_dir, filename)
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(content)
                deployed.append(filename)

            return DeploymentResult(
                success=True,
                target=DeployTarget.LOCAL_EXPORT,
                status_code=200,
                message=f"Exported {len(deployed)} files locally to {output_dir}",
                deployed_files=deployed,
                remote_url=output_dir,
            )
        except Exception:
            logger.exception("Local export hatası (müşteriye iletilmedi)")
            return DeploymentResult(
                success=False,
                target=DeployTarget.LOCAL_EXPORT,
                status_code=500,
                message="Yerel dışa aktarım başarısız (ayrıntılar sunucu günlüğünde).",
            )
