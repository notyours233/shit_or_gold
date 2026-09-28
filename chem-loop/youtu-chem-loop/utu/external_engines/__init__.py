"""External engine integrations.

These adapters allow the rollout stage to call non-utu agents (e.g. a colleague's
research repo) while keeping our evaluation/verify contract intact.
"""

from .mad_engine import MADEngineAdapter, MADEngineConfig

__all__ = ["MADEngineAdapter", "MADEngineConfig"]

