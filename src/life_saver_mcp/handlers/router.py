from __future__ import annotations

import logging

from .base import BaseHandler
from .generic import GenericHandler
from .lanhu import LanhuHandler
from .zentao import ZentaoHandler
from ..models import HandlerConfig

logger = logging.getLogger(__name__)


class URLRouter:
    def __init__(self, handlers: list[BaseHandler] | None = None) -> None:
        self.handlers: list[BaseHandler] = handlers or []
        self._default = GenericHandler()

    def register(self, handler: BaseHandler) -> None:
        self.handlers.append(handler)

    def route(self, url: str) -> BaseHandler:
        for handler in self.handlers:
            if handler.can_handle(url):
                logger.info("URL %s matched handler: %s", url, type(handler).__name__)
                return handler
        logger.info("URL %s using default GenericHandler", url)
        return self._default


def create_router(handler_configs: dict[str, HandlerConfig] | None = None) -> URLRouter:
    configs = handler_configs or {}
    router = URLRouter()

    lanhu_cfg = configs.get("lanhu")
    if lanhu_cfg and lanhu_cfg.enabled:
        router.register(LanhuHandler(config=lanhu_cfg))

    zentao_cfg = configs.get("zentao")
    if zentao_cfg and zentao_cfg.enabled:
        router.register(ZentaoHandler(config=zentao_cfg))

    return router
