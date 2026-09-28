# Debate Trace Contract (Closed Loop Ingestion)

This spec defines the minimal JSON contract required for `youtu-chem-loop` to ingest a multi-agent debate trace
and distill experiences from it (defeated vs surviving proposals + critiques).

In this workspace, the primary consumer is:
- `youtu-chem-loop/scripts/debate/update_experiences_from_debate.py`

The parser is intentionally file-based and does not depend on LangGraph at runtime:
- `youtu-chem-loop/utu/debate/langgraph_trace.py`

## Supported Producers

In ChemCouncil, debate traces are produced by MAD:
- `MAD/outputs/result_*.json`

The loader is best-effort and accepts either:
- `debate_id` / `run_id`, or
- `experiment_id` / `timestamp` (fallback naming used by some exporters)

Resolution rules:
- `debate_id = debate_id || experiment_id`
- `run_id = run_id || timestamp`

## Top-Level JSON Object (Required)

The file MUST be a JSON object (dict).

Recommended top-level keys (best-effort, not all required):
- `engine`: string (e.g. `"langgraph"`)
- `components`: list[str] (metal symbols; optional % lives elsewhere)
- `debate_id`: string (optional)
- `run_id`: string (optional)
- `experiment_id`: string (optional; used as debate_id fallback)
- `timestamp`: string (optional; used as run_id fallback)
- `reaction_type`: string (optional; may be inferred from proposal claim/query)
- `result`: object (REQUIRED; see below)

## `result` Object (Required)

`result` MUST be a JSON object containing:

### Status lists (Required for supervision signal)

- `surviving_proposals`: list[object]
- `defeated_proposals`: list[object]
- `withdrawn_proposals`: list[object]

Each item SHOULD be a dict containing at least:
- `proposal_id`: string
- `claim`: string (optional but useful for debugging)

The ingestor uses these lists to assign a pseudo reward:
- surviving => reward=1.0
- defeated => reward=0.0
- withdrawn => ignored by default (configurable)

### `debate_history` (Required)

`debate_history` MUST be a list of event objects. Only two event types are required:

1) Proposal event:
```json
{
  "type": "propose",
  "proposal_id": "agent1",
  "agent_name": "agent1",
  "claim": "Reaction Type: OER ...",
  "trajectory": {
    "query": "... Target reaction: OER ...",
    "steps": [ { ... }, { ... } ],
    "final_answer": "{...}" 
  }
}
```

Required fields:
- `type="propose"`
- `proposal_id` (string)
- `trajectory.steps` (list) (may be empty; required shape)

2) Review/Critique event:
```json
{
  "type": "review",
  "round": 1,
  "from_proposal_id": "agent2",
  "target_proposal_id": "agent1",
  "flaw_type": "wrong_unit",
  "critique": "....",
  "valid": true,
  "evidence": []
}
```

Required fields:
- `type="review"`
- `target_proposal_id` (string)
- `valid` (bool)

Other fields are optional but recommended: `round`, `from_proposal_id`, `flaw_type`, `critique`, `evidence`.

## Reaction Type Inference (Optional)

If `reaction_type` is missing at the top-level, the loader attempts best-effort inference from:
- proposal `claim` text containing `Reaction Type: <RT>`
- proposal `trajectory.query` text containing `Target reaction: <RT>`

This value is only used for metadata/audit; it does not affect reward.
