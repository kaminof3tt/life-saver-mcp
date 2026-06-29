"""Tests for life-saver-mcp"""
import asyncio
import json
import os
import pytest

from life_saver_mcp.models import (
    ImageData, PageContent, AnalysisResult, AppConfig, ProviderConfig, HandlerConfig, HandlerAuthConfig
)
from life_saver_mcp.config import load_config, _parse_config, _default_config
from life_saver_mcp.handlers.zentao import ZentaoHandler
from life_saver_mcp.handlers.lanhu import LanhuHandler, LanhuClient
from life_saver_mcp.handlers.router import create_router, URLRouter
from life_saver_mcp.handlers.generic import GenericHandler
from life_saver_mcp.analysis.prompts import build_image_prompt, build_url_prompt, parse_analysis_response
from life_saver_mcp.analysis.scenario import detect_scenario_and_build_result


# ── Models ──

class TestModels:
    def test_image_data_defaults(self):
        img = ImageData(data="abc123")
        assert img.mime_type == "image/png"
        assert img.source == ""

    def test_page_content(self):
        pc = PageContent(url="http://example.com", title="Test")
        assert pc.source_type == "generic"
        assert pc.text_sections == []
        assert pc.images == []

    def test_analysis_result(self):
        ar = AnalysisResult(scenario="bug_screenshot", summary="crash")
        assert ar.details == {}
        assert ar.raw_content is None

    def test_app_config(self):
        cfg = AppConfig(
            providers=[ProviderConfig(type="openai", api_key_env="KEY", default=True)],
            handlers={"zentao": HandlerConfig(enabled=True, url="http://zt.com", auth=HandlerAuthConfig(type="cookie", env="ZT_COOKIE"))}
        )
        assert cfg.providers[0].type == "openai"
        assert cfg.handlers["zentao"].url == "http://zt.com"


# ── Config ──

class TestConfig:
    def test_default_config(self):
        cfg = _default_config()
        assert len(cfg.providers) >= 1
        assert cfg.providers[0].type == "openai"
        assert "lanhu" in cfg.handlers
        assert "zentao" in cfg.handlers
        assert cfg.handlers["zentao"].auth.type == "cookie"

    def test_parse_config(self, tmp_path):
        cfg_file = tmp_path / "test.json"
        cfg_file.write_text(json.dumps({
            "providers": [{"type": "openai", "api_key_env": "MY_KEY", "models": ["gpt-4o"], "default": True}],
            "handlers": {"zentao": {"enabled": True, "url": "http://zt.local", "auth": {"type": "cookie", "env": "ZT_CK"}}}
        }), encoding="utf-8")
        cfg = _parse_config(cfg_file)
        assert cfg.providers[0].api_key_env == "MY_KEY"
        assert cfg.handlers["zentao"].enabled is True
        assert cfg.handlers["zentao"].url == "http://zt.local"

    def test_load_config_env(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "custom.json"
        cfg_file.write_text(json.dumps({
            "providers": [{"type": "google", "api_key_env": "G_KEY", "default": True}],
            "handlers": {}
        }), encoding="utf-8")
        monkeypatch.setenv("LIFE_SAVER_CONFIG", str(cfg_file))
        cfg = load_config()
        assert cfg.providers[0].type == "google"


# ── Zentao URL Parsing ──

class TestZentaoURLParsing:
    def test_bug_get_params(self):
        result = ZentaoHandler.parse_url_params("http://zentao.example.com/index.php?m=bug&f=view&bugID=1081")
        assert result == {"type": "bug", "id": "1081"}

    def test_story_get_params(self):
        result = ZentaoHandler.parse_url_params("http://zentao.example.com/index.php?m=story&f=view&id=572")
        assert result == {"type": "story", "id": "572"}

    def test_task_get_params(self):
        result = ZentaoHandler.parse_url_params("http://zentao.example.com/index.php?m=task&f=view&taskID=314")
        assert result == {"type": "task", "id": "314"}

    def test_requirement_get_params(self):
        result = ZentaoHandler.parse_url_params("http://zentao.example.com/index.php?m=requirement&f=view&storyID=495&version=0&param=0&storyType=story")
        assert result == {"type": "requirement", "id": "495"}

    def test_projectstory_get_params(self):
        result = ZentaoHandler.parse_url_params("http://zentao.example.com/index.php?m=projectstory&f=view&storyID=523&projectID=98")
        assert result == {"type": "projectstory", "id": "523"}

    def test_path_info_format(self):
        result = ZentaoHandler.parse_url_params("http://zentao.example.com/bug-view-1081.html")
        assert result == {"type": "bug", "id": "1081"}

    def test_story_path_info(self):
        result = ZentaoHandler.parse_url_params("http://zentao.example.com/story-view-572.html")
        assert result == {"type": "story", "id": "572"}

    def test_task_path_info(self):
        result = ZentaoHandler.parse_url_params("http://zentao.example.com/task-view-314.html")
        assert result == {"type": "task", "id": "314"}

    def test_no_match(self):
        result = ZentaoHandler.parse_url_params("http://example.com/something")
        assert result is None


# ── Zentao Domain Matching ──

class TestZentaoDomainMatching:
    def test_match_config_domain(self):
        cfg = HandlerConfig(enabled=True, url="http://zentao.example.com", auth=HandlerAuthConfig(type="cookie", env="ZT"))
        h = ZentaoHandler(config=cfg)
        assert h.can_handle("http://zentao.example.com/index.php?m=bug&f=view&bugID=1081") is True

    def test_no_match_different_domain(self):
        cfg = HandlerConfig(enabled=True, url="http://zentao.example.com", auth=HandlerAuthConfig(type="cookie", env="ZT"))
        h = ZentaoHandler(config=cfg)
        assert h.can_handle("http://other-zentao.com/index.php?m=bug&f=view&bugID=1081") is False

    def test_no_match_lanhu(self):
        cfg = HandlerConfig(enabled=True, url="http://zentao.example.com", auth=HandlerAuthConfig(type="cookie", env="ZT"))
        h = ZentaoHandler(config=cfg)
        assert h.can_handle("https://lanhuapp.com/web/#/item") is False


# ── Lanhu Domain Matching ──

class TestLanhuDomainMatching:
    def test_match_lanhuapp(self):
        h = LanhuHandler()
        assert h.can_handle("https://lanhuapp.com/web/#/item/project/product?tid=1&pid=2") is True

    def test_match_lanhu(self):
        h = LanhuHandler()
        assert h.can_handle("https://lanhu.com/web/#/item") is True

    def test_no_match_other(self):
        h = LanhuHandler()
        assert h.can_handle("https://example.com/page") is False


# ── Lanhu URL Parsing ──

class TestLanhuURLParsing:
    def test_full_url_with_tid_pid(self):
        result = LanhuClient.parse_url("https://lanhuapp.com/web/#/item/project/product?tid=123&pid=456")
        assert result["team_id"] == "123"
        assert result["project_id"] == "456"
        assert result["doc_id"] is None

    def test_url_with_docid(self):
        result = LanhuClient.parse_url("https://lanhuapp.com/web/#/item/project/product?tid=1&pid=2&docId=3")
        assert result["doc_id"] == "3"

    def test_url_without_tid(self):
        result = LanhuClient.parse_url("https://lanhuapp.com/web/#/item/project/detailDetach?pid=2&image_id=3")
        assert result["team_id"] is None
        assert result["project_id"] == "2"
        assert result["doc_id"] == "3"

    def test_missing_pid_raises(self):
        with pytest.raises(ValueError, match="missing required param pid"):
            LanhuClient.parse_url("https://lanhuapp.com/web/#/item/project/product?tid=1")


# ── Router ──

class TestRouter:
    def test_generic_fallback(self):
        router = create_router({"lanhu": HandlerConfig(enabled=False), "zentao": HandlerConfig(enabled=False, url="http://zt.com")})
        handler = router.route("https://example.com/page")
        assert isinstance(handler, GenericHandler)

    def test_lanhu_enabled(self):
        router = create_router({"lanhu": HandlerConfig(enabled=True), "zentao": HandlerConfig(enabled=False, url="http://zt.com")})
        handler = router.route("https://lanhuapp.com/web/#/item/project/product?tid=1&pid=2")
        assert isinstance(handler, LanhuHandler)

    def test_zentao_enabled(self):
        router = create_router({
            "lanhu": HandlerConfig(enabled=False),
            "zentao": HandlerConfig(enabled=True, url="http://zentao.example.com", auth=HandlerAuthConfig(type="cookie", env="ZT"))
        })
        handler = router.route("http://zentao.example.com/index.php?m=bug&f=view&bugID=1081")
        assert isinstance(handler, ZentaoHandler)


# ── Analysis ──

class TestAnalysis:
    def test_parse_analysis_response_valid_json(self):
        raw = '{"scenario": "ui_mockup", "summary": "login page", "details": {"components": ["button"]}}'
        result = parse_analysis_response(raw)
        assert result["scenario"] == "ui_mockup"
        assert result["summary"] == "login page"

    def test_parse_analysis_response_with_markdown(self):
        raw = '```json\n{"scenario": "general", "summary": "test", "details": {}}\n```'
        result = parse_analysis_response(raw)
        assert result["scenario"] == "general"

    def test_parse_analysis_response_fallback(self):
        raw = "This is just plain text that is not JSON"
        result = parse_analysis_response(raw)
        assert result["scenario"] == "general"

    def test_build_image_prompt(self):
        prompt = build_image_prompt("focus on buttons")
        assert "focus on buttons" in prompt
        assert "ui_mockup" in prompt

    def test_build_url_prompt(self):
        prompt = build_url_prompt("zentao_bug", "Bug #1", "check severity")
        assert "zentao_bug" in prompt
        assert "Bug #1" in prompt
        assert "check severity" in prompt

    def test_detect_scenario(self):
        raw = '{"scenario": "bug_screenshot", "summary": "crash", "details": {"error": "null pointer"}}'
        result = detect_scenario_and_build_result(raw)
        assert result.scenario == "bug_screenshot"
        assert result.summary == "crash"


# ── Zentao HTML Parsing ──

class TestZentaoHTMLParsing:
    def test_extract_detail_fields(self):
        from bs4 import BeautifulSoup
        html = '''
        <div class="datalist-item">
            <div class="datalist-item-label">Bug Type</div>
            <div class="datalist-item-content">Code Error</div>
        </div>
        <div class="datalist-item">
            <div class="datalist-item-label">Priority</div>
            <div class="datalist-item-content"><span class="pri-1">1</span></div>
        </div>
        '''
        h = ZentaoHandler()
        soup = BeautifulSoup(html, "html.parser")
        fields = h._extract_detail_fields(soup)
        assert fields["Bug Type"] == "Code Error"
        assert "1" in fields["Priority"]

    def test_extract_article_content(self):
        from bs4 import BeautifulSoup
        html = '<div class="article"><p>Step 1</p><p>Result 2</p></div>'
        h = ZentaoHandler()
        soup = BeautifulSoup(html, "html.parser")
        sections = h._extract_article_content(soup)
        assert len(sections) == 1
        assert "Step 1" in sections[0]

    def test_extract_images(self):
        from bs4 import BeautifulSoup
        html = '<img src="/index.php?m=file&f=read&t=png&fileID=4787" />'
        h = ZentaoHandler()
        soup = BeautifulSoup(html, "html.parser")
        urls = h._extract_images(soup)
        assert len(urls) == 1
        assert "fileID=4787" in urls[0]

    def test_extract_images_dedup(self):
        from bs4 import BeautifulSoup
        html = '<img src="/index.php?m=file&f=read&t=png&fileID=4787" /><img src="/index.php?m=file&f=read&t=png&fileID=4787" />'
        h = ZentaoHandler()
        soup = BeautifulSoup(html, "html.parser")
        urls = h._extract_images(soup)
        assert len(urls) == 1

    def test_extract_images_from_zui_create_attr(self):
        from bs4 import BeautifulSoup
        html = """<div zui-create zui-create-historyPanel='{"actions":[{"comment":"<img src=\\"/index.php?m=file&amp;f=read&amp;t=png&amp;fileID=4916\\" />"}]}'></div>"""
        h = ZentaoHandler()
        soup = BeautifulSoup(html, "html.parser")
        urls = h._extract_images(soup)
        assert len(urls) == 1
        assert "fileID=4916" in urls[0]

    def test_extract_images_both_dom_and_json(self):
        from bs4 import BeautifulSoup
        html = """<img src="/index.php?m=file&f=read&t=png&fileID=4787" /><div zui-create zui-create-historyPanel='{"actions":[{"comment":"<img src=\\"/index.php?m=file&amp;f=read&amp;t=png&amp;fileID=4916\\" />"}]}'></div>"""
        h = ZentaoHandler()
        soup = BeautifulSoup(html, "html.parser")
        urls = h._extract_images(soup)
        assert len(urls) == 2

    def test_no_images_without_fileid(self):
        from bs4 import BeautifulSoup
        html = '<img src="https://cdn.example.com/logo.png" />'
        h = ZentaoHandler()
        soup = BeautifulSoup(html, "html.parser")
        urls = h._extract_images(soup)
        assert len(urls) == 0

    def test_extract_history_from_zui_create(self):
        from bs4 import BeautifulSoup
        html = """<div zui-create zui-create-historyPanel='{"actions":[{"content":"2026-06-18 11:51:41, created by Zhu"},{"comment":"<p>new user is dept account</p>","historyChanges":"changed assignee"}]}'></div>"""
        h = ZentaoHandler()
        soup = BeautifulSoup(html, "html.parser")
        comments = h._extract_history_comments(soup)
        texts = " ".join(comments)
        assert "Zhu" in texts
        assert "dept account" in texts
