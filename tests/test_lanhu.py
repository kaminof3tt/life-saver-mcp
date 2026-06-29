"""Tests for Lanhu modules."""
import json
import pytest

from life_saver_mcp.handlers.lanhu import LanhuClient, LanhuHandler
from life_saver_mcp.handlers.lanhu_annotations import extract_annotations, extract_design_tokens
from life_saver_mcp.handlers.lanhu_slices import extract_slices
from life_saver_mcp.models import HandlerConfig, HandlerAuthConfig


# ── LanhuClient URL Parsing ──

class TestLanhuURLParsing:
    def test_full_url_with_tid_pid(self):
        result = LanhuClient.parse_url("https://lanhuapp.com/web/#/item/project/product?tid=123&pid=456")
        assert result["team_id"] == "123"
        assert result["project_id"] == "456"
        assert result["doc_id"] is None

    def test_url_with_docid(self):
        result = LanhuClient.parse_url("https://lanhuapp.com/web/#/item/project/product?tid=1&pid=2&docId=3")
        assert result["doc_id"] == "3"

    def test_url_with_image_id(self):
        result = LanhuClient.parse_url("https://lanhuapp.com/web/#/item/project/detailDetach?pid=2&image_id=3")
        assert result["doc_id"] == "3"

    def test_url_without_tid(self):
        result = LanhuClient.parse_url("https://lanhuapp.com/web/#/item/project/detailDetach?pid=2&image_id=3")
        assert result["team_id"] is None
        assert result["project_id"] == "2"

    def test_missing_pid_raises(self):
        with pytest.raises(ValueError, match="missing required param pid"):
            LanhuClient.parse_url("https://lanhuapp.com/web/#/item/project/product?tid=1")

    def test_params_only(self):
        result = LanhuClient.parse_url("?tid=1&pid=2&docId=3")
        assert result["team_id"] == "1"
        assert result["project_id"] == "2"
        assert result["doc_id"] == "3"


# ── Lanhu Domain Matching ──

class TestLanhuDomainMatching:
    def test_match_lanhuapp(self):
        h = LanhuHandler()
        assert h.can_handle("https://lanhuapp.com/web/#/item") is True

    def test_match_lanhu(self):
        h = LanhuHandler()
        assert h.can_handle("https://lanhu.com/page") is True

    def test_match_lhcdn(self):
        h = LanhuHandler()
        assert h.can_handle("https://cdn.lhcdn.com/image.png") is True

    def test_no_match_other(self):
        h = LanhuHandler()
        assert h.can_handle("https://example.com/page") is False


# ── Annotations ──

class TestAnnotations:
    def test_extract_annotations_empty(self):
        result = extract_annotations({})
        assert "Design Annotations" in result

    def test_extract_annotations_with_text_layer(self):
        sketch_data = {
            "psdName": "Test Design",
            "device": "iPhone",
            "board": {
                "width": 750,
                "height": 1334,
                "fill": {"color": {"red": 255, "green": 255, "blue": 255}},
                "layers": [
                    {
                        "name": "Title",
                        "type": "textLayer",
                        "width": 200,
                        "height": 30,
                        "left": 10,
                        "top": 20,
                        "textInfo": {
                            "text": "Hello World",
                            "color": {"red": 0, "green": 0, "blue": 0},
                            "size": 24,
                            "fontPostScriptName": "PingFang SC",
                        },
                    }
                ],
            },
        }
        result = extract_annotations(sketch_data, design_scale=2.0)
        assert "Hello World" in result
        assert "PingFang SC" in result

    def test_extract_annotations_with_shape_layer(self):
        sketch_data = {
            "board": {
                "width": 375,
                "height": 667,
                "layers": [
                    {
                        "name": "Button",
                        "type": "shapeLayer",
                        "width": 100,
                        "height": 40,
                        "left": 50,
                        "top": 100,
                        "fill": {"color": {"red": 0, "green": 122, "blue": 255}},
                    }
                ],
            },
        }
        result = extract_annotations(sketch_data)
        assert "Button" in result
        assert "100x40" in result or "50.0x20.0" in result

    def test_extract_design_tokens_empty(self):
        result = extract_design_tokens({})
        assert result == ""

    def test_extract_design_tokens_with_gradient(self):
        sketch_data = {
            "artboard": {
                "layers": [
                    {
                        "name": "Gradient BG",
                        "type": "shapeLayer",
                        "isVisible": True,
                        "left": 0, "top": 0, "width": 375, "height": 100,
                        "fills": [
                            {
                                "isEnabled": True,
                                "fillType": 1,
                                "gradient": {
                                    "from": {"x": 0.5, "y": 0},
                                    "to": {"x": 0.5, "y": 1},
                                    "colorStops": [
                                        {"color": {"value": "#FF0000"}, "position": 0},
                                        {"color": {"value": "#0000FF"}, "position": 1},
                                    ],
                                },
                            }
                        ],
                    }
                ],
            },
        }
        result = extract_design_tokens(sketch_data)
        assert "Gradient BG" in result
        assert "linear-gradient" in result


# ── Slices ──

class TestSlices:
    def test_extract_slices_empty(self):
        result = extract_slices({})
        assert result == []

    def test_extract_slices_figma_bitmap(self):
        sketch_data = {
            "meta": {"host": {"name": "figma"}},
            "artboard": {
                "layers": [
                    {
                        "name": "Icon",
                        "image": {
                            "imageUrl": "https://example.com/icon.png",
                            "size": {"width": 24, "height": 24},
                        },
                        "hasExportImage": True,
                    }
                ],
            },
        }
        result = extract_slices(sketch_data)
        assert len(result) == 1
        assert result[0]["name"] == "Icon"
        assert result[0]["download_url"] == "https://example.com/icon.png"
        assert result[0]["logical_width"] == 24
        assert "2x" in result[0]["scale_urls"]

    def test_extract_slices_figma_image_fill_skipped(self):
        sketch_data = {
            "meta": {"host": {"name": "figma"}},
            "artboard": {
                "layers": [
                    {
                        "name": "BG Image",
                        "image": {"imageUrl": "https://example.com/bg.png"},
                        "hasExportImage": False,
                    }
                ],
            },
        }
        result = extract_slices(sketch_data)
        assert len(result) == 0

    def test_extract_slices_old_sketch(self):
        sketch_data = {
            "info": [
                {
                    "name": "Logo",
                    "ddsImage": {
                        "imageUrl": "https://example.com/logo.png",
                        "size": {"width": 100, "height": 50},
                    },
                }
            ],
        }
        result = extract_slices(sketch_data)
        assert len(result) == 1
        assert result[0]["name"] == "Logo"
        assert result[0]["format"] == "png"

    def test_scale_urls_generation(self):
        sketch_data = {
            "meta": {},
            "sliceScale": 2,
            "info": [
                {
                    "name": "Button",
                    "image": {
                        "imageUrl": "https://oss.example.com/btn.png",
                        "size": {"width": 80, "height": 40},
                    },
                }
            ],
        }
        result = extract_slices(sketch_data)
        assert len(result) == 1
        urls = result[0]["scale_urls"]
        assert "1x" in urls
        assert "2x" in urls
        assert "3x" in urls
        assert "ios_2x" in urls
        assert "android_xxhdpi" in urls
