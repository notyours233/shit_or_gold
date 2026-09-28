"""
Experience updater for training-free GRPO.
"""

import asyncio
import ast
import copy
import json
import os
import re
from collections import defaultdict

from agents import custom_span
from tqdm import tqdm

from ..config import AgentConfig
from ..db import EvaluationSample
from ..utils import FileUtils, SimplifiedAsyncOpenAI, get_logger
from .utils import TaskRecorder

logger = get_logger(__name__)


class ExperienceUpdater:
    def __init__(self, config: AgentConfig, agent_objective: str, learning_objective: str):
        self.config = config
        self.agent_objective = agent_objective
        self.learning_objective = learning_objective
        prompt_pack = (os.getenv("UTU_EXPERIENCE_PROMPT_PACK") or "").strip().lower()
        if prompt_pack in ("", "chem", "casecard", "micro", "default"):
            prompt_path = "practice/experience.yaml"
        elif prompt_pack in ("generic", "broad", "legacy"):
            prompt_path = "practice/experience_generic.yaml"
        else:
            logger.warning("Unknown UTU_EXPERIENCE_PROMPT_PACK=%r; falling back to default prompts.", prompt_pack)
            prompt_path = "practice/experience.yaml"

        self.prompts = FileUtils.load_prompts(prompt_path)
        self.llm = SimplifiedAsyncOpenAI(**config.model.model_provider.model_dump())
        self._group_update_fallback_count = 0

    async def run(
        self,
        rollouts: list[EvaluationSample],
        recorder: TaskRecorder,
        concurrency: int = 16,
        given_ground_truth: bool = True,
        num_experiences: int = 2,
    ) -> None:
        """Update experiences based on rollouts."""
        # 1. Summarize trajectory for each rollout
        with custom_span("Trajectory Summarization"):
            problem_to_summarized_rollouts = await self._single_rollout_summary(
                rollouts=rollouts, concurrency=concurrency, given_ground_truth=given_ground_truth
            )

        # 2. Generate semantic group advantages based on summarized rollouts
        with custom_span("Semantic Group Advantage"):
            new_experiences = await self._group_advantage(
                problem_to_summarized_rollouts=problem_to_summarized_rollouts,
                concurrency=concurrency,
                given_ground_truth=given_ground_truth,
                num_experiences=num_experiences,
            )

        # 3. group update experiences
        with custom_span("Group update"):
            critiques = await self._group_update(
                recorder=recorder,
                new_experiences=new_experiences,
                concurrency=concurrency,
            )

        # 4. batch update experiences
        with custom_span("Batch update"):
            new_experiences = await self._batch_update(
                recorder=recorder,
                critiques=critiques,
            )

        if self._group_update_fallback_count:
            print(f"- Group update JSON fallback applied: {self._group_update_fallback_count}")

        # 5. assign new experience IDs
        new_experiences = {f"G{i}": exp for i, exp in enumerate(new_experiences.values())}
        recorder.experiences_update(new_experiences)
        return new_experiences

    async def _single_rollout_summary(
        self,
        rollouts: list[EvaluationSample],
        concurrency: int,
        given_ground_truth: bool,
    ) -> dict[str, list[str]]:
        """Summarize each rollout's trajectory."""
        # group by problems
        problems_to_rollouts = defaultdict(list)
        for rollout in rollouts:
            if len(rollout.trajectories) > 0:
                problems_to_rollouts[rollout.raw_question].append(rollout)

        # only summarize the group whose rollouts are partially correct
        all_rollouts_to_process = []
        for rollouts in problems_to_rollouts.values():
            if given_ground_truth:
                # only for those partially correct
                scores = [each.reward for each in rollouts]
                avg_score = sum(scores) / len(scores)
                if avg_score > 0 and avg_score < 1:
                    all_rollouts_to_process.extend(rollouts)
            else:
                all_rollouts_to_process.extend(rollouts)

        semaphore = asyncio.Semaphore(concurrency)

        async def summarize_with_semaphore(item: EvaluationSample):
            async with semaphore:
                try:
                    with custom_span("summary single rollout"):
                        traj0 = json.loads(item.trajectories)[0] if item.trajectories else {}
                        sp = FileUtils.get_jinja_template_str(
                            self.prompts["SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP"]
                        ).render(
                            agent_objective=self.agent_objective,
                            learning_objective=self.learning_objective,
                        )
                        up = FileUtils.get_jinja_template_str(
                            self.prompts["SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP"]
                        ).render(
                            question=item.raw_question,
                            trajectory=traj0.get("trajectory", []),
                            # For "thinking mode" providers, we persist the hidden reasoning field as a side-channel
                            # (see `utu/utils/reasoning_extractor.py`). Expose it to the summarizer so experiences
                            # can be distilled from explicit reasoning, not only inferred from actions.
                            thinking=traj0.get("reasoning") or "[Not available]",
                            answer=item.correct_answer if given_ground_truth else "[REDACTED]",
                            critique=item.reasoning or "[No critique provided]",
                        )
                        response = await self.llm.query_one(
                            messages=[
                                {"role": "system", "content": sp},
                                {"role": "user", "content": up},
                            ],
                            **self.config.model.model_params.model_dump(),
                        )
                    return {"trajectory_summary": response, **item.model_dump()}
                except Exception as e:
                    logger.warning(f"Warning: failed in single rollout summary, {e}")
                    return None

        # parallel running
        tasks = [summarize_with_semaphore(item) for item in all_rollouts_to_process]
        results = defaultdict(list)
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Single rollout summary"):
            result = await task
            if result is not None:
                problem = result["raw_question"]
                results[problem].append(result)
        return results

    async def _group_advantage(
        self,
        problem_to_summarized_rollouts: dict[str, list[dict]],
        concurrency: int,
        given_ground_truth: bool,
        num_experiences: int,
    ) -> dict[str, dict]:
        """Generate critique for each query based on summarized rollouts."""
        all_rollouts = []
        for rollouts in problem_to_summarized_rollouts.values():
            if given_ground_truth:
                # only for those partially correct
                scores = [each["reward"] for each in rollouts]
                avg_score = sum(scores) / len(scores)
                if avg_score > 0 and avg_score < 1:
                    all_rollouts.append(rollouts)
            else:
                all_rollouts.append(rollouts)

        semaphore = asyncio.Semaphore(concurrency)

        async def critique_with_semaphore(rollouts_per_problem: list[dict]):
            async with semaphore:
                try:
                    with custom_span("single query group advantage"):
                        formatted_trajectories = "\n\n".join(
                            [
                                f"Attempt {i + 1} (Reward {each['reward'] if given_ground_truth else '[REDACTED]'}):\n"
                                f"{each['trajectory_summary']}"
                                for i, each in enumerate(rollouts_per_problem)
                            ]
                        )
                        sp = FileUtils.get_jinja_template_str(self.prompts["SINGLE_QUERY_GROUP_ADVANTAGE_SP"]).render(
                            agent_objective=self.agent_objective,
                            learning_objective=self.learning_objective,
                            num_experiences=num_experiences,
                        )
                        up = FileUtils.get_jinja_template_str(self.prompts["SINGLE_QUERY_GROUP_ADVANTAGE_UP"]).render(
                            question=rollouts_per_problem[0]["raw_question"],
                            answer=rollouts_per_problem[0]["correct_answer"] if given_ground_truth else "[REDACTED]",
                            trajectories=formatted_trajectories,
                        )
                        response = await self.llm.query_one(
                            messages=[
                                {"role": "system", "content": sp},
                                {"role": "user", "content": up},
                            ],
                            **self.config.model.model_params.model_dump(),
                        )

                        # extract experiences from the response
                        pattern = re.compile(r"<Experiences>\s*(.*?)\s*</Experiences>", re.DOTALL | re.IGNORECASE)
                        match = pattern.search(response)
                        experiences = match.group(1).strip() if match else ""
                    return {"rollouts": rollouts_per_problem, "critique": response, "experiences": experiences}
                except Exception as e:
                    logger.warning(f"Warning: failed in single group advantage, {e}")
                    return None

        # parallel running
        results = []
        tasks = [critique_with_semaphore(rollouts_per_problem) for rollouts_per_problem in all_rollouts]
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Single query group advantage"):
            result = await task
            if result is not None:
                results.append(result)

        return results

    async def _group_update(
        self,
        recorder: TaskRecorder,
        new_experiences: list[dict],
        concurrency: int,
    ) -> dict[str, str]:
        """Group update experiences based on critiques."""
        semaphore = asyncio.Semaphore(concurrency)

        async def group_update_with_semaphore(new_experience: dict):
            async with semaphore:
                try:
                    with custom_span("single group update"):
                        # get current experiences from recorder
                        curr_experiences = recorder.experiences or {}
                        formatted_experiences = (
                            "\n".join([f"[{i}]. {e}" for i, e in curr_experiences.items()])
                            if curr_experiences
                            else "None"
                        )
                        sp = FileUtils.get_jinja_template_str(
                            self.prompts["GROUP_EXPERIENCE_UPDATE_TEMPLATE_SP"]
                        ).render(
                            agent_objective=self.agent_objective,
                            learning_objective=self.learning_objective,
                        )
                        up = FileUtils.get_jinja_template_str(
                            self.prompts["GROUP_EXPERIENCE_UPDATE_TEMPLATE_UP"]
                        ).render(
                            existing_experiences=formatted_experiences,
                            new_experiences=new_experience["experiences"],
                        )
                        response = await self.llm.query_one(
                            messages=[
                                {"role": "system", "content": sp},
                                {"role": "user", "content": up},
                            ],
                            **self.config.model.model_params.model_dump(),
                        )
                        operations = self._parse_ops_json_best_effort(response)
                        if operations is None:
                            operations = self._fallback_ops_add_all(str(new_experience.get("experiences") or ""))
                            self._group_update_fallback_count += 1
                    return {"operations": operations, **new_experience}
                except Exception as e:
                    # Avoid noisy WARNING logs during large smoke runs. Fall back to simple ADD ops so the
                    # experience pool still grows (instead of silently dropping a whole query's cards).
                    operations = self._fallback_ops_add_all(str(new_experience.get("experiences") or ""))
                    if operations:
                        self._group_update_fallback_count += 1
                        return {"operations": operations, **new_experience}
                    logger.debug("Group update failed and fallback produced no ops: %s", e)
                    return {"operations": [], **new_experience}

        # parallel running
        results = []
        tasks = [group_update_with_semaphore(new_experience) for new_experience in new_experiences]
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Group update"):
            result = await task
            if result is not None:
                results.append(result)
        return results

    async def _batch_update(
        self, recorder: TaskRecorder, critiques: list[dict], max_retries: int = 3
    ) -> dict[str, dict]:
        """Batch update experiences based on critiques."""
        # get current experiences from recorder
        logger.info("Batch update")
        # collect operations
        all_operations = []
        for each in critiques:
            all_operations.extend(each["operations"])
        print("- Num of operations to process:", len(all_operations))

        experiences = recorder.experiences or {}

        # IMPORTANT (ChemCouncil):
        # When experiences are paragraph-like (long strings), asking an LLM to *re-emit* a consolidated JSON revision
        # plan often collapses to a tiny output due to context/output token limits. This makes the experience pool
        # stop growing (or even shrink), which is the opposite of our "many micro-experiences" design.
        #
        # Default behavior:
        # - AUTO: if the batch is large, apply operations deterministically (no extra LLM call).
        # - You can force modes via env var:
        #   - UTU_EXPERIENCE_BATCH_UPDATE_MODE=direct  -> always deterministic apply
        #   - UTU_EXPERIENCE_BATCH_UPDATE_MODE=llm     -> always LLM consolidation (legacy)
        mode = (os.getenv("UTU_EXPERIENCE_BATCH_UPDATE_MODE") or "auto").strip().lower()
        if mode not in ("auto", "direct", "llm"):
            logger.warning("Unknown UTU_EXPERIENCE_BATCH_UPDATE_MODE=%r; falling back to auto.", mode)
            mode = "auto"

        if mode in ("direct", "auto"):
            # Heuristic: with many operations, LLM consolidation is likely to truncate/over-merge. Prefer direct apply.
            total_chars = sum(len(str(op.get("content") or "")) for op in all_operations)
            if mode == "direct" or len(all_operations) >= 40 or total_chars >= 12000:
                print(
                    f"- Batch update mode: {mode} -> deterministic_apply "
                    f"(ops={len(all_operations)} total_chars={total_chars})"
                )
                new_experiences = self._apply_operations_direct(experiences, all_operations)
                print("- Num of candidate experiences:", len(new_experiences))
                return new_experiences

        # Legacy path: use LLM to get the revision plan (may over-merge with long paragraph cards).
        revision_plan = []
        for _ in range(max_retries):
            try:
                sp = FileUtils.get_jinja_template_str(self.prompts["BATCH_EXPERIENCE_UPDATE_TEMPLATE_SP"]).render(
                    agent_objective=self.agent_objective,
                    learning_objective=self.learning_objective,
                )
                up = FileUtils.get_jinja_template_str(self.prompts["BATCH_EXPERIENCE_UPDATE_TEMPLATE_UP"]).render(
                    experiences_and_operations=self._format_exp_and_ops(experiences, all_operations)
                )
                response = await self.llm.query_one(
                    messages=[
                        {"role": "system", "content": sp},
                        {"role": "user", "content": up},
                    ],
                    **self.config.model.model_params.model_dump(),
                )
                # parse response
                revision_plan = json.loads(response.split("```json")[-1].split("```")[0])
                break
            except Exception:
                print("Warning: failed to decode in updating general experiences")

        if not isinstance(revision_plan, list) or not revision_plan:
            print("- Batch update fallback: deterministic_apply (llm_plan_decode_failed)")
            new_experiences = self._apply_operations_direct(experiences, all_operations)
            print("- Num of candidate experiences:", len(new_experiences))
            return new_experiences

        # apply revision plan to get new experiences
        max_ID = len(experiences)
        new_experiences = copy.deepcopy(experiences)
        for plan in revision_plan:
            operation = plan.get("operation", "ADD")
            content = plan.get("content", "")
            target_id = plan.get("id", None)
            if not content:
                continue

            if operation == "ADD":
                new_experiences[f"{max_ID}"] = content
                max_ID += 1
            elif operation == "UPDATE":
                if target_id in new_experiences:
                    new_experiences[target_id] = content
                else:
                    # directly add new experience
                    new_experiences[f"{max_ID}"] = content
                    max_ID += 1
            elif operation == "DELETE":
                if target_id in new_experiences:
                    del new_experiences[target_id]
        print("- Num of candidate experiences:", len(new_experiences))
        return new_experiences

    @staticmethod
    def _apply_operations_direct(experiences: dict[str, str], operations: list[dict]) -> dict[str, str]:
        """Apply group update operations deterministically (no extra LLM consolidation).

        Why:
        - For paragraph-like micro-cards, a second LLM pass often cannot re-emit dozens of long strings within
          max_tokens, so it silently collapses the update plan and the pool stops growing.
        - Deterministic apply preserves the already-generated card contents from group_update.

        Dedupe policy (conservative):
        - Only dedupe exact content matches after whitespace normalization.
        - Prefer ADD over UPDATE when an UPDATE would overwrite a generic guideline with a CaseCard.
        """
        new_experiences = copy.deepcopy(experiences or {})

        def _norm(s: str) -> str:
            return " ".join(str(s or "").split()).strip()

        seen_contents = {_norm(v) for v in new_experiences.values() if isinstance(v, str) and v.strip()}
        # Consolidate operations deterministically so results are order-invariant:
        # - DELETE overrides UPDATE for the same id
        # - Multiple UPDATEs pick the "most informative" one (longest content)
        id_to_ops: dict[str, list[dict]] = defaultdict(list)
        add_contents: list[str] = []

        for op in operations or []:
            if not isinstance(op, dict):
                continue
            operation = str(op.get("operation") or "").strip().upper()
            target_id = op.get("id")
            content = _norm(op.get("content"))

            if operation == "NONE":
                continue

            if operation == "ADD":
                if content:
                    add_contents.append(content)
                continue

            if operation == "UPDATE":
                if isinstance(target_id, str) and target_id.strip():
                    id_to_ops[target_id.strip()].append({"operation": "UPDATE", "content": content})
                else:
                    # Malformed UPDATE: treat as ADD to avoid losing potentially useful cards.
                    if content:
                        add_contents.append(content)
                continue

            if operation == "DELETE":
                if isinstance(target_id, str) and target_id.strip():
                    id_to_ops[target_id.strip()].append({"operation": "DELETE"})
                continue

        # Apply id-targeted ops with DELETE precedence.
        for target_id, ops in id_to_ops.items():
            if any(str(o.get("operation") or "").upper() == "DELETE" for o in ops):
                if target_id in new_experiences:
                    del new_experiences[target_id]
                continue

            update_contents = [str(o.get("content") or "") for o in ops if str(o.get("operation") or "").upper() == "UPDATE"]
            update_contents = [_norm(c) for c in update_contents if _norm(c)]
            if not update_contents:
                continue

            old = new_experiences.get(target_id, "")
            old_norm = _norm(old)
            is_old_case = old_norm.startswith(("MaterialCard |", "CaseCard |"))

            # If an UPDATE tries to overwrite a generic guideline with a material card, keep both by converting to ADD.
            candidate_updates: list[str] = []
            for c in update_contents:
                is_new_case = c.startswith(("MaterialCard |", "CaseCard |"))
                if (not is_old_case) and is_new_case:
                    add_contents.append(c)
                else:
                    candidate_updates.append(c)

            if not candidate_updates:
                continue

            best = max(candidate_updates, key=len)
            if target_id in new_experiences:
                new_experiences[target_id] = best
                seen_contents.add(best)
            else:
                add_contents.append(best)

        # Apply ADD ops with exact-content dedupe.
        next_id = len(new_experiences)

        def _alloc_id() -> str:
            nonlocal next_id
            while str(next_id) in new_experiences:
                next_id += 1
            out = str(next_id)
            next_id += 1
            return out

        for content in add_contents:
            content = _norm(content)
            if not content or content in seen_contents:
                continue
            new_experiences[_alloc_id()] = content
            seen_contents.add(content)

        return new_experiences

    def _format_exp_and_ops(self, experiences: dict[str, str], operations: list[dict]) -> str:
        """Format experiences and operations."""
        if not operations:
            return "No batch operations."

        # Format existing experiences and their related operations
        formatted_res = []
        for id, exp in experiences.items():
            curr_str = f"Experience {id}:\nContent: {exp}\n"
            related_ops = [op for op in operations if op.get("id") == id]
            if related_ops:
                curr_str += "Related Operations:\n"
                op_str = []
                for op in related_ops:
                    op_str.append(f"{json.dumps(op, ensure_ascii=False, indent=2)}")
                op_str = "\n".join(op_str)
                curr_str += op_str
            else:
                curr_str += "No related operations."
            formatted_res.append(curr_str)

        # Format operations without specific IDs
        no_id_ops = [op for op in operations if not op.get("id", None)]
        if no_id_ops:
            curr_str = "Operations without specific Experience ID:\n"
            op_str = []
            for op in no_id_ops:
                op_str.append(f"{json.dumps(op, ensure_ascii=False, indent=2)}")
            op_str = "\n".join(op_str)
            curr_str += op_str
            formatted_res.append(curr_str)

        return "\n\n".join(formatted_res)

    @staticmethod
    def _parse_ops_json_best_effort(text: str) -> list[dict] | None:
        """Parse the group-update operations JSON array from a model response.

        Models sometimes return:
        - valid JSON inside ```json fences
        - a JSON array plus extra prose
        - python-like literals with single quotes

        We try a few safe strategies before giving up.
        """
        if not isinstance(text, str) or not text.strip():
            return None

        raw = text
        if "```json" in raw:
            raw = raw.split("```json")[-1]
            raw = raw.split("```")[0]
        raw = raw.strip()

        # Try direct JSON first.
        try:
            obj = json.loads(raw)
            if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
                return obj
        except Exception:
            pass

        # Try extracting the first JSON array substring.
        m = re.search(r"\[\s*{.*?}\s*\]", raw, flags=re.DOTALL)
        if m:
            cand = m.group(0).strip()
            try:
                obj = json.loads(cand)
                if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
                    return obj
            except Exception:
                raw = cand

        # Fallback: python-literal parse (safe, non-executing), with minimal JSON->Python token normalization.
        # This handles single quotes and None/True/False.
        try:
            cand = re.sub(r"\bnull\b", "None", raw)
            cand = re.sub(r"\btrue\b", "True", cand, flags=re.IGNORECASE)
            cand = re.sub(r"\bfalse\b", "False", cand, flags=re.IGNORECASE)
            obj = ast.literal_eval(cand)
            if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
                return obj
        except Exception:
            return None

        return None

    @staticmethod
    def _fallback_ops_add_all(experiences_block: str) -> list[dict]:
        """Fallback when group-update JSON is malformed: treat extracted cards as ADD ops."""
        if not isinstance(experiences_block, str) or not experiences_block.strip():
            return []

        lines = [ln.strip() for ln in experiences_block.splitlines() if ln.strip()]
        cards: list[str] = []
        for ln in lines:
            m = re.match(r"^\s*\d+\.\s*(.*)\s*$", ln)
            if m:
                cand = m.group(1).strip()
                if cand:
                    cards.append(cand)
                continue
            # If the model omitted numbering, accept raw one-liners that look like cards.
            if ln.startswith(("MaterialCard |", "CaseCard |")):
                cards.append(ln)

        if not cards:
            # Last resort: treat the whole block as one card line.
            cards = [" ".join(experiences_block.split())]

        ops = []
        for card in cards:
            card = " ".join(str(card).split()).strip()
            if not card:
                continue
            ops.append({"operation": "ADD", "id": None, "content": card})
        return ops
