from __future__ import annotations

import json
import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

NOISE_TYPES = {"color", "gradient", "colorStop", "colorControl"}


def extract_annotations(sketch_data: dict, design_scale: float = 2.0) -> str:
    scale = design_scale or 2.0

    def _px(val) -> str:
        if val is None:
            return "0"
        return str(round(float(val) / scale, 1))

    def _rgb_str(color: dict) -> str:
        r = round(color.get("red", color.get("r", 0)))
        g = round(color.get("green", color.get("g", 0)))
        b = round(color.get("blue", color.get("b", 0)))
        return f"rgb({r},{g},{b})"

    def _rgba_str(color: dict, opacity: float = 100) -> str:
        r = round(color.get("red", color.get("r", 0)))
        g = round(color.get("green", color.get("g", 0)))
        b = round(color.get("blue", color.get("b", 0)))
        a = round(opacity / 100, 2) if opacity < 100 else 1
        if a < 1:
            return f"rgba({r},{g},{b},{a})"
        return f"rgb({r},{g},{b})"

    def _extract_opacity(layer: dict) -> float:
        bo = layer.get("blendOptions", {})
        if "opacity" in bo:
            op = bo["opacity"]
            if isinstance(op, dict):
                return op.get("value", 100)
            return op
        return 100

    def _extract_fill_color(layer: dict) -> str | None:
        fill = layer.get("fill", {})
        if not fill:
            return None
        color = fill.get("color")
        if not color:
            return None
        return _rgba_str(color, _extract_opacity(layer))

    def _extract_shadow_str(shadow: dict) -> str | None:
        if not shadow.get("enabled", True):
            return None
        color = shadow.get("color", {})
        opacity = shadow.get("opacity", {})
        op_val = opacity.get("value", 100) if isinstance(opacity, dict) else opacity
        distance = shadow.get("distance", 0)
        blur = shadow.get("blur", 0)
        spread = shadow.get("chokeMatte", 0)
        angle_raw = shadow.get("localLightingAngle", {})
        angle = angle_raw.get("value", 120) if isinstance(angle_raw, dict) else (angle_raw or 120)
        rad = math.radians(angle)
        x_off = round(distance * math.cos(rad), 1)
        y_off = round(distance * math.sin(rad), 1)
        return f"{_rgba_str(color, op_val)} {_px(x_off)}px {_px(y_off)}px {_px(blur)}px {_px(spread)}px"

    def _extract_stroke_str(frame_fx: dict) -> str | None:
        if not frame_fx.get("enabled", True):
            return None
        size = frame_fx.get("size", 0)
        color = frame_fx.get("color", {})
        opacity = frame_fx.get("opacity", {})
        op_val = opacity.get("value", 100) if isinstance(opacity, dict) else opacity
        style = frame_fx.get("style", "outsetFrame")
        pos_map = {"outsetFrame": "outside", "insetFrame": "inside", "centeredFrame": "center"}
        pos = pos_map.get(style, "outside")
        return f"{_px(size)}px {pos} {_rgba_str(color, op_val)}"

    board = sketch_data.get("board", {})
    psd_name = sketch_data.get("psdName", "")
    device = sketch_data.get("device", "")
    board_w = board.get("width", 0)
    board_h = board.get("height", 0)
    board_fill = board.get("fill", {})
    board_color = _rgb_str(board_fill.get("color", {})) if board_fill.get("color") else "#FFFFFF"

    text_layers: list[dict] = []
    shape_layers: list[dict] = []
    image_layers: list[dict] = []
    group_structure: list[dict] = []

    def _walk_layer(layer: dict, depth: int = 0, parent_path: str = ""):
        if not layer or not isinstance(layer, dict):
            return
        if layer.get("visible", True) is False:
            return

        name = layer.get("name", "?")
        ltype = layer.get("type", "?")
        w = layer.get("width", 0) or 0
        h = layer.get("height", 0) or 0
        left = layer.get("left", 0) or 0
        top = layer.get("top", 0) or 0
        current_path = f"{parent_path}/{name}" if parent_path else name

        if w == 0 and h == 0:
            for child in layer.get("layers", []):
                _walk_layer(child, depth, current_path)
            return

        opacity = _extract_opacity(layer)

        if ltype == "textLayer":
            ti = layer.get("textInfo", {})
            text = ti.get("text", "")
            color = ti.get("color", {})
            size = ti.get("size", 0)
            font = ti.get("fontPostScriptName", "")
            bold = ti.get("bold", False)
            le = layer.get("layerEffects", {})
            entry = {
                "name": name, "path": current_path, "text": text,
                "x": _px(left), "y": _px(top), "w": _px(w), "h": _px(h),
                "color": _rgba_str(color, opacity) if color else None,
                "fontSize": _px(size) if size else None,
                "font": font, "bold": bold,
                "stroke": _extract_stroke_str(le.get("frameFX", {})) if "frameFX" in le else None,
                "shadow": _extract_shadow_str(le.get("dropShadow", {})) if "dropShadow" in le else None,
            }
            text_layers.append(entry)

        elif ltype == "shapeLayer":
            fill_color = _extract_fill_color(layer)
            le = layer.get("layerEffects", {})
            entry = {
                "name": name, "path": current_path,
                "x": _px(left), "y": _px(top), "w": _px(w), "h": _px(h),
                "fill": fill_color,
                "opacity": opacity if opacity < 100 else None,
                "stroke": _extract_stroke_str(le.get("frameFX", {})) if "frameFX" in le else None,
            }
            shape_layers.append(entry)

        elif ltype == "layer":
            if w > 10 and h > 10:
                image_layers.append({
                    "name": name, "path": current_path,
                    "x": _px(left), "y": _px(top), "w": _px(w), "h": _px(h),
                })

        elif ltype == "layerSection":
            group_structure.append({
                "name": name, "depth": depth,
                "x": _px(left), "y": _px(top), "w": _px(w), "h": _px(h),
            })

        for child in layer.get("layers", []):
            _walk_layer(child, depth + 1, current_path)

    board_layers = board.get("layers", [])
    for layer in board_layers:
        _walk_layer(layer)

    lines: list[str] = []
    lines.append("=" * 50)
    lines.append("Design Annotations")
    lines.append("=" * 50)
    lines.append(f"Name: {psd_name}")
    lines.append(f"Device: {device} | Scale: @{int(scale)}x")
    lines.append(f"Canvas: {_px(board_w)}x{_px(board_h)} | BG: {board_color}")
    lines.append(f"All sizes in logical pixels (divided by @{int(scale)}x)")
    lines.append("")

    if group_structure:
        lines.append("--- Groups ---")
        for g in group_structure[:30]:
            indent = "  " * min(g["depth"], 4)
            lines.append(f"{indent}{g['name']} ({g['w']}x{g['h']})")
        lines.append("")

    if text_layers:
        lines.append(f"--- Text Layers ({len(text_layers)}) ---")
        for t in text_layers[:50]:
            line = f"  \"{t['text'][:40]}\" | {t['font']} {t['fontSize']}px"
            if t["color"]:
                line += f" | {t['color']}"
            if t["bold"]:
                line += " | bold"
            if t["stroke"]:
                line += f" | stroke: {t['stroke']}"
            if t["shadow"]:
                line += f" | shadow: {t['shadow']}"
            lines.append(line)
        lines.append("")

    if shape_layers:
        lines.append(f"--- Shape Layers ({len(shape_layers)}) ---")
        for s in shape_layers[:30]:
            line = f"  {s['name']} ({s['w']}x{s['h']})"
            if s["fill"]:
                line += f" | fill: {s['fill']}"
            if s["opacity"]:
                line += f" | opacity: {s['opacity']}%"
            if s["stroke"]:
                line += f" | stroke: {s['stroke']}"
            lines.append(line)
        lines.append("")

    if image_layers:
        lines.append(f"--- Image Layers ({len(image_layers)}) ---")
        for img in image_layers[:20]:
            lines.append(f"  {img['name']} ({img['w']}x{img['h']})")
        lines.append("")

    return "\n".join(lines)


def extract_design_tokens(sketch_data: dict) -> str:
    def _get_dimensions(obj: dict) -> tuple:
        frame = obj.get("ddsOriginFrame") or obj.get("layerOriginFrame") or {}
        x = frame.get("x", obj.get("left", 0)) or 0
        y = frame.get("y", obj.get("top", 0)) or 0
        w = frame.get("width", obj.get("width", 0)) or 0
        h = frame.get("height", obj.get("height", 0)) or 0
        return x, y, w, h

    def _simplify_fill(fill: dict) -> str | None:
        if not fill.get("isEnabled", True):
            return None
        fill_type = fill.get("fillType", 0)
        if fill_type == 0:
            color = fill.get("color", {})
            return f"solid({color.get('value', 'unknown')})"
        if fill_type == 1:
            gradient = fill.get("gradient", {})
            stops = gradient.get("colorStops", [])
            from_pt = gradient.get("from", {})
            to_pt = gradient.get("to", {})
            dx = to_pt.get("x", 0.5) - from_pt.get("x", 0.5)
            dy = to_pt.get("y", 0) - from_pt.get("y", 0)
            angle = round(math.degrees(math.atan2(dx, dy))) % 360
            parts = []
            for s in stops:
                c = s.get("color", {}).get("value", "unknown")
                p = s.get("position", 0)
                parts.append(f"{c} {round(p * 100)}%")
            return f"linear-gradient({angle}deg, {', '.join(parts)})"
        return None

    def _simplify_border(border: dict) -> str | None:
        if not border.get("isEnabled", True):
            return None
        color = border.get("color", {}).get("value", "unknown")
        thickness = border.get("thickness", 1)
        return f"{thickness}px {color}"

    def _simplify_shadow(shadow: dict) -> str | None:
        if not shadow.get("isEnabled", True):
            return None
        color = shadow.get("color", {}).get("value", "unknown")
        x = shadow.get("offsetX", 0)
        y = shadow.get("offsetY", 0)
        blur = shadow.get("blurRadius", 0)
        spread = shadow.get("spread", 0)
        return f"{color} {x}px {y}px {blur}px {spread}px"

    def _has_only_transparent_solid(fills: list) -> bool:
        for f in fills:
            if not f.get("isEnabled", True):
                continue
            if f.get("fillType", 0) == 0:
                color = f.get("color", {})
                alpha = color.get("alpha", color.get("a", 1))
                if alpha == 0:
                    continue
            return False
        return True

    def _is_high_risk(obj: dict) -> bool:
        obj_type = (obj.get("type") or obj.get("ddsType") or "").lower()
        if obj_type in NOISE_TYPES:
            return False
        _, _, w, h = _get_dimensions(obj)
        if w < 2 and h < 2:
            return False
        fills = obj.get("fills", [])
        for f in fills:
            if f.get("isEnabled", True) and f.get("fillType") == 1:
                return True
        if obj.get("borders"):
            for b in obj["borders"]:
                if b.get("isEnabled", True):
                    return True
        radius = obj.get("radius")
        if isinstance(radius, list) and len(set(radius)) > 1:
            return True
        if obj.get("shadows"):
            for s in obj["shadows"]:
                if s.get("isEnabled", True):
                    return True
        return False

    tokens: list[str] = []

    def _walk(obj: dict, parent_path: str = ""):
        if not obj or not isinstance(obj, dict):
            return
        if not obj.get("isVisible", True):
            return
        name = obj.get("name", "")
        current_path = f"{parent_path}/{name}" if parent_path else name
        if _is_high_risk(obj):
            x, y, w, h = _get_dimensions(obj)
            lines = [f'[{obj.get("type", "?")}] "{name}" @({int(x)},{int(y)}) {int(w)}x{int(h)}']
            radius = obj.get("radius")
            if radius:
                lines.append(f"  radius: {radius}")
            for f in obj.get("fills", []):
                s = _simplify_fill(f)
                if s:
                    lines.append(f"  fill: {s}")
            for b in obj.get("borders", []):
                s = _simplify_border(b)
                if s:
                    lines.append(f"  border: {s}")
            opacity = obj.get("opacity")
            if opacity is not None and opacity < 100:
                lines.append(f"  opacity: {opacity}%")
            for sh in obj.get("shadows", []):
                s = _simplify_shadow(sh)
                if s:
                    lines.append(f"  shadow: {s}")
            tokens.append("\n".join(lines))
        for child in obj.get("layers", []):
            _walk(child, current_path)

    artboard = sketch_data.get("artboard", {})
    if artboard and artboard.get("layers"):
        for layer in artboard["layers"]:
            _walk(layer)
    elif sketch_data.get("info"):
        for item in sketch_data["info"]:
            _walk(item)

    return "\n\n".join(tokens)
