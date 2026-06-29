from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import random
import time
import threading
import http.server
import socketserver
from pathlib import Path

import httpx

from ..models import ImageData

logger = logging.getLogger(__name__)

CDN_URL = "https://axure-file.lanhuapp.com"
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080


async def download_axure_resources(
    client: httpx.AsyncClient,
    doc_info: dict,
    cache_dir: Path,
) -> Path | None:
    versions = doc_info.get("versions", [])
    if not versions:
        return None

    version_info = versions[0]
    json_url = version_info.get("json_url")
    if not json_url:
        return None

    version_id = version_info.get("id", "")

    cache_meta_path = cache_dir / ".axure_cache.json"
    if cache_meta_path.exists():
        import json
        try:
            meta = json.loads(cache_meta_path.read_text(encoding="utf-8"))
            if meta.get("version_id") == version_id and cache_dir.exists():
                logger.info("Axure cache hit for version %s", version_id)
                return cache_dir
        except Exception:
            pass

    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        resp = await client.get(json_url)
        resp.raise_for_status()
        project_mapping = resp.json()
    except Exception as e:
        logger.warning("Failed to download project mapping: %s", e)
        return None

    pages = project_mapping.get("pages", {})
    if not pages:
        return None

    for html_filename, page_info in pages.items():
        html_data = page_info.get("html", {})
        html_md5 = html_data.get("sign_md5", "")
        if not html_md5:
            continue

        html_url = f"{CDN_URL}/{html_md5}"
        try:
            resp = await client.get(html_url)
            resp.raise_for_status()
            html_path = cache_dir / html_filename
            html_path.write_text(resp.text, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to download Axure HTML %s: %s", html_filename, e)

        page_mapping_md5 = page_info.get("mapping_md5", "")
        if page_mapping_md5:
            try:
                mapping_resp = await client.get(f"{CDN_URL}/{page_mapping_md5}")
                mapping_resp.raise_for_status()
                page_mapping = mapping_resp.json()
                await _download_page_assets(client, page_mapping, cache_dir)
            except Exception as e:
                logger.warning("Failed to download page mapping for %s: %s", html_filename, e)

    _fix_html_files(cache_dir)

    import json
    cache_meta = {
        "version_id": version_id,
        "pages": list(pages.keys()),
    }
    cache_meta_path.write_text(json.dumps(cache_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return cache_dir


async def _download_page_assets(client: httpx.AsyncClient, page_mapping: dict, output_dir: Path):
    tasks = []
    for local_path, info in page_mapping.get("styles", {}).items():
        sign_md5 = info.get("sign_md5", "")
        if sign_md5:
            url = sign_md5 if sign_md5.startswith("http") else f"{CDN_URL}/{sign_md5}"
            tasks.append(_download_file(client, url, output_dir / local_path))

    for local_path, info in page_mapping.get("scripts", {}).items():
        sign_md5 = info.get("sign_md5", "")
        if sign_md5:
            url = sign_md5 if sign_md5.startswith("http") else f"{CDN_URL}/{sign_md5}"
            tasks.append(_download_file(client, url, output_dir / local_path))

    for local_path, info in page_mapping.get("images", {}).items():
        sign_md5 = info.get("sign_md5", "")
        if sign_md5:
            url = sign_md5 if sign_md5.startswith("http") else f"{CDN_URL}/{sign_md5}"
            tasks.append(_download_file(client, url, output_dir / local_path))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _download_file(client: httpx.AsyncClient, url: str, local_path: Path):
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        resp = await client.get(url)
        resp.raise_for_status()
        local_path.write_bytes(resp.content)
    except Exception:
        pass


def _fix_html_files(directory: Path):
    from bs4 import BeautifulSoup

    for html_path in directory.glob("*.html"):
        try:
            content = html_path.read_text(encoding="utf-8")
            soup = BeautifulSoup(content, "html.parser")

            for tag in soup.find_all(["img", "script"]):
                if tag.has_attr("data-src"):
                    tag["src"] = tag["data-src"]
                    del tag["data-src"]
            for tag in soup.find_all("link"):
                if tag.has_attr("data-src"):
                    tag["href"] = tag["data-src"]
                    del tag["data-src"]

            body = soup.find("body")
            if body and body.has_attr("style"):
                style = body["style"]
                style = re.sub(r"display\s*:\s*none\s*;?", "", style)
                style = re.sub(r"opacity\s*:\s*0\s*;?", "", style)
                style = style.strip()
                if style:
                    body["style"] = style
                else:
                    del body["style"]

            for script in soup.find_all("script"):
                if script.string and "alistatic.lanhuapp.com" in script.string:
                    script.decompose()

            html_path.write_text(str(soup), encoding="utf-8")
        except Exception:
            pass


async def screenshot_axure_pages(
    resource_dir: Path,
    page_names: list[str],
    max_pages: int = 5,
) -> list[dict]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed, skipping Axure screenshots")
        return []

    results: list[dict] = []
    html_files = list(resource_dir.glob("*.html"))

    target_files: list[Path] = []
    for page_name in page_names:
        for f in html_files:
            if f.stem == page_name:
                target_files.append(f)
                break
    if not target_files:
        target_files = html_files[:max_pages]
    else:
        target_files = target_files[:max_pages]

    if not target_files:
        return []

    port = random.randint(8800, 8900)
    abs_dir = str(resource_dir.resolve())

    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=abs_dir, **kwargs
    )
    httpd = socketserver.TCPServer(("", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})

            for html_file in target_files:
                try:
                    url = f"http://localhost:{port}/{html_file.name}"
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(1500)

                    page_text = await page.evaluate("""() => {
                        const bodyText = document.body.innerText || '';
                        return bodyText.trim();
                    }""")

                    screenshot_bytes = await page.screenshot(full_page=True)
                    b64 = base64.b64encode(screenshot_bytes).decode()

                    results.append({
                        "page_name": html_file.stem,
                        "success": True,
                        "base64": b64,
                        "mime_type": "image/png",
                        "page_text": page_text[:5000],
                        "size": f"{len(screenshot_bytes) / 1024:.1f}KB",
                    })
                except Exception as e:
                    logger.warning("Failed to screenshot %s: %s", html_file.name, e)
                    results.append({
                        "page_name": html_file.stem,
                        "success": False,
                        "error": str(e),
                    })

            await browser.close()
    except Exception as e:
        logger.warning("Playwright error: %s", e)
    finally:
        httpd.shutdown()
        httpd.server_close()

    return results
