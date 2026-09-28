from typing import Any

from agents import AgentBase, RunContextWrapper, RunHooks, TContext, Tool
from agents.tool_context import ToolContext
from typing_extensions import TypeVar

from ..utils import PrintUtils, get_logger

TAgent = TypeVar("TAgent", bound=AgentBase, default=AgentBase)
logger = get_logger(__name__)

# Shared key used to track per-run tool call counts inside `RunContextWrapper.context`.
TOOL_CALL_COUNTS_KEY = "_utu_tool_call_counts"


def _inc_tool_call_count(ctx: Any, tool_name: str) -> None:
    """Best-effort tool call counting.

    Motivation:
    Some models (e.g. DeepSeek thinking mode) can loop and call the same tool repeatedly.
    We track tool call counts so tools can be dynamically disabled after a configured budget.
    """

    if not isinstance(ctx, dict):
        return
    counts = ctx.get(TOOL_CALL_COUNTS_KEY)
    if not isinstance(counts, dict):
        counts = {}
        ctx[TOOL_CALL_COUNTS_KEY] = counts
    try:
        prev = int(counts.get(tool_name, 0))
    except Exception:  # pylint: disable=broad-except
        prev = 0
    counts[tool_name] = prev + 1


class BaseRunHooks(RunHooks):
    def __init__(self):
        self.tool_result_max_length = 5000

    # on_llm_start, on_llm_end

    async def on_agent_start(self, context: RunContextWrapper[TContext], agent: TAgent) -> None:
        """Called before the agent is invoked. Called each time the current agent changes."""
        pass

    async def on_agent_end(self, context: RunContextWrapper[TContext], agent: TAgent, output: Any) -> None:
        """Called when the agent produces a final output."""
        pass

    async def on_handoff(self, context: RunContextWrapper[TContext], from_agent: TAgent, to_agent: TAgent) -> None:
        """Called when a handoff occurs."""
        pass

    async def on_tool_start(self, context: ToolContext, agent: TAgent, tool: Tool) -> None:
        """Called concurrently with tool invocation."""
        # Track tool call counts for this run; used by tool budgets (is_enabled gating).
        _inc_tool_call_count(getattr(context, "context", None), tool.name)
        logger.debug(f"[toolcall-{context.tool_call_id}] {tool.name}({context.tool_arguments})")

    async def on_tool_end(self, context: ToolContext, agent: TAgent, tool: Tool, result: Any) -> None:
        """Called after a tool is invoked."""
        # Tool results are not guaranteed to be strings (they are often dict/list),
        # so convert before logging / length checks.
        result_text = PrintUtils.truncate_text(result, max_length=self.tool_result_max_length, oneline=True)
        logger.debug(f"[toolcall-{context.tool_call_id}] {tool.name}: {result_text}...")
        if isinstance(result_text, str) and len(result_text) >= self.tool_result_max_length:
            logger.warning(
                f"Tool result too long! >= {self.tool_result_max_length} chars (truncated for logs)."
            )
