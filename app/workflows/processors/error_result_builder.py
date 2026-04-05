from typing import Any, Dict


def build_error_result(
    message: str,
    processed_for: str,
    detected_type: str,
    summary: str,
    error: str
) -> Dict[str, Any]:
    return {
        "message": message,
        "processed_for": processed_for,
        "detected_type": detected_type,
        "summary": summary,
        "error": error
    }