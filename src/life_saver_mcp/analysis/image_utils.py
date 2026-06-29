from __future__ import annotations

import base64
import io
import logging

logger = logging.getLogger(__name__)

MAX_GIF_FRAMES = 5


def extract_gif_frames(b64_data: str, mime_type: str, max_frames: int = MAX_GIF_FRAMES) -> list[tuple[str, str]]:
    if mime_type != "image/gif":
        return [(b64_data, mime_type)]

    try:
        from PIL import Image
    except ImportError:
        return [(b64_data, mime_type)]

    try:
        raw = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(raw))

        if not getattr(img, "is_animated", False):
            return [(b64_data, mime_type)]

        total_frames = getattr(img, "n_frames", 1)
        if total_frames <= 1:
            return [(b64_data, mime_type)]

        frame_indices = _pick_frame_indices(total_frames, max_frames)
        results: list[tuple[str, str]] = []

        for idx in frame_indices:
            img.seek(idx)
            frame = img.copy()
            if frame.mode not in ("RGB", "RGBA"):
                frame = frame.convert("RGB")
            buf = io.BytesIO()
            frame.save(buf, format="PNG")
            frame_b64 = base64.b64encode(buf.getvalue()).decode()
            results.append((frame_b64, "image/png"))

        logger.info("Extracted %d frames from animated GIF (%d total)", len(results), total_frames)
        return results

    except Exception as e:
        logger.warning("Failed to extract GIF frames: %s", e)
        return [(b64_data, mime_type)]


def _pick_frame_indices(total: int, max_frames: int) -> list[int]:
    if total <= max_frames:
        return list(range(total))
    step = (total - 1) / (max_frames - 1)
    return [round(i * step) for i in range(max_frames)]
