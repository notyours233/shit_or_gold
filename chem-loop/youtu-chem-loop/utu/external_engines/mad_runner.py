#!/usr/bin/env python3
"""Subprocess runner for the MAD external engine.

This script is executed by MADEngineAdapter via a subprocess. It is intentionally
standalone (stdlib + MAD deps) so it can run in a separate Python environment that
has the debate runtime requirements installed.

Protocol:
- Read one JSON object from stdin:
    {"question": "...", "meta": {...}}
- Print one JSON object to stdout:
    {
      "final_output": "...",
      "reasoning": "...",
      "trajectory": {...}
    }

Notes:
- We ask MAD to `conclude` with a STRICT JSON payload: {"think": "...", "answer": {...}}.
  The adapter converts this into legacy `<think>/<answer>` blocks for verify compatibility
  and applies best-effort auto-repair when the model deviates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
import importlib.util
from pathlib import Path
from typing import Any


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val or not val.strip():
        raise RuntimeError(f"Missing required env var: {key}")
    return val.strip()


def _build_system_prompt(*, enable_rag: bool) -> str:
    # Keep this prompt minimal and "hard", similar to youtu-agent chem-performance agent instructions.
    # The ReAct runtime will still run a THOUGHT phase separately.
    tool_policy = ""
    if enable_rag:
        tool_policy = (
            "\n"
            "TOOL POLICY:\n"
            "- You MUST call `search_experience` once before concluding. Query by material name/description, task, and metrics.\n"
            "- For better numeric anchoring, you MAY call `search_literature` (local Chroma-backed RAG) once.\n"
            "  If retrieval returns empty, proceed with best-effort domain knowledge.\n"
            "  Hard limits: call `search_experience` at most ONCE and `search_literature` at most ONCE per question.\n"
            "- Prefer calling `conclude` as soon as you have enough evidence.\n"
        )
    else:
        # In ablation mode we want a clean baseline without retrieval errors or tool loops.
        tool_policy = (
            "\n"
            "TOOL POLICY:\n"
            "- Literature retrieval may be unavailable in this run. Do NOT call `search_literature`.\n"
            "- You MAY still call `search_experience` if available.\n"
            "- Proceed with domain knowledge and call `conclude` as soon as you can.\n"
        )

    return (
        "You are a material-performance prediction assistant covering all 19 registered task directions.\n"
        "\n"
        "You will be given a task prompt that contains an INPUT_JSON with:\n"
        "- material_name (required)\n"
        "- material_description and optional structured/custom material fields\n"
        "- task_type\n"
        "- metrics_to_predict\n"
        "\n"
        "CRITICAL OUTPUT RULES:\n"
        "- You MUST call the `conclude` tool to submit the final answer.\n"
        "- When calling `conclude`, set its argument `conclusion` to a STRICT JSON object of the shape:\n"
        "    {\n"
        "      \"think\": \"short reasoning (string)\",\n"
        "      \"answer\": {\"metric_key\": value, ...}\n"
        "    }\n"
        "- The `answer` JSON keys MUST exactly match the metric names in metrics_to_predict (same spelling and case).\n"
        "- Output ALL requested metrics (no missing keys) and do NOT output extra keys.\n"
        "- JSON values MUST be numbers only (no units, no strings).\n"
        "- Normalize units before answering: conductivity S/m; percentage metrics as percent numbers;\n"
        "  thermal_conductivity W m-1 K-1; saturation_magnetization emu/g; neel_temperature K;\n"
        "  antibacterial minimum_concentration as ppm (ug/mL and mg/L are numerically equivalent in dilute water);\n"
        "  thermoelectric figure_of_merit as dimensionless zT.\n"
        "- Treat A m2/kg as equivalent to emu/g for magnetic saturation magnetization.\n"
        "- Never invent missing synthesis, structure, composition, element-content, or condition fields.\n"
        "- Do NOT wrap the output in <think>/<answer> tags; the system will handle formatting downstream.\n"
        + tool_policy
    )


def _monkeypatch_action_instruction_for_experience_first(*, enable_rag: bool) -> None:
    """Force MAD's ACTION phase to retrieve experiences before concluding.

    Why:
    - In MAD's default ReAct loop, the model is allowed to call `conclude` immediately.
      Explicit MAD evaluation and recommendation runs should retrieve relevant experiences
      via `search_experience` before concluding.
    - We keep this patch local to the subprocess runner to avoid modifying the MAD repo.
    """
    try:
        from agents.react_agent import ReActAgent  # type: ignore
    except Exception:
        return

    def _forced_action_phase_instruction() -> str:
        rag_clause = ""
        if enable_rag:
            rag_clause = (
                "- After `search_experience`, you MAY call `search_literature` ONCE if you need citations/evidence.\n"
            )
        return (
            "CURRENT PHASE: ACTION\n"
            "You MUST call tools (no free-form answers).\n"
            "\n"
            "RETRIEVAL REQUIREMENT (important):\n"
            "- If you have NOT called `search_experience` yet in this run, you MUST call `search_experience` NOW.\n"
            "- Do NOT call `conclude` until AFTER you have called `search_experience` at least once.\n"
            "- Hard limit: call `search_experience` at most ONCE. If it returns no results, proceed anyway.\n"
            + rag_clause
            + "\n"
            "After you receive the retrieval observations, in the NEXT step you should call `conclude`.\n"
        )

    # Patch the staticmethod used to build the ACTION system instruction each step.
    ReActAgent._get_action_phase_instruction = staticmethod(_forced_action_phase_instruction)  # type: ignore[attr-defined]


def _monkeypatch_action_instruction_for_no_rag_conclude_first() -> None:
    """Force MAD's ACTION-phase to conclude immediately (for RAG ablation baseline).

    This avoids the model repeatedly attempting retrieval tools that are not configured.
    """
    try:
        from agents.react_agent import ReActAgent  # type: ignore
    except Exception:
        return

    def _forced_action_phase_instruction() -> str:
        return (
            "CURRENT PHASE: ACTION\n"
            "You MUST call tools (no free-form answers).\n"
            "\n"
            "Literature RAG is disabled for this run:\n"
            "- Do NOT call `search_literature`.\n"
            "- You MAY call `search_experience` if you think it helps.\n"
            "- Call `conclude` now with the final STRICT JSON payload.\n"
        )

    ReActAgent._get_action_phase_instruction = staticmethod(_forced_action_phase_instruction)  # type: ignore[attr-defined]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mad_repo_path", required=True, help="Path to MAD repo root (contains agents/)")
    ap.add_argument("--max_react_steps", type=int, default=6)
    ap.add_argument("--agent_name", default="mad_engine")
    args = ap.parse_args()

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            raise RuntimeError("stdin JSON missing non-empty 'question' string")
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        masked_doc_ids = payload.get("masked_doc_ids")
        masked_doc_ids = masked_doc_ids if isinstance(masked_doc_ids, list) else []

        # Ensure we import MAD's local `agents` package, not the openai-agents SDK package.
        mad_repo = os.path.abspath(args.mad_repo_path)
        sys.path.insert(0, mad_repo)

        # Also allow importing youtu-agent helper modules (stdlib-only proxies).
        youtu_root = Path(__file__).resolve().parents[2]
        sys.path.insert(1, str(youtu_root))

        # Model config: use youtu-agent's env convention so one `.env` works for both repos.
        api_key = _require_env("UTU_LLM_API_KEY")
        base_url = _require_env("UTU_LLM_BASE_URL")
        # Model name is usually set in `.env`, but keep a safe default so the runner is usable
        # even if the caller relies on YAML defaults for UTU_LLM_MODEL.
        model = os.getenv("UTU_LLM_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro"

        # Best-effort: propagate temperature/max_tokens if the caller set them.
        temperature = float(os.getenv("UTU_LLM_TEMPERATURE", "1.0"))
        max_tokens = int(os.getenv("UTU_LLM_MAX_TOKENS", "2000"))

        model_config = {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Experience retrieval default (project decision):
        # - Prefer semantic vector search for `search_experience` retrieval
        # - Keep `jaccard` as a safe fallback when embeddings are unavailable
        #
        # We set a default via env so operators can override without code changes.
        os.environ.setdefault("MAD_EXPERIENCE_SEARCH_MODE", "vector")

        # Instantiate MAD ReAct agent.
        from agents.react_agent import ReActAgent  # type: ignore

        # Use only explicitly provided elements as optional retrieval guards. The material
        # name/description remains the primary experience query anchor through INPUT_JSON;
        # do not infer a user-supplied composition from a formula here.
        components: list[str] | None = None
        elements = meta.get("elements")
        if not isinstance(elements, list):
            material_input = meta.get("material_input")
            if isinstance(material_input, dict):
                elements = material_input.get("elements")
        # Legacy datasets carry measured metal elements under `metals`.
        if not isinstance(elements, list):
            elements = meta.get("metals")
        if isinstance(elements, list) and all(isinstance(x, str) for x in elements):
            components = [x for x in elements if x.strip()]

        # Experience retrieval:
        # - Optional legacy-evaluation override: load an explicitly supplied YAML pack.
        # - Fallback: load MAD's stable recommendation packs under <mad_repo>/experience.
        experience_store = None
        exp_pack = (os.getenv("MAD_EXPERIENCE_PACK_PATH") or os.getenv("MAD_EXPERIENCE_PACK") or "").strip()
        try:
            from experience import ExperienceStore  # type: ignore

            if exp_pack:
                experience_store = ExperienceStore(
                    storage_path=exp_pack,
                    max_experiences=int(os.getenv("MAD_EXPERIENCE_MAX", "2000")),
                    relevance_threshold=float(os.getenv("MAD_EXPERIENCE_THRESHOLD", "0.8")),
                    packs_path=None,
                    # Do NOT load MAD's builtin packs when we explicitly provide a per-step pack,
                    # otherwise we'd mix duplicate guidelines (seeded packs already include them).
                    load_builtin_packs=False,
                    guideline_top_k=int(os.getenv("MAD_EXPERIENCE_GUIDE_K", "3")),
                    always_include_guidelines=True,
                    guideline_search_mode=str(os.getenv("MAD_EXPERIENCE_GUIDE_MODE", "keyword") or "keyword"),
                )
                _eprint(
                    f"[mad_runner] loaded experience pack: {exp_pack} (total={len(getattr(experience_store, 'experiences', []) or [])})"
                )
            else:
                # Default: use MAD repo packs (stable experience.yaml + archive if any).
                experience_store = ExperienceStore(
                    storage_path=str(Path(mad_repo) / "data" / "experience_db.json"),
                    packs_path=str(Path(mad_repo) / "experience"),
                    max_experiences=int(os.getenv("MAD_EXPERIENCE_MAX", "2000")),
                    relevance_threshold=float(os.getenv("MAD_EXPERIENCE_THRESHOLD", "0.8")),
                    guideline_top_k=int(os.getenv("MAD_EXPERIENCE_GUIDE_K", "3")),
                    always_include_guidelines=True,
                    guideline_search_mode=str(os.getenv("MAD_EXPERIENCE_GUIDE_MODE", "keyword") or "keyword"),
                    load_builtin_packs=True,
                )
                _eprint(
                    f"[mad_runner] loaded default MAD experiences from {Path(mad_repo) / 'experience'} "
                    f"(total={len(getattr(experience_store, 'experiences', []) or [])})"
                )
        except Exception as e:
            _eprint(f"[mad_runner] WARNING: failed to initialize experience store: {e}")
            experience_store = None

        # Wire youtu-agent's chem literature DB into MAD as an optional RAG backend.
        # NOTE: This is enforced in code (not in prompts) and supports doc-level masking.
        rag_system = None
        enable_rag = (os.getenv("MAD_ENABLE_RAG", "1") or "1").strip().lower() not in ("0", "false", "no")
        if enable_rag:
            try:
                # IMPORTANT:
                # We cannot import `utu.*` in the MAD venv directly because `utu/__init__.py` depends on
                # the openai-agents package (`agents.run`), and MAD repo also has a local `agents/`
                # package which shadows it. Load the proxy module by file path instead.
                proxy_path = youtu_root / "utu" / "external_engines" / "chem_literature_proxy.py"
                spec = importlib.util.spec_from_file_location("ytu_chem_literature_proxy", str(proxy_path))
                if spec is None or spec.loader is None:
                    raise RuntimeError(f"Failed to load proxy module spec from: {proxy_path}")
                proxy_mod = importlib.util.module_from_spec(spec)
                # Required for dataclasses (and some libs) that access `sys.modules[__module__]`.
                sys.modules[spec.name] = proxy_mod
                spec.loader.exec_module(proxy_mod)  # type: ignore[call-arg]
                SubprocessChemLiteratureRAG = getattr(proxy_mod, "SubprocessChemLiteratureRAG")

                # Use youtu-agent venv to run the chem literature runner (has chromadb/voyage deps installed).
                youtu_python = os.getenv("YOUTU_PYTHON_BIN")
                if not youtu_python:
                    # Preferred: youtu-chem-loop local venv (standalone layout).
                    cand1 = (youtu_root / ".venv" / "bin" / "python")
                    # Monorepo layout: venv at repo parent (../.venv).
                    cand2 = (Path(youtu_root).parent / ".venv" / "bin" / "python")
                    if cand1.exists():
                        youtu_python = str(cand1)
                    elif cand2.exists():
                        youtu_python = str(cand2)
                    else:
                        # Fallback: run with the current interpreter (works in single-venv setups).
                        youtu_python = sys.executable
                runner_path = os.getenv("YOUTU_CHEM_LITERATURE_RUNNER") or str(
                    youtu_root / "utu" / "external_engines" / "chem_literature_runner.py"
                )
                rt = (meta.get("task_type") or meta.get("property_type") or meta.get("reaction_type") or "").strip() or None

                rag_system = SubprocessChemLiteratureRAG(
                    python_bin=youtu_python,
                    runner_path=runner_path,
                    repo_root=str(youtu_root),
                    reaction_type=rt,
                    masked_doc_ids=[str(x) for x in masked_doc_ids if str(x).strip()],
                    # Keep tool-call cost bounded (model may try to call search_rag multiple times).
                    limit=int(os.getenv("MAD_RAG_LIMIT", "5")),
                    max_distance=float(os.getenv("MAD_RAG_MAX_DISTANCE", "0.35")),
                    timeout_s=float(os.getenv("MAD_RAG_TIMEOUT_S", "30")),
                    call_limit=1,
                )
            except Exception as e:
                _eprint(f"[mad_runner] WARNING: failed to initialize RAG system: {e}")
                rag_system = None

        rag_enabled = bool(enable_rag and rag_system is not None)
        # Enforce "experience-first" behavior to ensure experience retrieval is actually used.
        # (Without this, the model may immediately call `conclude` and skip retrieval.)
        if experience_store is not None:
            _monkeypatch_action_instruction_for_experience_first(enable_rag=rag_enabled)
        elif rag_enabled:
            # If experience store is unavailable, fall back to a simple "conclude after optional search" baseline.
            _monkeypatch_action_instruction_for_no_rag_conclude_first()
        else:
            _monkeypatch_action_instruction_for_no_rag_conclude_first()

        agent = ReActAgent(
            agent_id="mad_external_engine",
            name=str(args.agent_name),
            model_config=model_config,
            rag_system=rag_system,
            experience_store=experience_store,
            system_prompt=_build_system_prompt(enable_rag=rag_enabled),
            max_react_steps=int(args.max_react_steps),
            verbose=False,
        )

        response, trajectory = agent.generate_response_with_react(
            query=question,
            components=components,
            context={"meta": meta},
            system_prompt_override=_build_system_prompt(enable_rag=rag_enabled),
        )

        traj_dict = trajectory.to_dict()
        # Prefer the actual CONCLUDE tool payload from trajectory.tool_calls, because:
        # - it is the most structured/authoritative output channel, and
        # - some providers may return empty/garbled assistant `content` even when tool args are correct.
        conclusion_payload: Any | None = None
        try:
            steps = traj_dict.get("steps") if isinstance(traj_dict, dict) else None
            if isinstance(steps, list) and steps:
                for step in reversed(steps):
                    if not isinstance(step, dict):
                        continue
                    tool_calls = step.get("tool_calls")
                    if not isinstance(tool_calls, list):
                        continue
                    for call in reversed(tool_calls):
                        if not isinstance(call, dict):
                            continue
                        if str(call.get("tool_name") or "").strip() != "conclude":
                            continue
                        args = call.get("tool_args")
                        if isinstance(args, dict) and "conclusion" in args:
                            conclusion_payload = args.get("conclusion")
                        else:
                            conclusion_payload = call.get("observation")
                        break
                    if conclusion_payload is not None:
                        break
        except Exception:
            conclusion_payload = None

        # Prefer explicit step-level thoughts as the "reasoning" field for youtu-agent stitching.
        # This avoids embedding the full original prompt (which often contains `<answer>` tags),
        # and keeps `<think>` concise and relevant for experience distillation.
        thoughts: list[str] = []
        for step in (traj_dict.get("steps") or []):
            if not isinstance(step, dict):
                continue
            t = step.get("thought")
            if isinstance(t, str) and t.strip():
                thoughts.append(t.strip())
        reasoning_text = "\n\n".join(thoughts).strip() or (response.reasoning or "")

        # If we found a structured conclude payload, use it as final_output.
        final_output = response.content
        if conclusion_payload is not None:
            if isinstance(conclusion_payload, (dict, list)):
                try:
                    final_output = json.dumps(conclusion_payload, ensure_ascii=False)
                except Exception:
                    final_output = str(conclusion_payload)
            else:
                final_output = str(conclusion_payload)

        out: dict[str, Any] = {
            "final_output": final_output,
            "reasoning": reasoning_text,
            "trajectory": traj_dict,
            "sources": response.sources,
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.stdout.flush()
        return 0

    except Exception as e:
        _eprint(f"[mad_runner] ERROR: {e}")
        _eprint(traceback.format_exc())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
