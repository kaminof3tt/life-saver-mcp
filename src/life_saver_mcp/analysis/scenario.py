from __future__ import annotations

from .prompts import parse_analysis_response
from ..models import AnalysisResult


def detect_scenario_and_build_result(raw_response: str, raw_content=None) -> AnalysisResult:
    parsed = parse_analysis_response(raw_response)
    return AnalysisResult(
        scenario=parsed.get("scenario", "general"),
        summary=parsed.get("summary", ""),
        details=parsed.get("details", {}),
        raw_content=raw_content,
    )
