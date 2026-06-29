from __future__ import annotations

from pydantic import BaseModel


class ImageData(BaseModel):
    data: str
    mime_type: str = "image/png"
    source: str = ""


class AttachmentInfo(BaseModel):
    file_id: str = ""
    name: str = ""
    url: str = ""
    extension: str = ""
    size: str = ""


class PageContent(BaseModel):
    url: str
    title: str = ""
    text_sections: list[str] = []
    images: list[ImageData] = []
    attachments: list[AttachmentInfo] = []
    metadata: dict = {}
    source_type: str = "generic"


class AnalysisResult(BaseModel):
    scenario: str = "general"
    summary: str = ""
    details: dict = {}
    raw_content: PageContent | None = None


class ProviderConfig(BaseModel):
    type: str
    api_key_env: str = ""
    base_url: str = ""
    models: list[str] = []
    default: bool = False


class HandlerAuthConfig(BaseModel):
    type: str = "token"
    env: str = ""


class HandlerConfig(BaseModel):
    enabled: bool = False
    url: str = ""
    auth: HandlerAuthConfig | None = None


class AppConfig(BaseModel):
    providers: list[ProviderConfig] = []
    handlers: dict[str, HandlerConfig] = {}
