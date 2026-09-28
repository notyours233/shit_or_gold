"""Chem-loop runtime package (extracted from the upstream youtu-agent framework).

This repo focuses on the electrochemistry closed-loop workflow:
- Training-free GRPO experience distillation (chem-performance)
- Single-agent GRPO rollouts with optional literature RAG/masking
- MAD external rollout engine integration for recommendation/evaluation compatibility
- Debate-trace ingestion -> experience update
- Experimental CSV ingestion -> dataset building

We keep initialization lightweight here:
- set up logging (based on UTU_LOG_LEVEL)
- set up tracing if configured (Phoenix/OpenTelemetry)

GRPO uses the standard openai-agents Runner. MAD is not part of the GRPO rollout
group; it remains a separate recommendation-time debate engine.
"""

from .utils import EnvUtils, setup_logging

# Keep the original "required env" contract: GRPO/experience distillation needs an LLM.
EnvUtils.assert_env(["UTU_LLM_TYPE", "UTU_LLM_MODEL"])

setup_logging(EnvUtils.get_env("UTU_LOG_LEVEL", "WARNING"))

# Tracing is optional; never fail import if tracing deps/config are missing.
try:  # pragma: no cover
    from .tracing import setup_tracing

    setup_tracing()
except Exception:
    pass
