from __future__ import annotations

import base64
import json
import logging
import os
import re
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from .base import BaseHandler
from ..models import PageContent, ImageData, HandlerConfig, AttachmentInfo

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30.0


class ZentaoClient:
    def __init__(self, base_url: str, cookie: str = "", token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie = cookie
        self.token = token
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            zin_options = json.dumps({
                "selector": [
                    "#configJS", "pageCSS/.zin-page-css>*", "pageJS/.zin-page-js",
                    "hookCode()", "title>*", "#heading>*", "#navbar>*",
                    "#pageToolbar>*", "#main>*", "",
                ],
                "type": "list",
            })
            headers: dict[str, str] = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "X-Requested-With": "XMLHttpRequest",
                "X-ZIN-Options": zin_options,
                "X-Zin-Cache-Time": "0",
            }
            if self.token:
                headers["Token"] = self.token
            elif self.cookie:
                headers["Cookie"] = self.cookie
            self._client = httpx.AsyncClient(
                timeout=HTTP_TIMEOUT,
                headers=headers,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_page_zin(self, url: str) -> dict[str, str] | None:
        sep = "&" if "?" in url else "?"
        zin_url = f"{url}{sep}zin=1"
        try:
            client = self._get_client()
            resp = await client.get(zin_url)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                return None
            result: dict[str, str] = {}
            for item in data:
                name = item.get("name", "")
                item_data = item.get("data", "")
                if name and item_data:
                    result[name] = item_data
            return result
        except Exception as e:
            logger.info("ZIN request failed, falling back to HTML: %s", e)
            return None

    async def fetch_page_html(self, url: str) -> str:
        client = self._get_client()
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text

    async def download_image_base64(self, image_url: str, max_size_mb: int = 10) -> tuple[str, str]:
        if not image_url.startswith("http"):
            image_url = f"{self.base_url}{image_url}"
        client = self._get_client()
        resp = await client.get(image_url)
        resp.raise_for_status()

        content_length = resp.headers.get("content-length")
        if content_length and int(content_length) > max_size_mb * 1024 * 1024:
            raise ValueError(f"Image too large: {int(content_length) / 1024 / 1024:.1f}MB (limit {max_size_mb}MB)")

        if len(resp.content) > max_size_mb * 1024 * 1024:
            raise ValueError(f"Image too large: {len(resp.content) / 1024 / 1024:.1f}MB (limit {max_size_mb}MB)")

        mime = resp.headers.get("content-type", "image/png")
        if not mime.startswith("image/"):
            mime = "image/png"
        b64 = base64.b64encode(resp.content).decode()
        return b64, mime


class ZentaoHandler(BaseHandler):
    def __init__(self, config: HandlerConfig | None = None) -> None:
        self._config = config

    def _get_client(self) -> ZentaoClient:
        base_url = self._get_base_url()
        auth_type = "cookie"
        if self._config and self._config.auth:
            auth_type = self._config.auth.type

        if auth_type == "password":
            account = os.environ.get("ZENTAO_ACCOUNT", "")
            password = os.environ.get("ZENTAO_PASSWORD", "")
            if not account or not password:
                raise ValueError(
                    "Zentao account/password not configured. Set ZENTAO_ACCOUNT and ZENTAO_PASSWORD env vars"
                )
            cookie = self._api_login(base_url, account, password)
            return ZentaoClient(base_url, cookie=cookie)

        if auth_type == "token":
            token = ""
            if self._config and self._config.auth:
                token = os.environ.get(self._config.auth.env, "")
            if not token:
                token = os.environ.get("ZENTAO_TOKEN", "")
            if not token:
                raise ValueError(
                    "Zentao token not configured. Set ZENTAO_TOKEN env var or configure auth in life-saver-mcp.json"
                )
            return ZentaoClient(base_url, token=token)

        # Default: cookie
        cookie = ""
        if self._config and self._config.auth:
            cookie = os.environ.get(self._config.auth.env, "")
        if not cookie:
            cookie = os.environ.get("ZENTAO_COOKIE", "")
        if not cookie:
            raise ValueError(
                "Zentao cookie not configured. Set ZENTAO_COOKIE env var or configure auth in life-saver-mcp.json"
            )
        return ZentaoClient(base_url, cookie=cookie)

    @staticmethod
    def _api_login(base_url: str, account: str, password: str) -> str:
        import hashlib

        hashed_pw = hashlib.md5(password.encode()).hexdigest()

        with httpx.Client(
            timeout=HTTP_TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        ) as login_client:
            login_page = login_client.get(f"{base_url}/index.php?m=user&f=login")

            verify_rand = ""
            match_vr = re.search(r'name="verifyRand"\s+value="(\d+)"', login_page.text)
            if match_vr:
                verify_rand = match_vr.group(1)

            boundary = "----WebKitFormBoundaryZENTAO"
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="account"\r\n\r\n'
                f'{account}\r\n'
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="password"\r\n\r\n'
                f'{hashed_pw}\r\n'
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="passwordStrength"\r\n\r\n'
                f'1\r\n'
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="verifyRand"\r\n\r\n'
                f'{verify_rand}\r\n'
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="keepLogin"\r\n\r\n'
                f'1\r\n'
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="captcha"\r\n\r\n'
                f'\r\n'
                f"--{boundary}--\r\n"
            )

            post_resp = login_client.post(
                f"{base_url}/index.php?m=user&f=login&t=json",
                content=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{base_url}/index.php?m=user&f=login",
                },
            )

            cookies = dict(login_client.cookies)
            if "zentaosid" not in cookies:
                try:
                    err = post_resp.json()
                    raise ValueError(f"Zentao login failed: {err.get('message', post_resp.text[:200])}")
                except Exception:
                    raise ValueError(f"Zentao login failed: {post_resp.text[:200]}")

            try:
                resp_data = post_resp.json()
                rand_from_resp = ""
                data_str = resp_data.get("data", "")
                if isinstance(data_str, str):
                    inner = json.loads(data_str)
                    rand_from_resp = str(inner.get("rand", ""))
                elif isinstance(data_str, dict):
                    rand_from_resp = str(data_str.get("rand", ""))
                if rand_from_resp:
                    zp = hashlib.sha1((hashed_pw + rand_from_resp).encode()).hexdigest()
                    cookies["zp"] = zp
            except Exception:
                pass

            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            return cookie_str

    def _get_base_url(self) -> str:
        if self._config and self._config.url:
            return self._config.url.rstrip("/")
        return os.environ.get("ZENTAO_URL", "https://zentao.example.com")

    def can_handle(self, url: str) -> bool:
        config_domain = self._extract_domain(self._get_base_url())
        if not config_domain:
            return False
        url_domain = self._extract_domain(url)
        return url_domain == config_domain

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            parsed = urlparse(url if "://" in url else f"http://{url}")
            return parsed.hostname or ""
        except Exception:
            return ""

    @staticmethod
    def parse_url_params(url: str) -> dict[str, str] | None:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        m = params.get("m", [None])[0]
        if not m:
            path_match = re.search(r"/(\w+)-view-(\d+)", parsed.path)
            if path_match:
                return {"type": path_match.group(1), "id": path_match.group(2)}
            return None

        entry_type = m.lower()
        object_id = None

        if entry_type == "bug":
            object_id = params.get("bugID", [None])[0]
        elif entry_type in ("story", "requirement", "projectstory"):
            object_id = params.get("id", [None])[0] or params.get("storyID", [None])[0]
        elif entry_type == "task":
            object_id = params.get("taskID", [None])[0]
        elif entry_type == "testcase":
            object_id = params.get("caseID", [None])[0] or params.get("id", [None])[0]
        elif entry_type == "testtask":
            object_id = params.get("testtaskID", [None])[0]

        if not object_id:
            return None

        return {"type": entry_type, "id": object_id}

    async def fetch_content(self, url: str) -> PageContent:
        client = self._get_client()
        try:
            params = self.parse_url_params(url)
            entry_type = params["type"] if params else "generic"
            entry_id = params["id"] if params else ""
        except Exception:
            entry_type = "generic"
            entry_id = ""

        try:
            return await self._fetch_page(client, url, entry_type, entry_id)
        except Exception as e:
            logger.exception("Zentao fetch_content failed")
            raise

    async def _fetch_zin_or_html(self, client: ZentaoClient, url: str) -> tuple[str, BeautifulSoup]:
        zin_data = await client.fetch_page_zin(url)
        if zin_data:
            title = self._extract_text_from_html(zin_data.get("title", ""))
            main_html = zin_data.get("main", "")
            soup = BeautifulSoup(main_html, "html.parser")
            return title, soup

        html = await client.fetch_page_html(url)
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        main_content = soup.find(id="mainContent") or soup.find(class_="detail-view") or soup
        return title, main_content

    @staticmethod
    def _extract_text_from_html(html_str: str) -> str:
        soup = BeautifulSoup(html_str, "html.parser")
        return soup.get_text(strip=True)

    def _extract_detail_fields(self, soup: BeautifulSoup) -> dict[str, str]:
        fields: dict[str, str] = {}
        for item in soup.find_all(class_="datalist-item"):
            label_el = item.find(class_="datalist-item-label")
            content_el = item.find(class_="datalist-item-content")
            if label_el and content_el:
                label = label_el.get_text(strip=True).rstrip("：:")
                value = content_el.get_text(strip=True)
                if label and value:
                    fields[label] = value
        return fields

    def _extract_article_content(self, soup: BeautifulSoup) -> list[str]:
        sections: list[str] = []
        for article in soup.find_all(class_="article"):
            text = article.get_text(strip=True)
            if text:
                sections.append(text)
        return sections

    def _extract_images(self, soup: BeautifulSoup) -> list[str]:
        seen: set[str] = set()
        image_urls: list[str] = []

        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src and self._is_zentao_file_url(src) and src not in seen:
                seen.add(src)
                image_urls.append(src)

        for el in soup.find_all(attrs={"zui-create-historypanel": True}):
            attr_val = el.get("zui-create-historypanel", "")
            if not attr_val:
                continue
            for match in re.findall(r'["\'](/index\.php\?[^"\']*fileID=\d+[^"\']*)["\']', attr_val):
                url = match.replace("&amp;", "&")
                if url not in seen:
                    seen.add(url)
                    image_urls.append(url)

        return image_urls

    @staticmethod
    def _is_zentao_file_url(src: str) -> bool:
        return "fileID=" in src or "file&f=read" in src

    def _extract_attachments(self, soup: BeautifulSoup) -> list[AttachmentInfo]:
        seen_ids: set[str] = set()
        attachments: list[AttachmentInfo] = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "file&f=download" not in href or "fileID=" not in href:
                continue
            match = re.search(r"fileID=(\d+)", href)
            if not match:
                continue
            file_id = match.group(1)
            if file_id in seen_ids:
                continue
            seen_ids.add(file_id)
            name = a.get_text(strip=True)
            if not name:
                name = f"attachment_{file_id}"
            url = href.replace("&amp;", "&")

            ext = ""
            bare_name = re.sub(r"\([\d.]+\s*[KMGT]?B\)$", "", name).strip()
            name_lower = bare_name.lower()
            for known in (".doc", ".docx", ".pdf", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar", ".txt", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".bmp"):
                if name_lower.endswith(known):
                    ext = known.lstrip(".")
                    break

            size = ""
            size_match = re.search(r"\(([\d.]+\s*[KMGT]?B)\)", name)
            if size_match:
                size = size_match.group(1)

            attachments.append(AttachmentInfo(
                file_id=file_id,
                name=name,
                url=url,
                extension=ext,
                size=size,
            ))

        return attachments

    def _extract_history_comments(self, soup: BeautifulSoup) -> list[str]:
        comments: list[str] = []

        for comment_el in soup.find_all(class_="comment-content"):
            text = comment_el.get_text(strip=True)
            if text:
                comments.append(text)
        for action in soup.find_all(class_="history-panel-action"):
            text = action.get_text(strip=True)
            if text:
                comments.append(text)

        for el in soup.find_all(attrs={"zui-create-historypanel": True}):
            attr_val = el.get("zui-create-historypanel", "")
            if not attr_val:
                continue
            try:
                data = json.loads(attr_val)
                for action in data.get("actions", []):
                    content = action.get("content", "")
                    if content:
                        content_soup = BeautifulSoup(content, "html.parser")
                        text = content_soup.get_text(strip=True)
                        if text:
                            comments.append(text)
                    comment = action.get("comment", "")
                    if comment:
                        comment_soup = BeautifulSoup(comment, "html.parser")
                        text = comment_soup.get_text(strip=True)
                        if text:
                            comments.append(text)
            except (json.JSONDecodeError, AttributeError):
                continue

        return comments

    async def _download_images(self, client: ZentaoClient, image_urls: list[str]) -> list[ImageData]:
        from ..analysis.image_utils import extract_gif_frames
        images: list[ImageData] = []
        for img_url in image_urls:
            try:
                b64, mime = await client.download_image_base64(img_url)
                frames = extract_gif_frames(b64, mime)
                for frame_b64, frame_mime in frames:
                    images.append(ImageData(data=frame_b64, mime_type=frame_mime, source=img_url))
            except Exception as e:
                logger.warning("Failed to download zentao image %s: %s", img_url, e)
        return images

    async def _fetch_page(self, client: ZentaoClient, url: str, entry_type: str, entry_id: str) -> PageContent:
        title, soup = await self._fetch_zin_or_html(client, url)

        type_labels = {
            "bug": "Bug",
            "story": "研发需求",
            "requirement": "用户需求",
            "projectstory": "研发需求",
            "task": "任务",
        }
        label = type_labels.get(entry_type, "禅道页面")
        prefix = f"{label} #{entry_id}: " if entry_id else f"{label}: "
        text_sections: list[str] = [f"{prefix}{title}"]

        fields = self._extract_detail_fields(soup)
        for k, v in fields.items():
            text_sections.append(f"{k}: {v}")

        for section in self._extract_article_content(soup):
            text_sections.append(section)

        history = self._extract_history_comments(soup)
        if history:
            text_sections.append("历史记录/备注:")
            for h in history:
                text_sections.append(h)

        attachments = self._extract_attachments(soup)
        if attachments:
            text_sections.append("附件 (可通过 download_url 下载后解析):")
            for att in attachments:
                line = f"  - {att.name}"
                if att.extension:
                    line += f" [{att.extension}]"
                if att.size:
                    line += f" {att.size}"
                line += f" download_url={att.url}"
                text_sections.append(line)

        image_urls = self._extract_images(soup)
        images = await self._download_images(client, image_urls)

        metadata = {"source": "zentao", "entry_type": entry_type, **fields}
        if entry_id:
            metadata["entry_id"] = entry_id

        return PageContent(
            url=url,
            title=title,
            text_sections=text_sections,
            images=images,
            attachments=attachments,
            metadata=metadata,
            source_type=f"zentao_{entry_type}",
        )
