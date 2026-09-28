import asyncio
import json
import time

from agents import Agent, Runner, gen_trace_id, trace
from tqdm import tqdm

from ...config import ConfigLoader, EvalConfig
from ...external_engines import MADEngineAdapter, MADEngineConfig
from ...hooks import get_run_hooks
from ...literature.chem_performance_masking import CHEM_PERF_DOC_ID_RESOLVER
from ...tools import TOOLKIT_MAP
from ...utils import AgentsUtils, get_logger
from ..data import DBDataManager, EvaluationSample
from ..processer import PROCESSER_FACTORY, BaseProcesser

logger = get_logger(__name__, "INFO")


class BaseBenchmark:
    """Base class for benchmarks.

    Evaluation phases:
      - preprocess: load and preprocess the data
      - rollout: rollout the predictions
      - judge: judge the correctness of a batch of predictions
      - stat: get metrics.
    """

    dataset: DBDataManager
    _source_to_processer: dict[str, BaseProcesser] = {}

    def __init__(self, config: EvalConfig | str) -> None:
        # config
        if isinstance(config, str):
            config = ConfigLoader.load_eval_config(name=config)
        self.config = config

        # dataset
        self.dataset = DBDataManager(config)
        _samples = self.dataset.load()
        if len(_samples) == 0:
            raise ValueError(f"No samples found for data config '{self.config.data}'! Please check the data config.")

    async def main(self):
        with trace(f"[{self.config.exp_id}] Evaluation", trace_id=gen_trace_id()):
            logger.info(
                f"> Running with config: \n{json.dumps(self.config.model_dump(), indent=2, ensure_ascii=False)}"
            )
            self.preprocess()
            await self.rollout()
            await self.judge()
            logger.info("> Running stat...")
            await self.stat()
            logger.info("> Cleaning up...")
            await self.cleanup()

    def preprocess(self) -> None:
        """Preprocess the dataset before rollout."""
        samples = self.dataset.get_samples(stage="init")
        logger.info(f"Preprocessing {len(samples)} samples...")
        results = []
        for sample in tqdm(samples, desc="Preprocessing"):
            processed_sample = self.preprocess_one(sample)
            if processed_sample is not None:
                results.append(processed_sample)
        logger.info(f"Successfully preprocessed {len(results)} samples. Updated to db.")
        return results

    def preprocess_one(self, sample: EvaluationSample) -> EvaluationSample:
        processer = self._get_processer(sample.source)
        processed_sample = processer.preprocess_one(sample)
        if processed_sample is None:
            return None
        self.dataset.save(sample)
        return sample

    async def rollout(self, max_retries: int = 3) -> None:
        """Rollout the datapoints."""
        samples = self.dataset.get_samples(stage="init")
        logger.info(f"Rollout {len(samples)} samples...")

        semaphore = asyncio.Semaphore(self.config.concurrency)

        async def rollout_with_semaphore(item: EvaluationSample):
            async with semaphore:
                for i in range(max_retries):
                    if i > 0:
                        logger.warning(f"Retrying rollout for sample '{item.raw_question}', attempt {i + 1}")
                    try:
                        return await self.rollout_one(item)
                    except Exception as e:  # pylint: disable=broad-except
                        logger.error(
                            f">>>>>>>>>>>>>\nError running rollout on sample '{item.raw_question}': {e}\n<<<<<<<<<<<<<",
                            exc_info=True,
                        )

        tasks = [rollout_with_semaphore(item) for item in samples]
        results = []
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Rolling out"):
            result = await task
            if result is not None:
                results.append(result)
        logger.info(f"Successfully rollout {len(results)} samples. Updated to db.")
        return results

    @staticmethod
    def _prepare_rollout_agent_config(sample: EvaluationSample, base_agent_config):
        """Copy per-sample toolkit state and inject the current paper's DOI mask."""
        agent_config = base_agent_config
        masked_doc_ids: list[str] = []
        try:
            meta = sample.meta or {}
            task_type = str(
                meta.get("task_type") or meta.get("property_type") or meta.get("reaction_type") or ""
            ).strip()
            sample_id = meta.get("sample_id")
            if sample_id is None:
                sample_id = meta.get("id")

            # New 19-direction records carry doc_id directly and use task_type/sample_id.
            # Older chem-performance datasets can still fall back to their TSV resolver.
            doc_id = str(meta.get("doc_id") or "").strip() or None
            if not doc_id and task_type and sample_id is not None and sample.dataset:
                doc_id = CHEM_PERF_DOC_ID_RESOLVER.resolve_doc_id(
                    dataset=str(sample.dataset),
                    reaction_type=task_type,
                    sample_id=sample_id,
                )
            if doc_id:
                masked_doc_ids = [doc_id]

                # Rollouts are concurrent. Never mutate the shared evaluation config with
                # one sample's DOI mask.
                if "chem_literature_db" in (agent_config.toolkits or {}):
                    agent_config = agent_config.model_copy(deep=True)
                    tk = agent_config.toolkits.get("chem_literature_db")
                    if tk is not None:
                        raw_cfg = dict(tk.config or {})
                        masked = raw_cfg.get("masked_doc_ids")
                        if isinstance(masked, list):
                            masked_list = [str(x) for x in masked if str(x).strip()]
                        elif masked:
                            masked_list = [str(masked)]
                        else:
                            masked_list = []
                        if doc_id not in masked_list:
                            masked_list.append(doc_id)
                        raw_cfg["masked_doc_ids"] = masked_list
                        tk.config = raw_cfg
        except Exception as e:  # pylint: disable=broad-except
            # Masking resolution should not hide the underlying rollout error path.
            logger.warning(f"Leakage-masking injection skipped due to error: {e}")
        return agent_config, masked_doc_ids

    @staticmethod
    def _build_single_agent_tools(agent_config) -> list:
        tools = []
        for config_name, toolkit_config in (agent_config.toolkits or {}).items():
            enabled = (toolkit_config.config or {}).get("enabled", True)
            if isinstance(enabled, str):
                enabled = enabled.strip().lower() not in {"0", "false", "no", "off"}
            if not enabled:
                continue
            if toolkit_config.mode != "builtin":
                raise RuntimeError(
                    "Single-agent rollout only supports builtin toolkits in this extracted repo; "
                    f"got mode={toolkit_config.mode!r} for {config_name!r}."
                )
            toolkit_name = str(toolkit_config.name or config_name).strip()
            toolkit_cls = TOOLKIT_MAP.get(toolkit_name)
            if toolkit_cls is None:
                raise RuntimeError(
                    f"Unknown single-agent toolkit {toolkit_name!r}; available={sorted(TOOLKIT_MAP)}"
                )
            tools.extend(toolkit_cls(config=toolkit_config).get_tools_in_agents())
        return tools

    async def _run_single_agent(self, *, question: str, agent_config) -> tuple[str, list[dict]]:
        if agent_config.type != "simple":
            raise RuntimeError(
                f"Unsupported non-MAD rollout agent type {agent_config.type!r}; expected type='simple'."
            )

        provider = agent_config.model.model_provider
        model = AgentsUtils.get_agents_model(
            type=provider.type,
            model=provider.model,
            base_url=provider.base_url,
            api_key=provider.api_key,
        )
        tool_use_behavior = "run_llm_again"
        if agent_config.stop_at_tool_names:
            tool_use_behavior = {"stop_at_tool_names": list(agent_config.stop_at_tool_names)}

        agent = Agent(
            name=agent_config.agent.name or "material_performance_agent",
            instructions=agent_config.agent.instructions,
            model=model,
            model_settings=agent_config.model.model_settings,
            tools=self._build_single_agent_tools(agent_config),
            tool_use_behavior=tool_use_behavior,
        )
        result = await Runner.run(
            starting_agent=agent,
            input=question,
            context={},
            max_turns=agent_config.max_turns,
            hooks=get_run_hooks(agent_config),
        )
        final_output = "" if result.final_output is None else str(result.final_output)
        return final_output, [AgentsUtils.get_trajectory_from_agent_result(result)]

    async def rollout_one(self, sample: EvaluationSample) -> EvaluationSample:
        agent_config, masked_doc_ids = self._prepare_rollout_agent_config(sample, self.config.agent)

        # Retained for explicit evaluation/legacy configs. TrainingFreeGRPO rejects MAD configs.
        env_name = (agent_config.env.name or "").strip().lower() if agent_config.env else ""
        if env_name == "mad":
            trace_id = AgentsUtils.gen_trace_id()
            start_time = time.time()

            engine_cfg = MADEngineConfig.model_validate(agent_config.env.config or {})
            logger.info(
                "Using external rollout engine: MAD "
                f"(python_bin={engine_cfg.python_bin!r}, mad_repo_path={engine_cfg.mad_repo_path!r})"
            )
            adapter = MADEngineAdapter(engine_cfg)
            engine_result = await adapter.run(
                question=sample.augmented_question,
                meta=sample.meta or {},
                masked_doc_ids=masked_doc_ids,
            )

            end_time = time.time()
            sample.update(
                trace_id=trace_id,
                response=engine_result.final_output,
                time_cost=end_time - start_time,
                trajectories=json.dumps(engine_result.trajectories, ensure_ascii=False),
                stage="rollout",
            )
            self.dataset.save(sample)
            return sample

        trace_id = AgentsUtils.gen_trace_id()
        start_time = time.time()
        response, trajectories = await self._run_single_agent(
            question=sample.augmented_question,
            agent_config=agent_config,
        )
        end_time = time.time()
        sample.update(
            trace_id=trace_id,
            response=response,
            time_cost=end_time - start_time,
            trajectories=json.dumps(trajectories, ensure_ascii=False),
            stage="rollout",
        )
        self.dataset.save(sample)
        return sample

    async def judge(self, stage: str | None = "rollout") -> list[EvaluationSample]:
        """Judge samples.

        Args:
            stage (str|None, optional): The stage of samples to judge. If set to None, you can rejudge all samples.
        """
        if stage == "rollout":
            num_init_samples = len(self.dataset.get_samples(stage="init"))
            if num_init_samples > 0:
                logger.error(
                    f"There are {num_init_samples} samples might failed unexpectedly in rollout stage."
                    "Please rerun the benchmarking to continue for final results."
                )
                exit(1)
        samples = self.dataset.get_samples(stage=stage)
        logger.info(f"Judging {len(samples)} samples...")

        semaphore = asyncio.Semaphore(self.config.judge_concurrency)

        async def judge_with_semaphore(item: EvaluationSample):
            async with semaphore:
                try:
                    return await self.judge_one(item)
                except Exception as e:  # pylint: disable=broad-except
                    logger.error(f">>>>>>>>>>>>>\nError judging sample '{item}': {e}\n<<<<<<<<<<<<<", exc_info=True)
                    return None

        tasks = [judge_with_semaphore(item) for item in samples]
        results = []
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Judging"):
            result = await task
            if result is not None:
                results.append(result)
        logger.info(f"Successfully judged {len(results)} samples. Updated to db.")
        return results

    async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
        judger = self._get_processer(data.source)
        result = await judger.judge_one(data)
        result.update(stage="judged")  # update stage to judged
        self.dataset.save(result)
        return result

    async def stat(self) -> list[dict]:
        # TODO: wrap the data like @verl / @torch
        # TODO: log to wandb
        judged_samples = self.dataset.get_samples(stage="judged")
        logger.info(f"Stat from {len(judged_samples)} samples:")

        data_by_benchmark = self._group_data_by_benchmark(judged_samples)
        overall_results: list[dict] = []
        for benchmark, data in data_by_benchmark.items():
            evaluator = self._get_processer(benchmark)
            result = await evaluator.stat(data)
            overall_results.append(result)

        logger.info(json.dumps(overall_results, indent=4, ensure_ascii=False))
        return overall_results

    def _get_processer(self, source: str) -> BaseProcesser:
        if source not in self._source_to_processer:
            processer = PROCESSER_FACTORY.get(source, self.config)
            self._source_to_processer[source] = processer
        return self._source_to_processer[source]

    def _group_data_by_benchmark(self, predict_data: list[EvaluationSample]) -> dict[str, list[EvaluationSample]]:
        # group data by benchmark
        data_by_benchmark: dict[str, list[EvaluationSample]] = {}
        for data in predict_data:
            benchmark = data.source
            if benchmark not in data_by_benchmark:
                data_by_benchmark[benchmark] = []
            data_by_benchmark[benchmark].append(data)
        return data_by_benchmark

    async def cleanup(self):
        pass
