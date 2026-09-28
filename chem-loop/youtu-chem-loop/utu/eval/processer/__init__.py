"""Evaluation processors (extracted, chem-loop focused).

Upstream youtu-agent supports many benchmarks (GAIA/WebWalker/XBench/etc.). For this
chem-loop repo we only keep the processor(s) required by our chem-performance datasets:

- `training_free_grpo` (uses non-LLM verify under `utu/practice/verify/`)

If you need to re-add other processors later, restore the upstream modules and re-export
them here so the factory can register them.
"""

from utu.config import EvalConfig
from utu.utils import get_logger

from .base_llm_processor import BaseLLMJudgeProcesser as BaseLLMJudgeProcesser
from .base_match_processor import BaseMatchProcesser as BaseMatchProcesser
from .base_processor import BaseProcesser
from .training_free_grpo_processor import TrainingFreeGRPOProcesser as TrainingFreeGRPOProcesser

logger = get_logger(__name__)


# factory class for evaluation
class ProcesserFactory:
    """
    Factory class for creating evaluation instances.
    """

    _registry = {}

    def __init__(self):
        # Register all processer classes
        self._recurse_register(BaseProcesser)

    def _recurse_register(self, cls: type[BaseProcesser]) -> None:
        """
        Recursively register all subclasses of cls.
        """
        for subcls in cls.__subclasses__():
            if hasattr(subcls, "name") and subcls.name:
                self._registry[subcls.name] = subcls
                self._registry[subcls.name.lower()] = subcls
            # Recursively register subclasses
            self._recurse_register(subcls)

    @classmethod
    def get(cls, name: str, config: EvalConfig) -> BaseProcesser:
        """
        Get a processer class by name.
        """
        name_lower = name.lower()
        if name_lower not in cls._registry:
            # if the name is found, return the corresponding processer
            logger.warning(f"Processer for dataset='{name}' not found. Using default processer.")
            return cls._registry["default"](config)
        return cls._registry[name_lower](config)

    @classmethod
    def get_all(cls) -> list[str]:
        """
        Get a list of all available processers.

        :return: A list of all available processers.
        """
        return list(cls._registry.keys())

    @classmethod
    def register(cls, name: str, processer_class: type[BaseProcesser]):
        """
        Register a processer class.

        :param name: The name of the processer.
        :param processer_class: The processer class to register.
        """
        if not issubclass(processer_class, BaseProcesser):
            raise TypeError(f"{processer_class} is not a subclass of BaseProcesser")
        cls._registry[name] = processer_class
        cls._registry[name.lower()] = processer_class


PROCESSER_FACTORY = ProcesserFactory()
