from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .base import BaseHandler
from ..models import PageContent, ImageData, HandlerConfig, AttachmentInfo

logger = logging.getLogger(__name__)

BASE_URL = "https://lanhuapp.com"
DDS_BASE_URL = "https://dds.lanhuapp.com"
HTTP_TIMEOUT = 30.0


class LanhuClient:
    def __init__(self, cookie: str, dds_cookie: str = "") -> None:
        self.cookie = cookie
        self.dds_cookie = dds_cookie or cookie
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=HTTP_TIMEOUT,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://lanhuapp.com/web/",
                    "Accept": "application/json, text/plain, */*",
                    "Cookie": self.cookie,
                    "sec-ch-ua-mobile": "?0",
                    "request-from": "web",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def parse_url(url: str) -> dict:
        if url.startswith("http"):
            parsed = urlparse(url)
            fragment = parsed.fragment
            if not fragment:
                raise ValueError("Invalid Lanhu URL: missing fragment part")
            if "?" in fragment:
                url = fragment.split("?", 1)[1]
            else:
                url = fragment

        if url.startswith("?"):
            url = url[1:]

        params: dict[str, str] = {}
        for part in url.split("&"):
            if "=" in part:
                key, value = part.split("=", 1)
                params[key] = value

        project_id = params.get("pid")
        if not project_id:
            raise ValueError("URL parsing failed: missing required param pid (project_id)")

        return {
            "team_id": params.get("tid"),
            "project_id": project_id,
            "doc_id": params.get("docId") or params.get("image_id"),
            "version_id": params.get("versionId"),
        }

    async def _api_get(self, url: str, params: dict | None = None) -> dict:
        client = self._get_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        code = data.get("code")
        if code not in (0, "0", "00000"):
            raise Exception(f"Lanhu API error: {data.get('msg')} (code={code})")
        return data.get("data") or data.get("result", {})

    async def get_project_info(self, project_id: str, team_id: str | None = None) -> dict:
        params: dict = {"project_id": project_id, "img_limit": "500", "detach": "1"}
        if team_id:
            params["team_id"] = team_id
        return await self._api_get(f"{BASE_URL}/api/project/multi_info", params)

    async def get_design_list(self, project_id: str, team_id: str | None = None) -> dict:
        params: dict = {
            "project_id": project_id,
            "dds_status": "1",
            "position": "1",
            "show_cb_src": "1",
            "comment": "1",
        }
        if team_id:
            params["team_id"] = team_id
        return await self._api_get(f"{BASE_URL}/api/project/images", params)

    async def get_document_info(self, project_id: str, doc_id: str) -> dict:
        return await self._api_get(
            f"{BASE_URL}/api/project/image",
            {"pid": project_id, "image_id": doc_id},
        )

    async def get_product_documents(self, team_id: str, project_id: str) -> dict:
        return await self._api_get(
            f"{BASE_URL}/api/project/product_documents",
            {"team_id": team_id, "project_id": project_id},
        )

    async def get_project_sectors(self, project_id: str) -> dict:
        return await self._api_get(
            f"{BASE_URL}/api/project/project_sectors",
            {"project_id": project_id},
        )

    async def get_version_id_by_image_id(self, project_id: str, image_id: str, team_id: str | None = None) -> str:
        info = await self.get_project_info(project_id, team_id)
        images = info.get("images", [])
        for img in images:
            if img.get("id") == image_id:
                vid = img.get("latest_version")
                if vid:
                    return vid
                raise Exception(f"No latest_version for image_id={image_id}")
        raise Exception(f"image_id={image_id} not found in project")

    async def get_dds_schema(self, version_id: str) -> dict:
        dds_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://dds.lanhuapp.com/",
            "Cookie": self.dds_cookie,
            "Authorization": "Basic dW5kZWZpbmVkOg==",
        }
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=dds_headers, follow_redirects=True) as dds_client:
            resp = await dds_client.get(
                f"{DDS_BASE_URL}/api/dds/image/store_schema_revise",
                params={"version_id": version_id},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "00000":
                raise Exception(f"DDS schema error: {data.get('msg')}")
            schema_url = (data.get("data") or {}).get("data_resource_url")
            if not schema_url:
                raise Exception("DDS did not return data_resource_url")
            schema_resp = await dds_client.get(schema_url)
            schema_resp.raise_for_status()
            return schema_resp.json()

    async def get_sketch_json(self, project_id: str, image_id: str, team_id: str | None = None) -> dict:
        doc_info = await self.get_document_info(project_id, image_id)
        versions = doc_info.get("versions", [])
        if not versions:
            raise Exception("No versions found for image")
        json_url = versions[0].get("json_url")
        if not json_url:
            raise Exception("No json_url in version")
        client = self._get_client()
        resp = await client.get(json_url)
        resp.raise_for_status()
        return resp.json()

    async def download_image_as_base64(self, image_url: str, max_size_mb: int = 10) -> tuple[str, str]:
        client = self._get_client()
        resp = await client.get(image_url)
        resp.raise_for_status()
        if len(resp.content) > max_size_mb * 1024 * 1024:
            raise ValueError(f"Image too large: {len(resp.content) / 1024 / 1024:.1f}MB (limit {max_size_mb}MB)")
        mime = resp.headers.get("content-type", "image/png")
        if not mime.startswith("image/"):
            mime = "image/png"
        b64 = base64.b64encode(resp.content).decode()
        return b64, mime


class LanhuHandler(BaseHandler):
    LANHU_DOMAINS = ("lanhu.com", "lanhuapp.com", "lhcdn.com")

    def __init__(self, config: HandlerConfig | None = None) -> None:
        self._config = config
        self._client: LanhuClient | None = None

    def _get_client(self) -> LanhuClient:
        if self._client is None:
            cookie = ""
            dds_cookie = ""
            if self._config and self._config.auth:
                cookie = os.environ.get(self._config.auth.env, "")
            if not cookie:
                cookie = os.environ.get("LANHU_COOKIE", "")
            dds_cookie = os.environ.get("DDS_COOKIE", cookie)
            if not cookie:
                raise ValueError(
                    "Lanhu cookie not configured. Set LANHU_COOKIE env var or configure auth in life-saver-mcp.json"
                )
            self._client = LanhuClient(cookie, dds_cookie)
        return self._client

    def can_handle(self, url: str) -> bool:
        return any(d in url for d in self.LANHU_DOMAINS)

    async def fetch_content(self, url: str) -> PageContent:
        client = self._get_client()
        try:
            params = client.parse_url(url)
            project_id = params["project_id"]
            team_id = params.get("team_id")
            doc_id = params.get("doc_id")

            if doc_id:
                return await self._fetch_document(client, url, project_id, team_id, doc_id)
            else:
                return await self._fetch_designs(client, url, project_id, team_id)
        except Exception as e:
            logger.exception("Lanhu fetch_content failed")
            raise

    async def _fetch_document(
        self,
        client: LanhuClient,
        url: str,
        project_id: str,
        team_id: str | None,
        doc_id: str,
    ) -> PageContent:
        from .lanhu_axure import download_axure_resources, screenshot_axure_pages

        doc_info = await client.get_document_info(project_id, doc_id)
        title = doc_info.get("name", "")
        doc_type = doc_info.get("type", "")

        text_sections: list[str] = [f"Document: {title}"]
        if doc_type:
            text_sections.append(f"Type: {doc_type}")
        if doc_info.get("description"):
            text_sections.append(f"Description: {doc_info['description']}")

        versions = doc_info.get("versions", [])
        if versions:
            latest = versions[0]
            text_sections.append(f"Version: {latest.get('version_num', 'N/A')}")

        images: list[ImageData] = []

        try:
            with tempfile.TemporaryDirectory(prefix="lanhu_axure_") as tmp_dir:
                cache_dir = Path(tmp_dir) / "axure_resources"
                resource_dir = await download_axure_resources(client._get_client(), doc_info, cache_dir)
                if resource_dir:
                    page_names = [p.stem for p in resource_dir.glob("*.html")][:5]
                    if page_names:
                        screenshots = await screenshot_axure_pages(resource_dir, page_names, max_pages=5)
                        for s in screenshots:
                            if s.get("success") and s.get("base64"):
                                images.append(ImageData(
                                    data=s["base64"],
                                    mime_type=s["mime_type"],
                                    source=f"axure:{s['page_name']}",
                                ))
                                if s.get("page_text"):
                                    text_sections.append(f"[{s['page_name']}] {s['page_text'][:500]}")
        except Exception as e:
            logger.warning("Axure screenshot failed: %s", e)

        if not images:
            for version in versions[:3]:
                img_url = version.get("url")
                if img_url:
                    try:
                        clean_url = img_url.split("?")[0]
                        b64, mime = await client.download_image_as_base64(clean_url)
                        images.append(ImageData(data=b64, mime_type=mime, source=clean_url))
                    except Exception as e:
                        logger.warning("Failed to download doc image: %s", e)

        return PageContent(
            url=url,
            title=title,
            text_sections=text_sections,
            images=images,
            metadata={"doc_id": doc_id, "project_id": project_id, "team_id": team_id, "doc_type": doc_type},
            source_type="lanhu_document",
        )

    async def _fetch_designs(
        self,
        client: LanhuClient,
        url: str,
        project_id: str,
        team_id: str | None,
    ) -> PageContent:
        from .lanhu_annotations import extract_annotations, extract_design_tokens
        from .lanhu_slices import extract_slices

        design_data = await client.get_design_list(project_id, team_id)
        project_name = design_data.get("name", "")
        img_list = design_data.get("images", [])

        text_sections: list[str] = [f"Project: {project_name}"]
        text_sections.append(f"Total designs: {len(img_list)}")

        for idx, img in enumerate(img_list[:10], 1):
            info = f"Design {idx}: {img.get('name', 'N/A')}"
            if img.get("width") and img.get("height"):
                info += f" ({img['width']}x{img['height']})"
            text_sections.append(info)

        images: list[ImageData] = []
        annotations_text = ""
        slices_info: list[dict] = []

        for img in img_list[:3]:
            img_id = img.get("id")
            img_url = img.get("url")
            if not img_url:
                continue

            try:
                clean_url = img_url.split("?")[0]
                b64, mime = await client.download_image_as_base64(clean_url)
                images.append(ImageData(data=b64, mime_type=mime, source=clean_url))
            except Exception as e:
                logger.warning("Failed to download design image: %s", e)

            if img_id and not annotations_text:
                try:
                    sketch_data = await client.get_sketch_json(project_id, img_id, team_id)
                    annotations_text = extract_annotations(sketch_data)
                    tokens = extract_design_tokens(sketch_data)
                    if tokens:
                        annotations_text += f"\n\n--- Design Tokens ---\n{tokens}"
                    slices_info = extract_slices(sketch_data)
                except Exception as e:
                    logger.info("Could not extract annotations for %s: %s", img_id, e)

        if annotations_text:
            text_sections.append(f"\n{annotations_text}")

        attachments: list[AttachmentInfo] = []
        for s in slices_info[:20]:
            attachments.append(AttachmentInfo(
                name=s.get("name", ""),
                url=s.get("download_url", ""),
                extension=s.get("format", ""),
                size=f"{s.get('logical_width', 0)}x{s.get('logical_height', 0)}",
            ))

        return PageContent(
            url=url,
            title=project_name,
            text_sections=text_sections,
            images=images,
            attachments=attachments,
            metadata={"project_id": project_id, "team_id": team_id},
            source_type="lanhu_design",
        )
