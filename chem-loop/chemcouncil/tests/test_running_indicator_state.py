from __future__ import annotations

import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


class _RunningIndicatorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.indicators: dict[str, dict[str, str | None]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        values = dict(attrs)
        element_id = values.get("id")
        if element_id in {"recommend-running", "update-running", "experience-build-running"}:
            self.indicators[element_id] = values


def test_running_indicators_start_hidden() -> None:
    parser = _RunningIndicatorParser()
    parser.feed((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    assert set(parser.indicators) == {
        "recommend-running",
        "update-running",
        "experience-build-running",
    }
    for attrs in parser.indicators.values():
        assert "hidden" in attrs
        assert "hidden" in str(attrs["class"]).split()
        assert attrs["aria-hidden"] == "true"
        assert attrs["aria-busy"] == "false"


def test_running_hidden_css_overrides_running_display() -> None:
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    running_rule = css.index(".running { display: flex;")
    hidden_rule = css.index(".running.hidden,")

    assert hidden_rule > running_rule
    assert ".running[hidden] { display: none; }" in css


def test_job_status_controls_spinner_and_completed_label() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for the frontend state test")

    script = r"""
const fs = require("fs");
const vm = require("vm");
const sourcePath = process.argv[1];
let source = fs.readFileSync(sourcePath, "utf8");
source = source.replace(/\ninit\(\);\s*$/, `
globalThis.__statusTest = { isActiveJobStatus, syncJobRunningIndicator, pill };
`);
const context = {
  localStorage: {
    getItem(key) { return key === "chemcouncil_lang" ? "zh" : null; },
    setItem() {},
    removeItem() {},
  },
  setTimeout,
  clearTimeout,
};
vm.runInNewContext(source, context, { filename: sourcePath });

function fakeElement() {
  const classes = new Set(["running", "hidden"]);
  return {
    hidden: true,
    attrs: {},
    classList: {
      contains(name) { return classes.has(name); },
      toggle(name, force) {
        if (force) classes.add(name); else classes.delete(name);
      },
    },
    setAttribute(name, value) { this.attrs[name] = value; },
  };
}

const { isActiveJobStatus, syncJobRunningIndicator, pill } = context.__statusTest;
const active = {};
for (const status of ["queued", "running", "cancelling"]) {
  const element = fakeElement();
  syncJobRunningIndicator(element, status);
  active[status] = {
    active: isActiveJobStatus(status),
    hidden: element.hidden,
    hiddenClass: element.classList.contains("hidden"),
    ariaHidden: element.attrs["aria-hidden"],
    ariaBusy: element.attrs["aria-busy"],
  };
}
const terminal = {};
for (const status of ["completed", "failed", "cancelled"]) {
  const element = fakeElement();
  element.hidden = false;
  element.classList.toggle("hidden", false);
  syncJobRunningIndicator(element, status);
  terminal[status] = {
    active: isActiveJobStatus(status),
    hidden: element.hidden,
    hiddenClass: element.classList.contains("hidden"),
    ariaHidden: element.attrs["aria-hidden"],
    ariaBusy: element.attrs["aria-busy"],
  };
}
process.stdout.write(JSON.stringify({ active, terminal, completedPill: pill("completed") }));
"""
    result = subprocess.run(
        [node, "-e", script, str(STATIC_DIR / "app.js")],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    for state in payload["active"].values():
        assert state == {
            "active": True,
            "hidden": False,
            "hiddenClass": False,
            "ariaHidden": "false",
            "ariaBusy": "true",
        }
    for state in payload["terminal"].values():
        assert state == {
            "active": False,
            "hidden": True,
            "hiddenClass": True,
            "ariaHidden": "true",
            "ariaBusy": "false",
        }
    assert "已完成" in payload["completedPill"]
