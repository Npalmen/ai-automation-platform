from typing import Any, Dict


def build_processor_result(
    message: str,
    processed_for: str,
    detected_type: str,
    summary: str,
    extracted_data: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    return {
        "message": message,
        "processed_for": processed_for,
        "detected_type": detected_type,
        "summary": summary,
        "extracted_data": extracted_data or {}
    }