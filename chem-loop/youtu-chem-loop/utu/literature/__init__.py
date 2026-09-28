"""Literature access helpers.

This package provides small, dependency-light building blocks for reading
literature metadata/content from external stores (e.g., SQLite) so they can be
exposed to agents via toolkits.
"""

from .chroma_store import ChromaLiteratureStore, ChromaLiteratureStoreConfig
from .sqlite_store import SQLiteLiteratureStore, SQLiteLiteratureStoreConfig
from .voyage_embedder import VoyageEmbedder, VoyageEmbedderConfig

__all__ = [
    "ChromaLiteratureStore",
    "ChromaLiteratureStoreConfig",
    "SQLiteLiteratureStore",
    "SQLiteLiteratureStoreConfig",
    "VoyageEmbedder",
    "VoyageEmbedderConfig",
]
