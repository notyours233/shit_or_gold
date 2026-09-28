"""Prompt modules for centralized prompt management."""

from prompts.system_prompts import UNIFIED_SYSTEM_PROMPT
from prompts.debate_phase_prompts import (
    DEBATE_PROPOSE_SYSTEM_PROMPT,
    DEBATE_REVIEW_SYSTEM_PROMPT,
    DEBATE_REBUTTAL_SYSTEM_PROMPT,
    build_initial_debate_prompt,
)

__all__ = [
    "UNIFIED_SYSTEM_PROMPT",
    "DEBATE_PROPOSE_SYSTEM_PROMPT",
    "build_initial_debate_prompt",
    "DEBATE_REVIEW_SYSTEM_PROMPT",
    "DEBATE_REBUTTAL_SYSTEM_PROMPT",
]
