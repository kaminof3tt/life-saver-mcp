from __future__ import annotations

import base64
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .base import BaseHandler
from ..models import PageContent, ImageData


class GenericHandler(BaseHandler):
    def can_handle(self, url: str) -> bool:
        return bool(urlparse(url).scheme in ("http", "https"))

    async def fetch_content(self, url: str) -> PageContent:
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": "LifeSaverMCP/0.1"},
            timeout=30.0,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text_sections: list[str] = []
        for el in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "span", "div"]):
            text = el.get_text(strip=True)
            if text and len(text) > 5:
                text_sections.append(text)

        images: list[ImageData] = []
        for img_tag in soup.find_all("img", src=True):
            src = img_tag["src"]
            if src.startswith("data:"):
                continue
            img_url = urljoin(url, src)
            try:
                async with httpx.AsyncClient(timeout=15.0) as img_client:
                    img_resp = await img_client.get(img_url)
                    img_resp.raise_for_status()
                mime = img_resp.headers.get("content-type", "image/png")
                if not mime.startswith("image/"):
                    continue
                if len(img_resp.content) > 10 * 1024 * 1024:
                    continue
                b64 = base64.b64encode(img_resp.content).decode()
                from ..analysis.image_utils import extract_gif_frames
                frames = extract_gif_frames(b64, mime)
                for frame_b64, frame_mime in frames:
                    images.append(ImageData(data=frame_b64, mime_type=frame_mime, source=img_url))
            except Exception:
                continue

        return PageContent(
            url=url,
            title=title,
            text_sections=text_sections[:100],
            images=images,
            source_type="generic",
        )
