from __future__ import annotations

import os
from abc import ABC, abstractmethod

from ..models import ImageData, ProviderConfig


class BaseProvider(ABC):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.api_key = os.environ.get(config.api_key_env, "")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def model_name(self) -> str:
        return self.config.models[0] if self.config.models else ""

    @abstractmethod
    async def analyze_image(self, image: ImageData, prompt: str) -> str: ...

    @abstractmethod
    async def analyze_text(self, text: str, prompt: str) -> str: ...

    @abstractmethod
    async def analyze_multimodal(
        self, images: list[ImageData], text: str, prompt: str
    ) -> str: ...
