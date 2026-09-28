import json
import sys
from collections import defaultdict

import prompt_toolkit
from colorama import Fore, Style, init
from prompt_toolkit.patch_stdout import patch_stdout

init(autoreset=True)  # Reset color to default (autoreset=True handles this automatically)

COLOR_DICT = defaultdict(lambda: Style.RESET_ALL)
COLOR_DICT.update(
    {
        "gray": Fore.LIGHTBLACK_EX,
        "orange": Fore.LIGHTYELLOW_EX,
        "red": Fore.RED,
        "green": Fore.GREEN,
        "blue": Fore.BLUE,
        "yellow": Fore.YELLOW,
        "magenta": Fore.MAGENTA,
        "cyan": Fore.CYAN,
        "white": Fore.WHITE,
        "bold_blue": Style.BRIGHT + Fore.BLUE,
    }
)


class PrintUtils:
    @staticmethod
    def _is_interactive_tty() -> bool:
        """Best-effort check for whether we can safely prompt for input.

        In CI/sandboxed runs (including our unit tests), stdin/stdout can be
        non-interactive and prompt_toolkit may raise EOFError/PermissionError
        when trying to attach to the event loop.
        """

        try:
            return bool(sys.stdin and sys.stdin.isatty() and sys.stdout and sys.stdout.isatty())
        except Exception:
            return False

    @staticmethod
    def print_input(prompt_text: str):
        """styled user input"""
        # https://github.com/prompt-toolkit/python-prompt-toolkit
        # user_input = input(COLOR_DICT[prompt_color] + prompt_text + COLOR_DICT[input_color])
        # print(Style.RESET_ALL, end="")
        if not PrintUtils._is_interactive_tty():
            # Non-interactive environment: don't crash the caller/tests.
            return ""
        try:
            return prompt_toolkit.prompt(prompt_text)
        except (EOFError, PermissionError, OSError):
            # prompt_toolkit can raise EOFError in sandboxed / redirected stdin.
            return ""

    @staticmethod
    async def async_print_input(prompt_text: str) -> str:
        # https://python-prompt-toolkit.readthedocs.io/en/master/pages/asking_for_input.html#prompt-in-an-asyncio-application  # noqa: E501
        if not PrintUtils._is_interactive_tty():
            return ""
        session = prompt_toolkit.PromptSession()
        try:
            with patch_stdout():
                return await session.prompt_async(prompt_text)
        except (EOFError, PermissionError, OSError):
            return ""

    @staticmethod
    def print_info(
        msg: str,
        color: str = "gray",
        add_prefix: bool = False,
        prefix: str = "",
        end: str = "\n",
        flush: bool = True,
    ):
        if add_prefix:
            msg = prefix + " " + msg
        print(COLOR_DICT[color] + msg + Style.RESET_ALL, end=end, flush=flush)

    @staticmethod
    def print_bot(
        msg: str,
        color: str = "orange",
        add_prefix: bool = False,
        prefix: str = "[BOT]",
        end: str = "\n",
        flush: bool = True,
    ):
        PrintUtils.print_info(msg, color=color, add_prefix=add_prefix, prefix=prefix, end=end, flush=flush)

    @staticmethod
    def print_tool(
        msg: str,
        color: str = "green",
        add_prefix: bool = False,
        prefix: str = "[TOOL]",
        end: str = "\n",
        flush: bool = True,
    ):
        PrintUtils.print_info(msg, color=color, add_prefix=add_prefix, prefix=prefix, end=end, flush=flush)

    @staticmethod
    def print_error(
        msg: str,
        color: str = "red",
        add_prefix: bool = False,
        prefix: str = "",
        end: str = "\n",
        flush: bool = True,
    ):
        PrintUtils.print_info(msg, color=color, add_prefix=add_prefix, prefix=prefix, end=end, flush=flush)

    @staticmethod
    def format_json(obj: dict, indent: int = None) -> str:
        return json.dumps(obj, indent=indent, ensure_ascii=False)

    @staticmethod
    def truncate_text(text, max_length: int = 100, oneline: bool = True) -> str:
        """Truncate text to max_length, adding ellipsis if truncated.

        Args:
            text: The text to truncate
            max_length: Maximum length of the returned text
            oneline: Whether to convert text to a single line by removing newlines
        """
        if not isinstance(text, str):
            # Tool outputs can be lists/dicts/None/etc. Convert to a readable string so
            # logging hooks don't crash on `.splitlines()`.
            try:
                text = json.dumps(text, ensure_ascii=False, default=str)
            except TypeError:
                text = str(text)
        if oneline:
            text = " ".join(text.splitlines())
        if len(text) <= max_length:
            return text
        else:
            return text[: max_length - 3] + "..."
