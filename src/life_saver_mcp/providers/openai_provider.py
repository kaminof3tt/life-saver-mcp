from __future__ import annotations

from openai import AsyncOpenAI

from .base import BaseProvider
from ..models import ImageData, ProviderConfig


class OpenAIProvider(BaseProvider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            kwargs: dict = {"api_key": self.api_key}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def _build_image_content(self, image: ImageData) -> dict:
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{image.mime_type};base64,{image.data}"},
        }

    async def analyze_image(self, image: ImageData, prompt: str) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    self._build_image_content(image),
                ],
            }
        ]
        resp = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=4096,
        )
        return resp.choices[0].message.content or ""

    async def analyze_text(self, text: str, prompt: str) -> str:
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ]
        resp = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=4096,
        )
        return resp.choices[0].message.content or ""

    async def analyze_multimodal(
        self, images: list[ImageData], text: str, prompt: str
    ) -> str:
        content: list[dict] = [{"type": "text", "text": prompt}]
        if text:
            content.append({"type": "text", "text": text})
        for img in images:
            content.append(self._build_image_content(img))

        messages = [{"role": "user", "content": content}]
        resp = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=4096,
        )
        return resp.choices[0].message.content or ""
