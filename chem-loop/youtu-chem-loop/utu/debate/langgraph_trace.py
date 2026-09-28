"""LangGraph debate trace loader.

The repo's "closed-loop" plan treats debate as an additional supervision signal:
- proposals that are *defeated* by other agents are treated as negative examples
  (at least wrt reasoning/tool-use patterns)
- the corresponding critiques (reviews) can be distilled into reusable experiences

This module parses the JSON export produced by the LangGraph debate runner.
It intentionally avoids depending on LangGraph itself; it only consumes the saved
JSON schema.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


ProposalStatus = Literal["surviving", "defeated", "withdrawn", "unknown"]

_REACTION_TYPE_RE = re.compile(r"\b(?:Reaction\s*Type|Target\s*reaction)\s*:\s*(?P<rt>[A-Za-z0-9_+-]+)\b")


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    agent_name: str | None
    status: ProposalStatus
    claim: str | None
    trajectory: dict[str, Any] | None

    @property
    def query(self) -> str | None:
        traj = self.trajectory or {}
        q = traj.get("query")
        return q.strip() if isinstance(q, str) and q.strip() else None

    @property
    def steps(self) -> list[dict[str, Any]]:
        traj = self.trajectory or {}
        steps = traj.get("steps")
        return steps if isinstance(steps, list) else []

    @property
    def final_answer(self) -> str | None:
        traj = self.trajectory or {}
        fa = traj.get("final_answer")
        return fa.strip() if isinstance(fa, str) and fa.strip() else None


@dataclass(frozen=True)
class Critique:
    """A critique/review item targeting a proposal."""

    round: int | None
    from_proposal_id: str | None
    target_proposal_id: str
    flaw_type: str | None
    critique: str | None
    valid: bool
    evidence: Any | None = None


@dataclass(frozen=True)
class LangGraphDebate:
    path: str
    debate_id: str | None
    run_id: str | None
    engine: str | None
    reaction_type: str | None
    components: list[str]
    raw: dict[str, Any]

    proposals: list[Proposal]
    critiques: list[Critique]

    def proposal_status_map(self) -> dict[str, ProposalStatus]:
        return {p.proposal_id: p.status for p in self.proposals}

    def critiques_by_target(self, *, valid_only: bool = True) -> dict[str, list[Critique]]:
        out: dict[str, list[Critique]] = {}
        for c in self.critiques:
            if valid_only and not c.valid:
                continue
            out.setdefault(c.target_proposal_id, []).append(c)
        return out


def _as_str(x: Any) -> str | None:
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None


def _status_map_from_result(result: dict[str, Any]) -> dict[str, ProposalStatus]:
    """Return proposal_id -> status using result.{surviving,defeated,withdrawn}_proposals."""

    out: dict[str, ProposalStatus] = {}
    for key, status in (
        ("surviving_proposals", "surviving"),
        ("defeated_proposals", "defeated"),
        ("withdrawn_proposals", "withdrawn"),
    ):
        items = result.get(key) or []
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            pid = _as_str(it.get("proposal_id"))
            if pid:
                out[pid] = status  # type: ignore[assignment]
    return out


def load_langgraph_debate(path: str | Path) -> LangGraphDebate:
    """Load a LangGraph debate JSON export from disk."""

    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a JSON object at top-level, got: {type(raw).__name__}")

    # Support multiple debate runners:
    # - our in-repo debate runner emits {debate_id, run_id, reaction_type, ...}
    # - the external debate runtime `MAD/` emits {experiment_id, timestamp, ...}
    debate_id = _as_str(raw.get("debate_id")) or _as_str(raw.get("experiment_id"))
    run_id = _as_str(raw.get("run_id")) or _as_str(raw.get("timestamp"))
    engine = _as_str(raw.get("engine"))
    reaction_type = _as_str(raw.get("reaction_type"))

    components_raw = raw.get("components") or []
    components: list[str] = []
    if isinstance(components_raw, list):
        for x in components_raw:
            s = _as_str(x)
            if s:
                components.append(s)

    result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
    status_by_id = _status_map_from_result(result)

    debate_history = result.get("debate_history") or []
    if not isinstance(debate_history, list):
        debate_history = []

    proposals: list[Proposal] = []
    critiques: list[Critique] = []

    for e in debate_history:
        if not isinstance(e, dict):
            continue
        et = _as_str(e.get("type")) or ""

        if et == "propose":
            pid = _as_str(e.get("proposal_id"))
            if not pid:
                continue
            proposals.append(
                Proposal(
                    proposal_id=pid,
                    agent_name=_as_str(e.get("agent_name")),
                    status=status_by_id.get(pid, "unknown"),
                    claim=_as_str(e.get("claim")),
                    trajectory=e.get("trajectory") if isinstance(e.get("trajectory"), dict) else None,
                )
            )
            continue

        if et == "review":
            target = _as_str(e.get("target_proposal_id"))
            if not target:
                continue
            critiques.append(
                Critique(
                    round=int(e.get("round")) if isinstance(e.get("round"), int) else None,
                    from_proposal_id=_as_str(e.get("from_proposal_id")),
                    target_proposal_id=target,
                    flaw_type=_as_str(e.get("flaw_type")),
                    critique=_as_str(e.get("critique")),
                    valid=bool(e.get("valid")),
                    evidence=e.get("evidence"),
                )
            )

    # Best-effort: infer reaction_type from proposal claim/query when it is not present
    # at the top-level (as in `MAD/outputs/result_*.json`).
    if reaction_type is None:
        for p0 in proposals:
            claim = (p0.claim or "").strip()
            if claim:
                m = _REACTION_TYPE_RE.search(claim)
                if m:
                    reaction_type = m.group("rt").strip()
                    break
            q = p0.query or ""
            if q:
                m = _REACTION_TYPE_RE.search(q)
                if m:
                    reaction_type = m.group("rt").strip()
                    break

    return LangGraphDebate(
        path=str(p),
        debate_id=debate_id,
        run_id=run_id,
        engine=engine,
        reaction_type=reaction_type,
        components=components,
        raw=raw,
        proposals=proposals,
        critiques=critiques,
    )
