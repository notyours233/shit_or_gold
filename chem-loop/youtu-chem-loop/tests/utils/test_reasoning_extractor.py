from __future__ import annotations

from utu.utils.reasoning_extractor import (
    extract_reasoning_text_from_raw_responses,
    stitch_think_and_answer,
    strip_answer_blocks,
)


class _FakeModelResp:
    def __init__(self, output):
        self.output = output


def test_extract_reasoning_text_from_raw_responses_dict_item():
    raw_responses = [
        _FakeModelResp(
            output=[
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "first reasoning"}],
                }
            ]
        )
    ]
    assert extract_reasoning_text_from_raw_responses(raw_responses) == "first reasoning"


def test_extract_reasoning_text_from_raw_responses_dedup():
    raw_responses = [
        _FakeModelResp(
            output=[
                {"type": "reasoning", "summary": [{"type": "summary_text", "text": "dup"}]},
                {"type": "reasoning", "summary": [{"type": "summary_text", "text": "dup"}]},
            ]
        )
    ]
    assert extract_reasoning_text_from_raw_responses(raw_responses) == "dup"


def test_stitch_think_block():
    resp = "<answer>{\"overpotential\": 0.288}</answer>"
    out = stitch_think_and_answer(resp, "some reasoning")
    assert "<think>" in out.lower()
    assert "<answer>" in out.lower()


def test_stitch_think_block_noop_when_already_has_think():
    resp = "<think>r</think><answer>{\"x\": 1}</answer>"
    out = stitch_think_and_answer(resp, "ignored")
    assert out == resp


def test_stitch_think_and_answer_recovers_answer_from_reasoning_field():
    # Some providers may return the *answer* inside the thinking field and leave content empty.
    resp = ""
    reasoning = "reasoning text...\n\n<answer>{\"x\": 1}</answer>\n"
    out = stitch_think_and_answer(resp, reasoning)
    # Ensure answer is not nested inside <think>
    assert "</think>" in out.lower()
    assert "<answer>" in out.lower()
    assert out.lower().index("</think>") < out.lower().index("<answer>")
    assert "<answer>" not in strip_answer_blocks(out).lower()

