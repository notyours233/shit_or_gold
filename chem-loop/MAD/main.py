"""
===================================
Multi-Agent Debate System 
===================================

Functionality:
1. Initialize system components 
2. Execute multi-agent debate
3. Generate result reports

===================================
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Any, List, Optional, Dict

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

from utils import (
    load_config,
    setup_logging,
    DebateLogger,
    parse_component_string,
    validate_components,
    print_header,
    print_section,
    dict_to_table,
    format_duration,
    save_json,
    ensure_dir
)
from database import RAGSystem
from database.embedder import MultiModelEmbedder
from agents import AgentConfig
from agents.llm_agents import create_agent
from experience import ExperienceStore
from debate.langgraph_coordinator import LangGraphDebateCoordinator
from utils.task_types import (
    TASK_FAMILY_MATERIAL,
    TASK_FAMILY_REACTION,
    UNIFIED_TASK_TYPES,
    canonical_task_or_raw,
    canonical_task_type,
    task_family,
)
from utils.material_input import MaterialInput


def _resolve_material_input(
    components: Optional[List[str]],
    material_input: Optional[MaterialInput | Dict[str, Any]],
) -> MaterialInput:
    if isinstance(material_input, MaterialInput):
        return material_input
    if isinstance(material_input, dict):
        return MaterialInput.from_mapping(material_input)
    return MaterialInput.from_legacy_components(components or [])


def _extract_debate_error(result_dict: Dict[str, Any]) -> Optional[str]:
    """Summarize debate-level provider/schema failures for ranking output."""
    if not isinstance(result_dict, dict):
        return "invalid debate result"
    if result_dict.get("final_performance") or result_dict.get("performance_evaluation"):
        return None

    details = result_dict.get("resolution_details")
    if isinstance(details, dict) and details.get("error") == "no_active_proposals":
        errors: List[str] = []
        for item in details.get("withdrawn_errors") or []:
            if not isinstance(item, dict):
                continue
            agent = str(item.get("agent_name") or item.get("proposal_id") or "").strip()
            err = str(item.get("error") or "").strip()
            if err:
                errors.append(f"{agent}: {err}" if agent else err)
        if errors:
            return "all proposals withdrawn; " + " | ".join(errors)
        return "all proposals withdrawn before a usable performance estimate was produced"

    surviving = result_dict.get("surviving_proposals") or []
    if isinstance(surviving, list) and not surviving:
        withdrawn = result_dict.get("withdrawn_proposals") or []
        errors = []
        if isinstance(withdrawn, list):
            for item in withdrawn:
                if not isinstance(item, dict):
                    continue
                err = str(item.get("last_call_error") or "").strip()
                if err:
                    errors.append(err)
        if errors:
            return "no active proposals; " + " | ".join(errors)
        return "no active proposals"

    return None


def _resolve_rag_storage_config(vector_config: Dict[str, Any]) -> tuple[str, str, str, str]:
    """Resolve material/reaction Chroma directories and collection base names."""
    cfg = vector_config or {}
    material_persist_dir = (
        os.getenv("MAD_RAG_MATERIAL_PERSIST_DIR")
        or os.getenv("MAD_RAG_PERSIST_DIR")
        or cfg.get("material_persist_directory")
        or cfg.get("persist_directory")
        or "./data/chroma_db"
    )
    reaction_persist_dir = (
        os.getenv("MAD_RAG_REACTION_PERSIST_DIR")
        or cfg.get("reaction_persist_directory")
        or cfg.get("reaction_persist_dir")
        or material_persist_dir
    )

    base_collection_name = cfg.get("collection_name", "chemical_reactions_recommendation")
    collection_names_cfg = cfg.get("collection_names") or {}
    material_collection_base = (
        os.getenv("MAD_RAG_MATERIAL_COLLECTION")
        or collection_names_cfg.get(TASK_FAMILY_MATERIAL)
        or collection_names_cfg.get("material")
        or collection_names_cfg.get("material_property")
        or base_collection_name
    )
    reaction_collection_base = (
        os.getenv("MAD_RAG_REACTION_COLLECTION")
        or collection_names_cfg.get(TASK_FAMILY_REACTION)
        or collection_names_cfg.get("reaction")
        or material_collection_base
    )
    return (
        str(material_persist_dir),
        str(reaction_persist_dir),
        str(material_collection_base),
        str(reaction_collection_base),
    )


class MADSystem:
    """
    Multi-Agent Debate System Main Class
    Integrates all components and provides a unified interface for running the system.
    Evaluates a named material against one or more requested performance directions.
    """
    
    def __init__(self, config_path: str = "./config/config.yaml", default_engine: str = "langgraph"):
        """
        Initialize MADSystem with configuration and default debate engine
        
        Args:
            config_path: Path to configuration file
            default_engine: Default debate engine to use "langgraph"
        """
        print_header("Multi-Agent Debate System")
        print("Initializing system...")
        
        self.config = load_config(config_path)
        
        # Initialize logging
        self.logger = setup_logging(self.config)
        self.logger.info("System initialization started")
        
        # Initialize components
        self.rag_systems = {}
        self.rag_systems_by_family = {}
        self.agents = []
        self.experience_store = None
        self.debate_coordinator = None
        self.langgraph_debate_coordinator = None
        self.default_engine = default_engine
        
        # Initialization flag
        self._initialized = False
    
    def initialize(self) -> None:
        """
        Initialize all system components
        """
        if self._initialized:
            self.logger.warning("System already initialized, skipping re-initialization")
            return
        
        try:
            # 1. Initialize RAG systems (required)
            self._init_rag_systems()

            # 2. Initialize Experience Store (for `search_experience`)
            self._init_experience_store()
            
            # 3. Initialize Agents
            self._init_agents()
            
            # 4. Initialize debate coordinators
            self._init_debate_coordinators()
            
            self._initialized = True
            self.logger.info("System initialization completed")
            print("\n✓ System initialized successfully\n")
            
        except Exception as e:
            self.logger.error(f"System initialization failed: {str(e)}", exc_info=True)
            print(f"\n✗ System initialization failed: {str(e)}\n")
            raise
    
    def _init_experience_store(self) -> None:
        """Initialize experience store (YAML packs + optional JSON dynamic store)."""
        exp_cfg = self.config.get("experience", {}) or {}
        storage_path = exp_cfg.get("storage_path", "./data/experience_db.json")
        packs_path = exp_cfg.get("packs_path", "./experience")
        max_exps = int(exp_cfg.get("max_experiences", 1000))
        threshold = float(exp_cfg.get("relevance_threshold", 0.8))
        guideline_top_k = int(exp_cfg.get("guideline_top_k", 3))
        always_include_guidelines = bool(exp_cfg.get("always_include_guidelines", True))
        guideline_search_mode = exp_cfg.get("guideline_search_mode", "keyword")
        load_builtin_packs = bool(exp_cfg.get("load_builtin_packs", True))
        experience_search_mode = exp_cfg.get("search_mode") or exp_cfg.get("experience_search_mode")
        embedding_provider = exp_cfg.get("embedding_provider")
        embedding_model = exp_cfg.get("embedding_model")
        embedding_hash_dim = exp_cfg.get("embedding_hash_dim")
        embedding_cache_path = exp_cfg.get("embedding_cache_path")

        self.experience_store = ExperienceStore(
            storage_path=storage_path,
            packs_path=packs_path,
            max_experiences=max_exps,
            relevance_threshold=threshold,
            guideline_top_k=guideline_top_k,
            always_include_guidelines=always_include_guidelines,
            guideline_search_mode=guideline_search_mode,
            load_builtin_packs=load_builtin_packs,
            experience_search_mode=experience_search_mode,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_hash_dim=embedding_hash_dim,
            embedding_cache_path=embedding_cache_path,
        )
        self.logger.info(
            "ExperienceStore initialized: storage_path=%s packs_path=%s total=%s",
            storage_path,
            packs_path,
            len(getattr(self.experience_store, "experiences", []) or []),
        )
    
    def _init_rag_systems(self) -> None:
        """Initialize RAG retrieval adapters (Chroma/VectorStore-backed)."""
        enable_rag = (os.getenv("MAD_ENABLE_RAG", "1") or "1").strip().lower() not in ("0", "false", "no")
        if not enable_rag:
            print("Initializing RAG systems... (disabled via MAD_ENABLE_RAG=0)")
            self.rag_systems = {}
            self.logger.info("RAG systems disabled via MAD_ENABLE_RAG=0")
            return

        print("Initializing RAG systems...")
        rag_config = self.config.get('rag', {})
        vector_config = self.config.get('vector_store', {})

        material_persist_dir, reaction_persist_dir, material_collection_base, reaction_collection_base = (
            _resolve_rag_storage_config(vector_config)
        )
        distance_metric = vector_config.get('distance_metric', 'cosine')

        top_k = rag_config.get('top_k', 5)
        similarity_threshold = rag_config.get('similarity_threshold', None)

        # Build a shared embedder that knows each agent's embedding profile.
        agent_config = AgentConfig(self.config)
        agent_keys = ["agent1", "agent2", "agent3", "agent4"]
        all_agent_configs = {k: agent_config.get_llm_config(k) for k in agent_keys}
        embedder = MultiModelEmbedder(all_agent_configs["agent1"], agent_configs=all_agent_configs)

        # RAG mode:
        # - per_agent (default): one collection per agent (matches build_vector_db.py: <base>_<agentX>)
        # - shared: all agents share ONE collection + ONE embedding profile (reduces memory when Chroma is huge)
        rag_mode = (os.getenv("MAD_RAG_MODE") or "").strip().lower() or str(rag_config.get("mode") or "").strip().lower()
        rag_mode = rag_mode or "per_agent"

        self.rag_systems = {}
        self.rag_systems_by_family = {TASK_FAMILY_MATERIAL: {}, TASK_FAMILY_REACTION: {}}
        if rag_mode == "shared":
            shared_agent = (os.getenv("MAD_RAG_SHARED_AGENT") or "").strip().lower() or "agent2"
            if shared_agent not in agent_keys:
                shared_agent = "agent2"
            shared_collection = (os.getenv("MAD_RAG_SHARED_COLLECTION") or "").strip()
            if not shared_collection:
                shared_collection = f"{material_collection_base}_{shared_agent}"
            material_shared_collection = (
                os.getenv("MAD_RAG_SHARED_MATERIAL_COLLECTION") or shared_collection
            ).strip()
            reaction_shared_collection = (
                os.getenv("MAD_RAG_SHARED_REACTION_COLLECTION") or ""
            ).strip()
            if not reaction_shared_collection and reaction_collection_base:
                reaction_shared_collection = f"{reaction_collection_base}_{shared_agent}"

            print(
                f"  RAG mode=shared (MAD_RAG_MODE=shared): material_collection={material_shared_collection} embedder_agent={shared_agent}"
            )

            rag_system = RAGSystem(
                persist_dir=material_persist_dir,
                collection_name=material_shared_collection,
                embedder=embedder,
                agent_name=shared_agent,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                distance_metric=distance_metric,
            )

            for agent_key in agent_keys:
                # All agents reuse the same adapter; retrieval uses the shared embedding profile.
                self.rag_systems[agent_key] = rag_system
                self.rag_systems_by_family[TASK_FAMILY_MATERIAL][agent_key] = rag_system

            if reaction_shared_collection:
                print(f"  RAG reaction collection={reaction_shared_collection} embedder_agent={shared_agent}")
                reaction_rag = RAGSystem(
                    persist_dir=reaction_persist_dir,
                    collection_name=reaction_shared_collection,
                    embedder=embedder,
                    agent_name=shared_agent,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold,
                    distance_metric=distance_metric,
                )
                for agent_key in agent_keys:
                    self.rag_systems_by_family[TASK_FAMILY_REACTION][agent_key] = reaction_rag
            else:
                print("  RAG reaction collection not configured; reaction literature retrieval will return empty.")
        else:
            # One collection per agent (high recall, higher memory footprint).
            for agent_key in agent_keys:
                collection_name = f"{material_collection_base}_{agent_key}"
                print(f"  Creating RAG adapter for {agent_key}, using collection: {collection_name}")

                rag_system = RAGSystem(
                    persist_dir=material_persist_dir,
                    collection_name=collection_name,
                    embedder=embedder,
                    agent_name=agent_key,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold,
                    distance_metric=distance_metric,
                )
                self.rag_systems[agent_key] = rag_system
                self.rag_systems_by_family[TASK_FAMILY_MATERIAL][agent_key] = rag_system

                if reaction_collection_base:
                    reaction_collection = f"{reaction_collection_base}_{agent_key}"
                    print(f"  Creating reaction RAG adapter for {agent_key}, using collection: {reaction_collection}")
                    self.rag_systems_by_family[TASK_FAMILY_REACTION][agent_key] = RAGSystem(
                        persist_dir=reaction_persist_dir,
                        collection_name=reaction_collection,
                        embedder=embedder,
                        agent_name=agent_key,
                        top_k=top_k,
                        similarity_threshold=similarity_threshold,
                        distance_metric=distance_metric,
                    )
            if not reaction_collection_base:
                print("  RAG reaction collection not configured; reaction literature retrieval will return empty.")

        self.logger.info("RAG systems initialization completed")
    
    def _init_agents(self) -> None:
        """Initialize Agents"""
        print("Initializing Agents...")

        agent_config = AgentConfig(self.config)

        agent_specs = [
            ("agent1", "GPT Researcher", "agent1"),
            ("agent2", "DeepSeek Researcher", "agent2"),
            ("agent3", "Gemini Researcher", "agent3"),
            ("agent4", "Qwen Researcher", "agent4")
        ]

        self.agents = []
        for agent_key, agent_name, provider_key in agent_specs:
            model_config = agent_config.get_llm_config(agent_key)
            rag_system = self.rag_systems.get(provider_key)
            rag_systems_by_family = {
                family: systems.get(provider_key)
                for family, systems in (self.rag_systems_by_family or {}).items()
                if isinstance(systems, dict) and systems.get(provider_key) is not None
            }

            agent = create_agent(
                agent_type=model_config.get("provider", "openai"),
                agent_id=agent_key,
                name=agent_name,
                model_config=model_config,
                rag_system=rag_system,
                rag_systems_by_family=rag_systems_by_family,
                experience_store=self.experience_store
            )

            self.agents.append(agent)
            print(f"✓ Successfully created Agent: {agent_name} ({provider_key})")

        if not self.agents:
            raise RuntimeError("No Agents were successfully created")

        self.logger.info(f"Successfully initialized {len(self.agents)} Agents")
    
    def _init_debate_coordinators(self) -> None:
        """Initialize debate coordinator(s) (LangGraph-style only)."""
        print("Initializing debate coordinator...")

        debate_config = self.config.get('debate', {})

        # LangGraph-style coordinator (implemented in-repo; no external dependency required).
        self.langgraph_debate_coordinator = LangGraphDebateCoordinator(
            agents=self.agents,
            config=debate_config
        )

        # Default engine points to LangGraph coordinator
        self.debate_coordinator = self.langgraph_debate_coordinator
        
    
    def run_debate(
        self,
        components: Optional[List[str]] = None,
        reaction_type: Optional[str] = None,
        save_result: bool = True,
        engine: Optional[str] = None,
        material_input: Optional[MaterialInput | Dict[str, Any]] = None,
    ) -> dict:
        """
        Run debate
        
        Args:
            components: Legacy retrieval-element input. New callers should use `material_input`.
            save_result: Whether to save results
        
        Returns:
            dict: Debate results
        """
        if not self._initialized:
            raise RuntimeError("System not initialized, please call initialize() first")

        from prompts.debate_phase_prompts import build_initial_debate_prompt

        material = _resolve_material_input(components, material_input)
        elements = material.retrieval_elements()
        material_description = material.build_material_description()
        
        if reaction_type:
            self.logger.info(
                "Starting debate with task type %s and material=%s",
                reaction_type,
                material.material_name,
            )
        else:
            self.logger.info("Starting debate with material=%s", material.material_name)
        
        # Create debate logger
        debate_logger = DebateLogger()
        debate_logger.log_debate_start(elements, self.config.get('debate', {}))
        
        # Only LangGraph-style engine is supported.
        selected_engine = "langgraph"
        if engine and str(engine).strip().lower() != "langgraph":
            raise ValueError(f"Unsupported debate engine: {engine}. Only 'langgraph' is supported.")
        coordinator = self.langgraph_debate_coordinator or self.debate_coordinator

        if coordinator is None:
            raise RuntimeError(f"Debate coordinator for engine '{selected_engine}' is not initialized")

        # Run debate
        initial_prompt = build_initial_debate_prompt(
            elements,
            reaction_type=reaction_type,
            material_input=material,
        )
        result = coordinator.start_debate(elements, initial_prompt=initial_prompt, reaction_type=reaction_type)
        result_dict = result.to_dict()
        result_dict["engine"] = selected_engine
        result_dict["material_name"] = material.material_name
        result_dict["material_description"] = material_description
        result_dict["material_input"] = material.to_dict()

        # Performance grading (only when there is a single final conclusion).
        # - Prefer `final_performance` if present.
        # - Otherwise, if there is exactly one surviving proposal, grade its claim.
        # - Otherwise, leave as N/A (no field).
        try:
            from utils.performance_grading import evaluate_claim

            final_claim = None
            fp = result_dict.get("final_performance")
            if isinstance(fp, str) and fp.strip():
                final_claim = fp
            else:
                surviving = result_dict.get("surviving_proposals") or []
                if isinstance(surviving, list) and len(surviving) == 1:
                    claim = (surviving[0] or {}).get("claim") if isinstance(surviving[0], dict) else None
                    if isinstance(claim, str) and claim.strip():
                        final_claim = claim

            perf_eval = evaluate_claim(final_claim, reaction_type=reaction_type) if final_claim else None
            if perf_eval:
                result_dict["performance_evaluation"] = perf_eval
        except Exception as e:
            # Never break debate completion on grading errors.
            self.logger.warning("Performance evaluation failed: %s", str(e))
        
        # Log debate end
        debate_logger.log_debate_end(result_dict)
        
        # Save results
        if save_result:
            self._save_result(
                result,
                elements,
                material_input=material,
                engine=selected_engine,
                performance_evaluation=result_dict.get("performance_evaluation"),
                reaction_type=reaction_type,
            )
        
        self.logger.info("Debate completed")
        
        return result_dict

    def run_rank_tasks(
        self,
        components: Optional[List[str]] = None,
        task_types: Optional[List[str]] = None,
        top_k: int = 2,
        max_parallel_tasks: int = 1,
        save_each_task: bool = False,
        material_input: Optional[MaterialInput | Dict[str, Any]] = None,
    ) -> Dict:
        """
        Run one isolated four-agent debate per task and return a Top-K task summary.

        The outer loop may schedule one, a subset, or all 19 directions. Each
        inner debate always receives exactly one ``task_type``. Cross-direction
        ordering uses task-specific grades and normalized within-grade scores;
        raw values with different units are never compared directly.

        Notes:
        - Per-task ``outputs/result_*.json`` files are saved only when ``save_each_task=True``.
        - Parallel tasks use fresh agents/coordinators to avoid shared debate state.
        """
        if not self._initialized:
            raise RuntimeError("System not initialized, please call initialize() first")

        material = _resolve_material_input(components, material_input)
        elements = material.retrieval_elements()
        material_description = material.build_material_description()

        # Resolve property/application types: explicit arg > config.yaml > built-in fallback.
        rt_list: List[str] = []
        if task_types is not None:
            rt_list = [canonical_task_or_raw(x) for x in task_types if str(x).strip()]
        else:
            chem_cfg = ((self.config or {}).get("chemistry", {}) or {})
            cfg_rts = chem_cfg.get("task_types") or chem_cfg.get("reaction_types") or chem_cfg.get("property_types") or []
            if isinstance(cfg_rts, list) and cfg_rts:
                rt_list = [canonical_task_or_raw(x) for x in cfg_rts if str(x).strip()]
        if not rt_list:
            raise ValueError("task_types must contain at least one task direction")
        # De-duplicate while preserving order (avoid re-running the same task twice).
        seen_rt: set[str] = set()
        rt_dedup: List[str] = []
        for rt in rt_list:
            s = canonical_task_or_raw(rt)
            if not s or s in seen_rt:
                continue
            seen_rt.add(s)
            rt_dedup.append(s)
        rt_list = rt_dedup

        # Clamp and sanitize.
        try:
            k_final = int(top_k)
        except Exception:
            k_final = 2
        k_final = min(len(rt_list), max(1, k_final))
        try:
            max_par = int(max_parallel_tasks)
        except Exception:
            max_par = 1
        max_par = min(len(rt_list), max(1, max_par))

        debate_config = (self.config.get("debate", {}) or {}).copy()

        def _extract_perf_fields(result_dict: Dict) -> Dict[str, Any]:
            pe = result_dict.get("performance_evaluation") if isinstance(result_dict, dict) else None
            out: Dict[str, Any] = {"performance_evaluation": pe if isinstance(pe, dict) else None}
            if isinstance(pe, dict):
                out["metric_value"] = pe.get("metric_value")
                out["metric_unit"] = pe.get("metric_unit")
                out["grade"] = pe.get("grade")
            else:
                out["metric_value"] = None
                out["metric_unit"] = None
                out["grade"] = None
            return out

        def _run_debate_with_coordinator(
            coordinator: LangGraphDebateCoordinator,
            reaction_type: str,
            save_result: bool,
        ) -> Dict[str, Any]:
            from prompts.debate_phase_prompts import build_initial_debate_prompt

            rt = canonical_task_or_raw(reaction_type) or "UNKNOWN"

            if rt and rt != "UNKNOWN":
                self.logger.info(
                    "Starting debate (isolated) with task type %s and material=%s",
                    rt,
                    material.material_name,
                )
            else:
                self.logger.info("Starting debate (isolated) with material=%s", material.material_name)

            debate_logger = DebateLogger()
            debate_logger.log_debate_start(elements, debate_config)

            initial_prompt = build_initial_debate_prompt(
                elements,
                reaction_type=rt,
                material_input=material,
            )
            result = coordinator.start_debate(elements, initial_prompt=initial_prompt, reaction_type=rt)

            result_dict = result.to_dict()
            result_dict["engine"] = "langgraph"
            result_dict["material_name"] = material.material_name
            result_dict["material_description"] = material_description
            result_dict["material_input"] = material.to_dict()

            # Attach performance grading if we can extract a final claim.
            try:
                from utils.performance_grading import evaluate_claim

                final_claim = None
                fp = result_dict.get("final_performance")
                if isinstance(fp, str) and fp.strip():
                    final_claim = fp
                else:
                    surviving = result_dict.get("surviving_proposals") or []
                    if isinstance(surviving, list) and len(surviving) == 1:
                        claim = (surviving[0] or {}).get("claim") if isinstance(surviving[0], dict) else None
                        if isinstance(claim, str) and claim.strip():
                            final_claim = claim

                perf_eval = evaluate_claim(final_claim, reaction_type=rt) if final_claim else None
                if perf_eval:
                    result_dict["performance_evaluation"] = perf_eval
            except Exception as e:
                self.logger.warning("Performance evaluation failed: %s", str(e))

            debate_logger.log_debate_end(result_dict)

            if save_result:
                self._save_result(
                    result,
                    elements,
                    material_input=material,
                    engine="langgraph",
                    performance_evaluation=result_dict.get("performance_evaluation"),
                    reaction_type=rt,
                )

            return result_dict

        def _build_isolated_coordinator() -> LangGraphDebateCoordinator:
            """
            Build a fresh coordinator (fresh agents) for safe parallel per-reaction execution.
            """
            # Reduce inner concurrency when outer reaction-level parallelism is enabled to mitigate API rate limits.
            local_cfg = dict(debate_config or {})
            if max_par > 1:
                inner_cap = 1 if max_par > 3 else 2
                try:
                    current_inner = int(local_cfg.get("max_concurrency", 4))
                except Exception:
                    current_inner = 4
                local_cfg["max_concurrency"] = max(1, min(current_inner, inner_cap))

            # Create fresh RAG systems to avoid sharing a Chroma collection object across threads.
            rag_config = self.config.get("rag", {}) or {}
            vector_config = self.config.get("vector_store", {}) or {}
            material_persist_dir, reaction_persist_dir, material_collection_base, reaction_collection_base = (
                _resolve_rag_storage_config(vector_config)
            )
            distance_metric = vector_config.get("distance_metric", "cosine")
            top_k_rag = rag_config.get("top_k", 5)
            similarity_threshold = rag_config.get("similarity_threshold", None)

            # Prefer reusing the already-initialized embedder (it knows per-agent embedding profiles).
            embedder = None
            try:
                if self.rag_systems:
                    embedder = next(iter(self.rag_systems.values())).embedder
            except Exception:
                embedder = None
            if embedder is None:
                agent_config = AgentConfig(self.config)
                agent_keys = ["agent1", "agent2", "agent3", "agent4"]
                all_agent_configs = {k: agent_config.get_llm_config(k) for k in agent_keys}
                embedder = MultiModelEmbedder(all_agent_configs["agent1"], agent_configs=all_agent_configs)

            rag_systems_local: Dict[str, Any] = {}
            rag_systems_local_by_family: Dict[str, Dict[str, Any]] = {
                TASK_FAMILY_MATERIAL: {},
                TASK_FAMILY_REACTION: {},
            }
            enable_rag = (os.getenv("MAD_ENABLE_RAG", "1") or "1").strip().lower() not in ("0", "false", "no")
            rag_mode = (os.getenv("MAD_RAG_MODE") or "").strip().lower() or str(rag_config.get("mode") or "").strip().lower()
            rag_mode = rag_mode or "per_agent"

            if enable_rag:
                if rag_mode == "shared":
                    shared_agent = (os.getenv("MAD_RAG_SHARED_AGENT") or "").strip().lower() or "agent2"
                    if shared_agent not in ["agent1", "agent2", "agent3", "agent4"]:
                        shared_agent = "agent2"
                    shared_collection = (os.getenv("MAD_RAG_SHARED_COLLECTION") or "").strip()
                    if not shared_collection:
                        shared_collection = f"{material_collection_base}_{shared_agent}"
                    material_shared_collection = (
                        os.getenv("MAD_RAG_SHARED_MATERIAL_COLLECTION") or shared_collection
                    ).strip()
                    reaction_shared_collection = (
                        os.getenv("MAD_RAG_SHARED_REACTION_COLLECTION") or ""
                    ).strip()
                    if not reaction_shared_collection and reaction_collection_base:
                        reaction_shared_collection = f"{reaction_collection_base}_{shared_agent}"

                    rag_system = RAGSystem(
                        persist_dir=material_persist_dir,
                        collection_name=material_shared_collection,
                        embedder=embedder,
                        agent_name=shared_agent,
                        top_k=top_k_rag,
                        similarity_threshold=similarity_threshold,
                        distance_metric=distance_metric,
                    )
                    for agent_key in ["agent1", "agent2", "agent3", "agent4"]:
                        rag_systems_local[agent_key] = rag_system
                        rag_systems_local_by_family[TASK_FAMILY_MATERIAL][agent_key] = rag_system
                    if reaction_shared_collection:
                        reaction_rag = RAGSystem(
                            persist_dir=reaction_persist_dir,
                            collection_name=reaction_shared_collection,
                            embedder=embedder,
                            agent_name=shared_agent,
                            top_k=top_k_rag,
                            similarity_threshold=similarity_threshold,
                            distance_metric=distance_metric,
                        )
                        for agent_key in ["agent1", "agent2", "agent3", "agent4"]:
                            rag_systems_local_by_family[TASK_FAMILY_REACTION][agent_key] = reaction_rag
                else:
                    for agent_key in ["agent1", "agent2", "agent3", "agent4"]:
                        collection_name = f"{material_collection_base}_{agent_key}"
                        material_rag = RAGSystem(
                            persist_dir=material_persist_dir,
                            collection_name=collection_name,
                            embedder=embedder,
                            agent_name=agent_key,
                            top_k=top_k_rag,
                            similarity_threshold=similarity_threshold,
                            distance_metric=distance_metric,
                        )
                        rag_systems_local[agent_key] = material_rag
                        rag_systems_local_by_family[TASK_FAMILY_MATERIAL][agent_key] = material_rag
                        if reaction_collection_base:
                            rag_systems_local_by_family[TASK_FAMILY_REACTION][agent_key] = RAGSystem(
                                persist_dir=reaction_persist_dir,
                                collection_name=f"{reaction_collection_base}_{agent_key}",
                                embedder=embedder,
                                agent_name=agent_key,
                                top_k=top_k_rag,
                                similarity_threshold=similarity_threshold,
                                distance_metric=distance_metric,
                            )

            agent_config = AgentConfig(self.config)
            agent_specs = [
                ("agent1", "GPT Researcher", "agent1"),
                ("agent2", "DeepSeek Researcher", "agent2"),
                ("agent3", "Gemini Researcher", "agent3"),
                ("agent4", "Qwen Researcher", "agent4"),
            ]

            agents_local = []
            for agent_key, agent_name, provider_key in agent_specs:
                model_config = agent_config.get_llm_config(agent_key)
                rag_system = rag_systems_local.get(provider_key)
                rag_systems_by_family = {
                    family: systems.get(provider_key)
                    for family, systems in rag_systems_local_by_family.items()
                    if isinstance(systems, dict) and systems.get(provider_key) is not None
                }
                agent = create_agent(
                    agent_type=model_config.get("provider", "openai"),
                    agent_id=agent_key,
                    name=agent_name,
                    model_config=model_config,
                    rag_system=rag_system,
                    rag_systems_by_family=rag_systems_by_family,
                    experience_store=self.experience_store,
                )
                agents_local.append(agent)

            return LangGraphDebateCoordinator(agents=agents_local, config=local_cfg)

        def _run_one_reaction(rt: str) -> Dict[str, Any]:
            """
            Run one reaction (with optional retry) and return a summary dict.
            """
            import time

            reaction = canonical_task_or_raw(rt)
            family = task_family(reaction)
            attempts = 2  # best-effort retry for transient 429/rate-limit type failures
            last_err = None

            for attempt in range(attempts):
                try:
                    if max_par <= 1:
                        res = self.run_debate(
                            components,
                            reaction_type=reaction,
                            save_result=bool(save_each_task),
                            engine="langgraph",
                            material_input=material,
                        )
                    else:
                        coord = _build_isolated_coordinator()
                        res = _run_debate_with_coordinator(
                            coord,
                            reaction_type=reaction,
                            save_result=bool(save_each_task),
                        )

                    perf_fields = _extract_perf_fields(res if isinstance(res, dict) else {})
                    prop = reaction if family == TASK_FAMILY_MATERIAL else None
                    return {
                        "task_type": reaction,
                        "task_family": family,
                        "property_type": prop,
                        "reaction_type": reaction,
                        "consensus_reached": bool((res or {}).get("consensus_reached")) if isinstance(res, dict) else False,
                        "final_products": (res or {}).get("final_products") if isinstance(res, dict) else None,
                        "final_performance": (res or {}).get("final_performance") if isinstance(res, dict) else None,
                        "debate_rounds": (res or {}).get("debate_rounds") if isinstance(res, dict) else None,
                        "time_elapsed": (res or {}).get("time_elapsed") if isinstance(res, dict) else None,
                        **perf_fields,
                        "error": None,
                    }
                except Exception as e:
                    last_err = e
                    msg = str(e) or e.__class__.__name__
                    # Retry only for likely transient rate-limit failures.
                    msg_l = msg.lower()
                    retriable = any(
                        s in msg_l
                        for s in [
                            "429",
                            "rate limit",
                            "ratelimit",
                            "too many requests",
                            "temporarily unavailable",
                            "timeout",
                            "read timed out",
                            "connect timeout",
                        ]
                    )
                    if attempt < attempts - 1 and retriable:
                        # Exponential backoff (bounded) with a tiny deterministic jitter.
                        sleep_s = min(30.0, 2.0 * (2**attempt))
                        time.sleep(sleep_s)
                        continue
                    break

            err_text = str(last_err) if last_err is not None else "unknown error"
            family = task_family(reaction)
            return {
                "task_type": reaction,
                "task_family": family,
                "property_type": reaction if family == TASK_FAMILY_MATERIAL else None,
                "reaction_type": reaction,
                "consensus_reached": False,
                "final_products": None,
                "final_performance": None,
                "debate_rounds": None,
                "time_elapsed": None,
                "performance_evaluation": None,
                "metric_value": None,
                "metric_unit": None,
                "grade": None,
                "error": err_text,
            }

        # ---- Execute all reactions (sequential or parallel) ----
        summaries: List[Dict[str, Any]] = []
        if max_par <= 1:
            for rt in rt_list:
                summaries.append(_run_one_reaction(rt))
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=max_par) as ex:
                future_to_rt = {ex.submit(_run_one_reaction, rt): rt for rt in rt_list}
                for fut in as_completed(future_to_rt):
                    try:
                        summaries.append(fut.result())
                    except Exception as e:
                        # Should be rare since _run_one_reaction catches, but keep robust.
                        summaries.append(
                            {
                                "task_type": canonical_task_or_raw(future_to_rt.get(fut)),
                                "task_family": task_family(future_to_rt.get(fut)),
                                "property_type": canonical_task_or_raw(future_to_rt.get(fut)) if task_family(future_to_rt.get(fut)) == TASK_FAMILY_MATERIAL else None,
                                "reaction_type": canonical_task_or_raw(future_to_rt.get(fut)),
                                "error": str(e),
                                "performance_evaluation": None,
                                "metric_value": None,
                                "metric_unit": None,
                                "grade": None,
                            }
                        )

            # Preserve original reaction_types order as a stable secondary key for equal ranks.
            order = {canonical_task_or_raw(rt): i for i, rt in enumerate(rt_list)}
            summaries.sort(
                key=lambda d: order.get(
                    canonical_task_or_raw(d.get("task_type") or d.get("property_type") or d.get("reaction_type")),
                    10**9,
                )
            )

        # ---- Rank and save summary ----
        from utils.reaction_ranking import rank_reactions
        from utils.helpers import generate_timestamp

        ranking, top_items = rank_reactions(summaries, top_k=k_final)

        timestamp = generate_timestamp()
        output_dir = ensure_dir(self.config.get("paths", {}).get("outputs", "./outputs"))
        out_path = output_dir / f"rank_{timestamp}.json"
        payload = {
            "timestamp": timestamp,
            "engine": "langgraph",
            "material_name": material.material_name,
            "material_description": material_description,
            "material_input": material.to_dict(),
            "components": elements,
            "task_types": rt_list,
            "property_types": rt_list,
            "reaction_types": rt_list,
            "selection_mode": "all" if rt_list == list(UNIFIED_TASK_TYPES) else "single" if len(rt_list) == 1 else "subset",
            "direction_count": len(rt_list),
            "top_k_properties": k_final,
            "max_parallel_properties": max_par,
            "debate_scope": "single_task_per_debate",
            "ranking": ranking,
            "top_k": top_items,
        }
        save_json(payload, out_path)
        self.logger.info("Task ranking saved: %s", str(out_path))

        return payload

    def run_rank_reactions(
        self,
        components: Optional[List[str]] = None,
        reaction_types: Optional[List[str]] = None,
        top_k: int = 2,
        max_parallel_reactions: int = 1,
        save_each_reaction: bool = False,
        material_input: Optional[MaterialInput | Dict[str, Any]] = None,
    ) -> Dict:
        """Compatibility wrapper for the former reaction-named public API."""
        return self.run_rank_tasks(
            components,
            task_types=reaction_types,
            top_k=top_k,
            max_parallel_tasks=max_parallel_reactions,
            save_each_task=save_each_reaction,
            material_input=material_input,
        )
    
    def _extract_and_save_experience(self, debate_result, components: List[str], reaction_type: Optional[str] = None) -> None:
        """Experience extraction interface reserved (currently disabled)"""
        return
    
    def _save_result(
        self,
        result,
        components: List[str],
        material_input: Optional[MaterialInput] = None,
        engine: Optional[str] = None,
        performance_evaluation: Optional[Dict] = None,
        reaction_type: Optional[str] = None,
    ) -> None:
        """Save debate results to file"""
        output_dir = ensure_dir(self.config.get('paths', {}).get('outputs', './outputs'))
        
        from utils.helpers import create_experiment_id, generate_timestamp
        identity_parts = [material_input.material_name] if material_input is not None else components
        exp_id = create_experiment_id(identity_parts)
        timestamp = generate_timestamp()
        
        filename = f"result_{timestamp}.json"
        filepath = output_dir / filename
        
        task = canonical_task_or_raw(reaction_type) if reaction_type else ""
        family = task_family(task) if task else None

        result_payload = result.to_dict()
        if task:
            result_payload["task_type"] = task
            result_payload["reaction_type"] = task
        if family:
            result_payload["task_family"] = family
        if performance_evaluation:
            result_payload["performance_evaluation"] = performance_evaluation

        result_data = {
            "experiment_id": exp_id,
            "timestamp": timestamp,
            "engine": engine,
            "components": components,
            "elements": components,
            "result": result_payload
        }
        if material_input is not None:
            result_data["material_name"] = material_input.material_name
            result_data["material_description"] = material_input.build_material_description()
            result_data["material_input"] = material_input.to_dict()
        if task:
            result_data["task_type"] = task
            result_data["reaction_type"] = task
        if family:
            result_data["task_family"] = family
        
        save_json(result_data, filepath)
        self.logger.info(f"Results saved: {filepath}")
    
    def print_system_status(self) -> None:
        """Print system status"""
        print_header("System Status")

        exp_total = 0
        try:
            if self.experience_store:
                exp_total = int(self.experience_store.get_statistics().get("total_experiences", 0))
        except Exception:
            exp_total = 0

        status = {
            "Initialization Status": "Initialized" if self._initialized else "Not Initialized",
            "Number of Agents": len(self.agents) if self.agents else 0,
            "Experience Store Size": exp_total,
            "RAG Systems": "Loaded" if self.rag_systems else "Not Loaded"
        }
        
        print(dict_to_table(status, headers=("Item", "Status")))
        
        if self.experience_store:
            stats = self.experience_store.get_statistics()
            print_section("Experience Store Statistics", dict_to_table(stats, headers=("Metric", "Value")))

def main():
    """Main program entry point"""
    valid_reaction_types = list(UNIFIED_TASK_TYPES)

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Multi-Agent Debate System"
    )
    parser.add_argument(
        '--components',
        type=str,
        help=(
            'Legacy compatibility input. The value is treated as a material identity; prefer --material-name '
            'or --material-input-file for the material-name-centered workflow.'
        )
    )
    parser.add_argument(
        '--material-name',
        type=str,
        help='Required material identity for the material-name-centered workflow (unless --material-input-file is used).'
    )
    parser.add_argument(
        '--material-input-file',
        type=str,
        help='Path to a UTF-8 JSON object containing material_name and any optional structured/custom fields.'
    )
    parser.add_argument(
        '--custom-prompt',
        type=str,
        default=None,
        help='Optional free-form supplemental material description used with --material-name.'
    )
    parser.add_argument(
        '--task-type',
        type=str,
        choices=valid_reaction_types,
        help='Specify one task direction for a single four-agent debate.'
    )
    parser.add_argument(
        '--reaction-type',
        type=str,
        choices=valid_reaction_types,
        help='Compatibility alias for --task-type.'
    )
    parser.add_argument(
        '--rank-tasks',
        action='store_true',
        help='Run one independent debate per selected task and rank the task-specific normalized results.'
    )
    parser.add_argument(
        '--rank-reactions',
        action='store_true',
        help='Compatibility alias for --rank-tasks.'
    )
    parser.add_argument(
        '--top-k-properties',
        type=int,
        default=None,
        help='Number of task directions to return after the outer ranking (default: 2).'
    )
    parser.add_argument(
        '--top-k-reactions',
        type=int,
        default=2,
        help='Compatibility alias for --top-k-properties.'
    )
    parser.add_argument(
        '--task-types',
        type=str,
        default=None,
        help='Comma-separated task subset. Omit to evaluate all 19 directions.'
    )
    parser.add_argument(
        '--reaction-types',
        type=str,
        default=None,
        help='Compatibility alias for --task-types.'
    )
    parser.add_argument(
        '--property-types',
        type=str,
        default=None,
        help='Alias for --reaction-types; accepts material-property and reaction task keys.'
    )
    parser.add_argument(
        '--max-parallel-properties',
        type=int,
        default=None,
        help='Maximum number of independent task debates running concurrently (default: 3).'
    )
    parser.add_argument(
        '--max-parallel-reactions',
        type=int,
        default=3,
        help='Compatibility alias for --max-parallel-properties.'
    )
    parser.add_argument(
        '--save-each-task',
        action='store_true',
        help='Save one detailed result/trace JSON for every task debate.'
    )
    parser.add_argument(
        '--save-each-reaction',
        action='store_true',
        help='Compatibility alias for --save-each-task.'
    )
    parser.add_argument(
        '--engine',
        type=str,
        choices=["langgraph"],
        default="langgraph",
        help='Select Debate Engine (only langgraph is supported currently)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='./config/config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Show system status'
    )
    
    args = parser.parse_args()
    
    try:
        # Create system instance
        system = MADSystem(config_path=args.config, default_engine=args.engine)
        
        # Initialize system
        system.initialize()
        
        # Show system status
        if args.status:
            system.print_system_status()
            return
        
        material = None
        if args.material_input_file:
            material = MaterialInput.from_json_file(args.material_input_file)
        elif args.material_name:
            material = MaterialInput(material_name=args.material_name, custom_prompt=args.custom_prompt)
        elif args.components:
            material = MaterialInput.from_legacy_components(parse_component_string(args.components))

        # Run debate
        if material is not None:
            components = material.retrieval_elements()
            print(f"\nAnalyzing material: {material.material_name}\n")

            rank_tasks = bool(args.rank_tasks or args.rank_reactions)
            single_task = args.task_type or args.reaction_type
            if rank_tasks:
                if single_task:
                    raise ValueError("`--task-type` cannot be used together with task ranking.")

                subset = None
                requested_types = args.task_types or args.property_types or args.reaction_types
                if requested_types:
                    subset = [canonical_task_or_raw(s) for s in str(requested_types).split(",") if s.strip()]
                    bad = [s for s in subset if s not in valid_reaction_types]
                    if bad:
                        raise ValueError(f"Unknown task types: {bad}. Choices: {valid_reaction_types}")

                payload = system.run_rank_tasks(
                    components,
                    material_input=material,
                    task_types=subset,
                    top_k=int(args.top_k_properties if args.top_k_properties is not None else args.top_k_reactions),
                    max_parallel_tasks=int(
                        args.max_parallel_properties
                        if args.max_parallel_properties is not None
                        else args.max_parallel_reactions
                    ),
                    save_each_task=bool(args.save_each_task or args.save_each_reaction),
                )

                ranking = payload.get("ranking") or []
                top_items = payload.get("top_k") or []

                def _fmt_metric(it: Dict) -> str:
                    v = it.get("metric_value")
                    u = it.get("metric_unit")
                    if v is None or not u:
                        return "N/A"
                    return f"{v} {u}"

                print_header("Task Ranking Summary")
                print("Rank | Task Type                             | Grade        | Metric              | Consensus | Error")
                print("-----|---------------------------------------|--------------|---------------------|----------|------")
                for idx, it in enumerate(ranking, start=1):
                    rt = str(it.get("task_type") or it.get("property_type") or it.get("reaction_type") or "").strip() or "?"
                    grade = str(it.get("grade") or "N/A")
                    metric = _fmt_metric(it)
                    consensus = "Yes" if bool(it.get("consensus_reached")) else "No"
                    err = str(it.get("error") or "")
                    if len(err) > 60:
                        err = err[:57] + "..."
                    print(f"{idx:>4} | {rt:<37} | {grade:<12} | {metric:<19} | {consensus:<8} | {err}")

                print_header(f"Top {len(top_items)} Task Types")
                for idx, it in enumerate(top_items, start=1):
                    rt = str(it.get("task_type") or it.get("property_type") or it.get("reaction_type") or "").strip() or "?"
                    grade = str(it.get("grade") or "N/A")
                    metric = _fmt_metric(it)
                    print(f"{idx}. {rt} | Grade: {grade} | Metric: {metric}")

                out_dir = system.config.get("paths", {}).get("outputs", "./outputs")
                ts = payload.get("timestamp") or ""
                if ts:
                    print(f"\nSaved ranking summary: {out_dir}\\rank_{ts}.json")

            else:
                result = system.run_debate(
                    components,
                    reaction_type=single_task,
                    engine=args.engine,
                    material_input=material,
                )

                # Print result summary
                print_header("Debate Result Summary")

                perf_eval = result.get("performance_evaluation") if isinstance(result, dict) else None
                metric_norm = "N/A"
                grade = "N/A"
                if isinstance(perf_eval, dict):
                    v = perf_eval.get("metric_value")
                    u = perf_eval.get("metric_unit")
                    g = perf_eval.get("grade")
                    if v is not None and u:
                        metric_norm = f"{v} {u}"
                    if g:
                        grade = str(g)

                summary = {
                    "Consensus Reached": "Yes" if result["consensus_reached"] else "No",
                    "Products": result.get("final_products") or "Not Determined",
                    "Performance": result.get("final_performance") or "Not Estimated",
                    "Metric (normalized)": metric_norm,
                    "Grade": grade,
                    "Debate Rounds": result["debate_rounds"],
                    "Time Elapsed": format_duration(result["time_elapsed"]),
                }

                print(dict_to_table(summary, headers=("Item", "Result")))
        else:
            print("\nNo material specified.")
            print('Usage: python main.py --material-name "CuO" --rank-reactions')
         
            system.print_system_status()
    
    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user")
        sys.exit(0)
    
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
