"""Debate trace ingestion utilities.

This package provides light-weight helpers to ingest multi-agent debate logs
(e.g., LangGraph JSON exports) and convert them into inputs suitable for
experience distillation / closed-loop updates.
"""

from .langgraph_trace import (  # noqa: F401
    Critique,
    LangGraphDebate,
    Proposal,
    load_langgraph_debate,
)

