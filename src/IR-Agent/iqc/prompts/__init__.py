"""
Package: prompts
Description: Exports prompt constants and builder functions for the IQC pipeline.
Author: IQC Team
"""
from .system_prompts import (
    FIELD_DESCRIPTIONS, QUICK_PROMPTS, FIELD_EXAMPLES,
    EXTRACTION_SYSTEM_PROMPT,
    build_question_text, build_explanation_text,
)

__all__ = [
    "FIELD_DESCRIPTIONS", "QUICK_PROMPTS", "FIELD_EXAMPLES",
    "EXTRACTION_SYSTEM_PROMPT",
    "build_question_text", "build_explanation_text",
]
