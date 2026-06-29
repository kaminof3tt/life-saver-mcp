from __future__ import annotations

import base64

from google import genai
from google.genai import types as genai_types

from .base import BaseProvider
from ..models import ImageData, ProviderConfig


class GoogleProvider(BaseProvider):
    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client: genai.Client | None = None

    @property
    def genai_client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def analyze_image(self, image: ImageData, prompt: str) -> str:
        resp = await self.genai_client.aio.models.generate_content(
            model=self.model_name,
            contents=[
                genai_types.Part.from_bytes(data=base64.b64decode(image.data), mime_type=image.mime_type),
                prompt,
            ],
        )
        return resp.text or ""

    async def analyze_text(self, text: str, prompt: str) -> str:
        resp = await self.genai_client.aio.models.generate_content(
            model=self.model_name,
            contents=f"{prompt}\n\n{text}",
        )
        return resp.text or ""

    async def analyze_multimodal(
        self, images: list[ImageData], text: str, prompt: str
    ) -> str:
        parts: list = []
        parts.append(genai_types.Part.from_text(text=prompt))
        if text:
            parts.append(genai_types.Part.from_text(text=text))
        for img in images:
            parts.append(
                genai_types.Part.from_bytes(
                    data=base64.b64decode(img.data),
                    mime_type=img.mime_type,
                )
            )

        resp = await self.genai_client.aio.models.generate_content(
            model=self.model_name,
            contents=parts,
        )
        return resp.text or ""
