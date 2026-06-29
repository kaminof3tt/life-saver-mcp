from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def extract_slices(sketch_data: dict) -> list[dict]:
    meta = sketch_data.get("meta") or {}
    slice_scale = int(
        sketch_data.get("sliceScale")
        or sketch_data.get("exportScale")
        or meta.get("sliceScale")
        or 2
    )
    is_figma = (meta.get("host") or {}).get("name") == "figma"

    slices: list[dict] = []

    def _build_scale_urls(image_url: str, logical_w: float, logical_h: float) -> dict:
        if not image_url or not logical_w or not logical_h:
            return {}
        lw = max(1, int(round(logical_w)))
        lh = max(1, int(round(logical_h)))
        stored_w = lw * slice_scale
        stored_h = lh * slice_scale

        def make_url(w: int, h: int) -> str:
            w, h = max(1, w), max(1, h)
            if w == stored_w and h == stored_h:
                return image_url
            return f"{image_url}?x-oss-process=image/resize,w_{w},h_{h}/format,png"

        def js_round(v: float) -> int:
            return math.floor(v + 0.5)

        ios_base = stored_w / 4
        return {
            "1x": make_url(lw, lh),
            "2x": make_url(lw * 2, lh * 2),
            "3x": make_url(lw * 3, lh * 3),
            "ios_1x": make_url(max(1, js_round(ios_base)), max(1, js_round(stored_h / 4))),
            "ios_2x": make_url(max(1, js_round(ios_base * 2)), max(1, js_round(stored_h / 4 * 2))),
            "ios_3x": make_url(max(1, js_round(ios_base * 3)), max(1, js_round(stored_h / 4 * 3))),
            "android_mdpi": make_url(max(1, js_round(stored_w / 4)), max(1, js_round(stored_h / 4))),
            "android_hdpi": make_url(max(1, js_round(stored_w / 4 * 1.5)), max(1, js_round(stored_h / 4 * 1.5))),
            "android_xhdpi": make_url(max(1, js_round(stored_w / 4 * 2)), max(1, js_round(stored_h / 4 * 2))),
            "android_xxhdpi": make_url(max(1, js_round(stored_w / 4 * 3)), max(1, js_round(stored_h / 4 * 3))),
            "android_xxxhdpi": make_url(stored_w, stored_h),
        }

    def _walk(obj: dict, parent_name: str = "", layer_path: str = ""):
        if not obj or not isinstance(obj, dict):
            return
        current_name = obj.get("name", "")
        current_path = f"{layer_path}/{current_name}" if layer_path else current_name

        if obj.get("image") and (obj["image"].get("imageUrl") or obj["image"].get("svgUrl")):
            if is_figma and not obj.get("hasExportImage"):
                pass
            else:
                image_data = obj["image"]
                download_url = image_data.get("imageUrl") or image_data.get("svgUrl")
                img_size = image_data.get("size") or {}
                logical_w = img_size.get("width") or 0
                logical_h = img_size.get("height") or 0
                slices.append({
                    "name": current_name,
                    "path": current_path,
                    "download_url": download_url,
                    "format": "svg" if image_data.get("svgUrl") else "png",
                    "logical_width": logical_w,
                    "logical_height": logical_h,
                    "scale": slice_scale,
                    "scale_urls": _build_scale_urls(download_url, logical_w, logical_h),
                })

        elif obj.get("ddsImage") and obj["ddsImage"].get("imageUrl") and not is_figma:
            dds = obj["ddsImage"]
            download_url = dds["imageUrl"]
            img_size = dds.get("size") or {}
            logical_w = img_size.get("width") or 0
            logical_h = img_size.get("height") or 0
            slices.append({
                "name": current_name,
                "path": current_path,
                "download_url": download_url,
                "format": "png",
                "logical_width": logical_w,
                "logical_height": logical_h,
                "scale": slice_scale,
                "scale_urls": _build_scale_urls(download_url, logical_w, logical_h),
            })

        for child_key in ("layers", "children"):
            for child in obj.get(child_key) or []:
                if isinstance(child, dict):
                    _walk(child, current_name, current_path)

    artboard = sketch_data.get("artboard", {})
    if artboard and artboard.get("layers"):
        for layer in artboard["layers"]:
            _walk(layer)
    elif sketch_data.get("info"):
        for item in sketch_data["info"]:
            _walk(item)

    return slices
