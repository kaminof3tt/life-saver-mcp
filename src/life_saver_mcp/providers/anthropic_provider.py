from __future__ import annotations

from anthropic import AsyncAnthropic

from .base import BaseProvider
from ..models import ImageData, ProviderConfig


class AnthropicProvider(BaseProvider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client: AsyncAnthropic | None = None

    @property
    def client(self) -> AsyncAnthropic:
        if self._client is None:
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    def _build_image_block(self, image: ImageData) -> dict:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.mime_type,
                "data": image.data,
            },
        }

    async def analyze_image(self, image: ImageData, prompt: str) -> str:
        resp = await self.client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        self._build_image_block(image),
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return resp.content[0].text if resp.content else ""

    async def analyze_text(self, text: str, prompt: str) -> str:
        resp = await self.client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            system=prompt,
            messages=[{"role": "user", "content": text}],
        )
        return resp.content[0].text if resp.content else ""

    async def analyze_multimodal(
        self, images: list[ImageData], text: str, prompt: str
    ) -> str:
        content: list[dict] = []
        for img in images:
            content.append(self._build_image_block(img))
        if text:
            content.append({"type": "text", "text": text})
        content.append({"type": "text", "text": prompt})

        resp = await self.client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
        )
        return resp.content[0].text if resp.content else ""
