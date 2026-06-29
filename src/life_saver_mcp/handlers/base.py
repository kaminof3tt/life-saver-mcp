from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import PageContent


class BaseHandler(ABC):
    @abstractmethod
    def can_handle(self, url: str) -> bool: ...

    @abstractmethod
    async def fetch_content(self, url: str) -> PageContent: ...
