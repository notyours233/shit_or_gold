import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import mcp.types as types
from agents import FunctionTool, function_tool

from ..config import ToolkitConfig
from ..hooks.base_hooks import TOOL_CALL_COUNTS_KEY
from ..utils import ChatCompletionConverter, FileUtils, MCPConverter, get_logger
from .utils import register_tool as register_tool

if TYPE_CHECKING:
    from e2b_code_interpreter import AsyncSandbox

logger = get_logger(__name__)


def _as_int(val: Any) -> int | None:
    """Parse a config value to int, returning None for empty/invalid/unlimited."""
    if val is None:
        return None
    if isinstance(val, str) and not val.strip():
        return None
    try:
        i = int(val)
    except Exception:  # pylint: disable=broad-except
        return None
    return i if i > 0 else None


class AsyncBaseToolkit:
    """Base class for toolkits."""

    def __init__(self, config: ToolkitConfig | dict | None = None):
        if not isinstance(config, ToolkitConfig):
            config = config or {}
            config = ToolkitConfig(config=config, name=self.__class__.__name__)

        self.config: ToolkitConfig = config
        self._tools_map: dict[str, Callable] = None

        self.env: _BaseEnv = None
        self.env_mode = self.config.env_mode  # TODO: deprecate it
        if self.env_mode == "e2b":
            self.e2b_sandbox: AsyncSandbox = None

    def setup_env(self, env: "_BaseEnv") -> None:
        """Setup env and workspace."""
        self.env = env
        if self.env_mode == "e2b":  # assert is E2BEnv
            self.e2b_sandbox = env.sandbox
        self.setup_workspace()

    def setup_workspace(self, workspace_root: str = None):
        """Setup workspace. Implemented inside specific toolkits."""
        pass

    @property
    def tools_map(self) -> dict[str, Callable]:
        """Lazy loading of tools map.
        - collect tools registered by @register_tool
        """
        if self._tools_map is None:
            self._tools_map = {}
            # Iterate through all methods of the class and register @tool
            for attr_name in dir(self):
                attr = getattr(self, attr_name)
                if callable(attr) and getattr(attr, "_is_tool", False):
                    self._tools_map[attr._tool_name] = attr
        return self._tools_map

    def get_tools_map_func(self) -> dict[str, Callable]:
        """Get tools map. It will filter tools by config.activated_tools if it is not None."""
        if self.config.activated_tools:
            assert all(tool_name in self.tools_map for tool_name in self.config.activated_tools), (
                f"Error config activated tools: {self.config.activated_tools}! available tools: {self.tools_map.keys()}"
            )
            tools_map = {tool_name: self.tools_map[tool_name] for tool_name in self.config.activated_tools}
        else:
            tools_map = self.tools_map
        return tools_map

    def get_tools_in_agents(self) -> list[FunctionTool]:
        """Get tools in openai-agents format."""
        tools_map = self.get_tools_map_func()
        raw_cfg = self.config.config or {}
        # Optional tool-call budgeting:
        # - `tool_call_limits`: per-tool max calls in a single run, e.g. {"literature_search": 1}
        # - `max_calls_per_run`: fallback max calls applied to all tools in this toolkit
        tool_call_limits = raw_cfg.get("tool_call_limits") or {}
        if not isinstance(tool_call_limits, dict):
            tool_call_limits = {}
        max_calls_per_run = _as_int(raw_cfg.get("max_calls_per_run"))

        tools = []
        for tool_name, tool in tools_map.items():
            limit = _as_int(tool_call_limits.get(tool_name)) or max_calls_per_run
            agent_tool = function_tool(
                tool,
                strict_mode=False,  # turn off strict mode
                # Keep budgeted tools registered across turns. Some chat-completions
                # models repeat a previous tool call even after the next tool schema
                # omits it; dynamic removal then becomes a fatal "tool not found".
                is_enabled=True,
            )
            if limit is not None:
                original_invoke = agent_tool.on_invoke_tool

                async def _budgeted_invoke(
                    run_context,
                    arguments,
                    *,
                    _original=original_invoke,
                    _tool_name=tool_name,
                    _limit=limit,
                ):
                    ctx = getattr(run_context, "context", None)
                    counts = ctx.get(TOOL_CALL_COUNTS_KEY, {}) if isinstance(ctx, dict) else {}
                    try:
                        used = int(counts.get(_tool_name, 0)) if isinstance(counts, dict) else 0
                    except Exception:  # pylint: disable=broad-except
                        used = 0
                    # BaseRunHooks increments the count in on_tool_start before invocation.
                    if used > _limit:
                        return json.dumps(
                            {
                                "ok": False,
                                "error": "tool_call_budget_exceeded",
                                "tool": _tool_name,
                                "max_calls_per_run": _limit,
                                "instruction": "Do not call this tool again; answer using the evidence already returned.",
                            },
                            ensure_ascii=False,
                        )
                    return await _original(run_context, arguments)

                agent_tool.on_invoke_tool = _budgeted_invoke
            tools.append(agent_tool)
        return tools

    def get_tools_in_openai(self) -> list[dict]:
        """Get tools in OpenAI format."""
        tools = self.get_tools_in_agents()
        return [ChatCompletionConverter.tool_to_openai(tool) for tool in tools]

    def get_tools_in_mcp(self) -> list[types.Tool]:
        """Get tools in MCP format."""
        tools = self.get_tools_in_agents()
        return [MCPConverter.function_tool_to_mcp(tool) for tool in tools]

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Call a tool by its name."""
        tools_map = self.get_tools_map_func()
        if name not in tools_map:
            raise ValueError(f"Tool {name} not found")
        tool = tools_map[name]
        return await tool(**arguments)


TOOL_PROMPTS: dict[str, str] = FileUtils.load_prompts("tools/tools_prompts.yaml")
