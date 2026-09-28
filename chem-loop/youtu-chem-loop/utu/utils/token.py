from __future__ import annotations

# NOTE:
# `tiktoken.get_encoding("cl100k_base")` will download a BPE file on first use if
# it's not already cached. That makes importing this module brittle in restricted
# / offline environments (e.g. CI sandboxes).
#
# We therefore:
# - lazily initialize the tokenizer, and
# - fall back to a simple character-based heuristic if tiktoken is unavailable
#   or cannot be initialized.

_TOKENIZER_INIT_DONE = False
_tokenizer = None
_tiktoken_init_error: str | None = None


def _maybe_init_tokenizer() -> None:
    global _TOKENIZER_INIT_DONE, _tokenizer, _tiktoken_init_error
    if _TOKENIZER_INIT_DONE:
        return
    _TOKENIZER_INIT_DONE = True
    try:
        import tiktoken  # type: ignore

        _tokenizer = tiktoken.get_encoding("cl100k_base")
    except Exception as e:  # pragma: no cover (depends on runtime network/caches)
        _tokenizer = None
        _tiktoken_init_error = f"{type(e).__name__}: {e}"


class TokenUtils:
    @staticmethod
    def truncate_text_by_token(text: str, limit: int = -1) -> str:
        """Truncate text to a given token limit with tiktoken."""
        if limit <= 0 or not text:
            return text
        _maybe_init_tokenizer()
        if _tokenizer is None:
            # Heuristic: ~4 chars per token for English-ish text. Keep it simple and
            # deterministic so unit tests do not require network access.
            approx_chars = max(0, int(limit) * 4)
            if len(text) <= approx_chars:
                return text
            return text[:approx_chars] + "..."

        tokens = _tokenizer.encode(text)
        if len(tokens) <= limit:
            return text
        truncated_tokens = tokens[:limit]
        truncated_text = _tokenizer.decode(truncated_tokens)
        return truncated_text + "..."

    @staticmethod
    def count_tokens(text: str) -> int:
        if not text:
            return 0
        _maybe_init_tokenizer()
        if _tokenizer is None:
            # Same heuristic as truncate_text_by_token.
            return max(1, len(text) // 4)
        return len(_tokenizer.encode(text))
