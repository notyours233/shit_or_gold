from __future__ import annotations

import inspect
from html.parser import HTMLParser
from pathlib import Path

from chemcouncil.server import (
    EXPERIENCE_UPDATE_BATCH_SIZE_DEFAULT,
    EXPERIENCE_UPDATE_EPOCHS_DEFAULT,
    EXPERIENCE_UPDATE_GRPO_N_DEFAULT,
    EXPERIENCE_UPDATE_ROLLOUT_CONCURRENCY_DEFAULT,
)
from chemcouncil.workflows import run_experience_update_job


class _InputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inputs: dict[str, dict[str, str | None]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        values = dict(attrs)
        input_id = values.get("id")
        if input_id:
            self.inputs[input_id] = values


def test_feedback_defaults_match_selected_19_direction_sweep() -> None:
    assert EXPERIENCE_UPDATE_BATCH_SIZE_DEFAULT == 19
    assert EXPERIENCE_UPDATE_GRPO_N_DEFAULT == 3
    assert EXPERIENCE_UPDATE_ROLLOUT_CONCURRENCY_DEFAULT == 4
    assert EXPERIENCE_UPDATE_EPOCHS_DEFAULT == 1

    defaults = {
        name: parameter.default
        for name, parameter in inspect.signature(run_experience_update_job).parameters.items()
    }
    assert defaults["batch_size"] == 19
    assert defaults["grpo_n"] == 3
    assert defaults["rollout_concurrency"] == 4
    assert defaults["epochs"] == 1


def test_feedback_form_displays_selected_defaults() -> None:
    index_path = Path(__file__).resolve().parents[1] / "static" / "index.html"
    parser = _InputParser()
    parser.feed(index_path.read_text(encoding="utf-8"))

    assert parser.inputs["update-batch-size"]["value"] == "19"
    assert "readonly" in parser.inputs["update-batch-size"]
    assert parser.inputs["update-n"]["value"] == "3"
    assert parser.inputs["update-c"]["value"] == "4"
    assert parser.inputs["update-e"]["value"] == "1"
    assert "checked" in parser.inputs["update-rag"]
    assert "disabled" in parser.inputs["update-rag"]
