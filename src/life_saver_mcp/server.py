from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

from .config import load_config
from .models import ImageData, AnalysisResult, ProviderConfig
from .providers.base import BaseProvider
from .providers.openai_provider import OpenAIProvider
from .providers.google_provider import GoogleProvider
from .providers.anthropic_provider import AnthropicProvider
from .handlers.router import URLRouter, create_router
from .analysis.prompts import build_image_prompt, build_url_prompt
from .analysis.scenario import detect_scenario_and_build_result

logger = logging.getLogger(__name__)

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "openai": OpenAIProvider,
    "google": GoogleProvider,
    "anthropic": AnthropicProvider,
}


def _create_providers(configs: list[ProviderConfig]) -> list[BaseProvider]:
    providers: list[BaseProvider] = []
    for cfg in configs:
        cls = PROVIDER_REGISTRY.get(cfg.type)
        if cls is None:
            logger.warning("Unknown provider type: %s, skipping", cfg.type)
            continue
        provider = cls(cfg)
        if provider.available:
            providers.append(provider)
        else:
            logger.info(
                "Provider %s not available (API key env %s not set)",
                cfg.type,
                cfg.api_key_env,
            )
    return providers


def _get_default_provider(providers: list[BaseProvider], configs: list[ProviderConfig]) -> BaseProvider | None:
    for cfg in configs:
        if cfg.default:
            for p in providers:
                if p.config.type == cfg.type:
                    return p
    return providers[0] if providers else None


async def _resolve_image(image_input: str) -> ImageData:
    if image_input.startswith("data:"):
        parts = image_input.split(",", 1)
        mime = "image/png"
        if ";" in parts[0]:
            mime_part = parts[0].split(";")[0]
            mime = mime_part.split(":")[1] if ":" in mime_part else mime
        return ImageData(data=parts[1], mime_type=mime, source="base64_data_uri")

    if image_input.startswith("http://") or image_input.startswith("https://"):
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(image_input)
            resp.raise_for_status()
        if len(resp.content) > 10 * 1024 * 1024:
            raise ValueError(f"Image too large: {len(resp.content) / 1024 / 1024:.1f}MB (limit 10MB)")
        mime = resp.headers.get("content-type", "image/png")
        b64 = base64.b64encode(resp.content).decode()
        return ImageData(data=b64, mime_type=mime, source=image_input)

    path = Path(image_input).expanduser()
    if path.exists():
        file_size = path.stat().st_size
        if file_size > 10 * 1024 * 1024:
            raise ValueError(f"Image too large: {file_size / 1024 / 1024:.1f}MB (limit 10MB)")
        mime, _ = mimetypes.guess_type(str(path))
        if not mime:
            mime = "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode()
        return ImageData(data=b64, mime_type=mime, source=str(path))

    try:
        base64.b64decode(image_input, validate=True)
        return ImageData(data=image_input, mime_type="image/png", source="base64_raw")
    except Exception:
        raise ValueError(f"Cannot resolve image input: {image_input[:100]}")


def _format_result(result: AnalysisResult) -> str:
    output = {
        "scenario": result.scenario,
        "summary": result.summary,
        "details": result.details,
    }
    if result.raw_content:
        output["source"] = {
            "url": result.raw_content.url,
            "type": result.raw_content.source_type,
            "title": result.raw_content.title,
        }
        if result.raw_content.attachments:
            output["attachments"] = [
                {
                    "name": att.name,
                    "extension": att.extension,
                    "size": att.size,
                    "download_url": att.url,
                }
                for att in result.raw_content.attachments
            ]
    return json.dumps(output, ensure_ascii=False, indent=2)


_config: AppConfig | None = None
_providers: list[BaseProvider] | None = None
_default_provider: BaseProvider | None = None
_router: URLRouter | None = None


def _ensure_initialized() -> None:
    global _config, _providers, _default_provider, _router
    if _config is not None:
        return
    _config = load_config()
    _providers = _create_providers(_config.providers)
    _default_provider = _get_default_provider(_providers, _config.providers)
    _router = create_router(_config.handlers)


mcp = FastMCP("life-saver-mcp")


@mcp.tool(name="analyze_image", title="Image Analyzer")
async def analyze_image(image: str, hint: str | None = None) -> str:
    _ensure_initialized()
    """分析图片内容，自动识别场景（UI原型/Bug截图/需求文档/通用图片），支持本地路径、base64、图片URL"""
    if not _default_provider:
        return json.dumps({"error": "No AI provider available. Please configure API key."}, ensure_ascii=False)

    try:
        image_data = await _resolve_image(image)
    except Exception as e:
        return f"Error loading image: {e}"

    prompt = build_image_prompt(hint)
    try:
        raw = await _default_provider.analyze_image(image_data, prompt)
        result = detect_scenario_and_build_result(raw)
        return _format_result(result)
    except Exception as e:
        logger.exception("analyze_image failed")
        return f"Analysis error: {e}"


@mcp.tool(name="analyze_url", title="URL Content Analyzer")
async def analyze_url(url: str, hint: str | None = None) -> str:
    _ensure_initialized()
    """分析网页URL内容，自动识别来源（蓝湖/禅道/通用网页），拉取文字和图片后AI整理输出"""
    handler = _router.route(url)
    try:
        page_content = await handler.fetch_content(url)
    except Exception as e:
        logger.exception("fetch_content failed")
        return f"Error fetching URL: {e}"

    if not _default_provider:
        output = {
            "scenario": "raw_fetch",
            "summary": page_content.title,
            "details": {"text_sections": page_content.text_sections},
        }
        output["source"] = {
            "url": page_content.url,
            "type": page_content.source_type,
            "title": page_content.title,
        }
        output["images_fetched"] = len(page_content.images)
        if page_content.attachments:
            output["attachments"] = [
                {"name": a.name, "extension": a.extension, "size": a.size, "download_url": a.url}
                for a in page_content.attachments
            ]
        return json.dumps(output, ensure_ascii=False, indent=2)

    prompt = build_url_prompt(page_content.source_type, page_content.title, hint)

    try:
        if page_content.images:
            combined_text = "\n\n".join(page_content.text_sections)
            raw = await _default_provider.analyze_multimodal(
                page_content.images[:5], combined_text, prompt
            )
        else:
            combined_text = "\n\n".join(page_content.text_sections)
            raw = await _default_provider.analyze_text(combined_text, prompt)

        result = detect_scenario_and_build_result(raw, raw_content=page_content)
        return _format_result(result)
    except Exception as e:
        logger.exception("analyze_url failed")
        return f"Analysis error: {e}"


def main() -> None:
    import click

    @click.command()
    @click.option("--port", default=8000, help="Port to listen on for HTTP transport")
    @click.option(
        "--transport",
        type=click.Choice(["stdio", "streamable-http", "sse"]),
        default="stdio",
        help="Transport type: stdio, streamable-http, or sse",
    )
    @click.option("--config", "config_path", default=None, help="Path to config file (life-saver-mcp.json)")
    def _main(port: int, transport: str, config_path: str | None) -> None:
        if config_path:
            os.environ["LIFE_SAVER_CONFIG"] = config_path

        _ensure_initialized()
        logging.basicConfig(level=logging.INFO)

        if transport in ("streamable-http", "sse"):
            mcp.settings.host = "127.0.0.1"
            mcp.settings.port = port

        mcp.run(transport=transport)

    _main()


if __name__ == "__main__":
    main()
