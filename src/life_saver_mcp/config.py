from __future__ import annotations

import json
import os
from pathlib import Path

from .models import AppConfig, ProviderConfig, HandlerConfig, HandlerAuthConfig

_DEFAULT_CONFIG_PATHS = [
    "life-saver-mcp.json",
    "~/.config/life-saver-mcp/config.json",
]


def load_config(config_path: str | None = None) -> AppConfig:
    env_path = os.environ.get("LIFE_SAVER_CONFIG")
    if config_path:
        path = Path(config_path).expanduser()
        if path.exists():
            return _parse_config(path)
    elif env_path:
        path = Path(env_path).expanduser()
        if path.exists():
            return _parse_config(path)

    for candidate in _DEFAULT_CONFIG_PATHS:
        path = Path(candidate).expanduser()
        if path.exists():
            return _parse_config(path)

    return _default_config()


def _parse_config(path: Path) -> AppConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    providers = []
    for p in raw.get("providers", []):
        providers.append(ProviderConfig(**p))

    handlers = {}
    for name, h in raw.get("handlers", {}).items():
        auth = h.get("auth")
        handlers[name] = HandlerConfig(
            enabled=h.get("enabled", False),
            url=h.get("url", ""),
            auth=HandlerAuthConfig(**auth) if auth else None,
        )

    return AppConfig(providers=providers, handlers=handlers)


def _default_config() -> AppConfig:
    providers = [
        ProviderConfig(
            type="openai",
            api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            models=["gpt-4o"],
            default=True,
        ),
    ]
    handlers = {
        "lanhu": HandlerConfig(enabled=False, auth=HandlerAuthConfig(type="cookie", env="LANHU_COOKIE")),
        "zentao": HandlerConfig(enabled=False, url="", auth=HandlerAuthConfig(type="cookie", env="ZENTAO_COOKIE")),
    }
    return AppConfig(providers=providers, handlers=handlers)
