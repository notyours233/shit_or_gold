import os
from pathlib import Path

import pytest

from utu.config import ToolkitConfig
from utu.literature.voyage_embedder import VoyageEmbedder
from utu.tools.chem_literature_db_toolkit import ChemLiteratureDBToolkit


def _build_chroma_db(path: Path, collection_name: str = "test_collection") -> None:
    # Chroma can fail in constrained envs unless SQLite temp dirs are set.
    os.environ.setdefault("SQLITE_TMPDIR", "/tmp")
    os.environ.setdefault("TMPDIR", "/tmp")

    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(path),
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )
    col = client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

    col.add(
        ids=["a", "b"],
        documents=[
            "OER overpotential 0.288 V at 10 mA/cm2 for Mn-Ni-Tb catalysts.",
            "HER overpotential 0.60 V at 10 mA/cm2 for La catalysts.",
        ],
        embeddings=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        metadatas=[
            {"doc_id": "10.0000/test1", "reaction_type": "OER", "chunk_id": 0, "total_chunks": 1},
            {"doc_id": "10.0000/test2", "reaction_type": "HER", "chunk_id": 0, "total_chunks": 1},
        ],
    )


@pytest.mark.asyncio
async def test_chroma_backend_missing_voyage_key_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Ensure the test is deterministic even when the developer has VOYAGE_API_KEY set locally.
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    _build_chroma_db(tmp_path, collection_name="lit")
    tk = ChemLiteratureDBToolkit(
        ToolkitConfig(
            name="chem_literature_db",
            config={
                "backend": "chroma",
                "persist_directory": str(tmp_path),
                "collection_name": "lit",
                # Intentionally omit voyage_api_key
                "voyage_model": "voyage-3-large",
                "max_distance": 0.2,
            },
        )
    )
    hits = await tk.literature_search("OER overpotential", limit=2)
    assert isinstance(hits, list)
    assert hits and "error" in hits[0]
    assert hits[0].get("hit") is False
    assert "Voyage embedding is not configured" in hits[0]["error"]


@pytest.mark.asyncio
async def test_chroma_backend_search_hit_and_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _build_chroma_db(tmp_path, collection_name="lit")

    # Avoid network by stubbing embeddings.
    def _fake_embed_query(self: VoyageEmbedder, query: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    monkeypatch.setattr(VoyageEmbedder, "embed_query", _fake_embed_query)

    tk = ChemLiteratureDBToolkit(
        ToolkitConfig(
            name="chem_literature_db",
            config={
                "backend": "chroma",
                "persist_directory": str(tmp_path),
                "collection_name": "lit",
                "voyage_api_key": "test-key",
                "voyage_model": "voyage-3-large",
                "max_distance": 0.2,  # strict
                "snippet_chars": 80,
            },
        )
    )

    hits = await tk.literature_search("Mn Ni Tb OER overpotential", limit=5)
    assert isinstance(hits, list)
    assert hits and "error" not in hits[0]
    assert hits[0]["doc_id"] == "10.0000/test1"
    assert hits[0]["reaction_type"] == "OER"
    assert hits[0]["distance"] is not None
    assert "text" in hits[0] and hits[0]["text"]

    # Reaction-type filter + strict threshold -> explicit "no results"
    no_hits = await tk.literature_search("Mn Ni Tb OER overpotential", limit=5, reaction_type="HER", max_distance=0.2)
    assert isinstance(no_hits, list)
    assert no_hits and no_hits[0].get("hit") is False
    assert "No results" in (no_hits[0].get("message") or "")


@pytest.mark.asyncio
async def test_chroma_backend_masked_doc_ids_filters_hits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _build_chroma_db(tmp_path, collection_name="lit")

    # Avoid network by stubbing embeddings.
    def _fake_embed_query(self: VoyageEmbedder, query: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    monkeypatch.setattr(VoyageEmbedder, "embed_query", _fake_embed_query)

    # Control: without masking, we hit doc_id=test1.
    tk = ChemLiteratureDBToolkit(
        ToolkitConfig(
            name="chem_literature_db",
            config={
                "backend": "chroma",
                "persist_directory": str(tmp_path),
                "collection_name": "lit",
                "voyage_api_key": "test-key",
                "voyage_model": "voyage-3-large",
                "max_distance": 0.2,  # strict: only the best hit should pass
            },
        )
    )
    hits = await tk.literature_search("Mn Ni Tb OER overpotential", limit=5)
    assert hits and hits[0].get("doc_id") == "10.0000/test1"

    # With doc-level masking, the same query should return explicit "no results".
    tk_masked = ChemLiteratureDBToolkit(
        ToolkitConfig(
            name="chem_literature_db",
            config={
                "backend": "chroma",
                "persist_directory": str(tmp_path),
                "collection_name": "lit",
                "voyage_api_key": "test-key",
                "voyage_model": "voyage-3-large",
                "max_distance": 0.2,
                "masked_doc_ids": ["10.0000/test1"],
            },
        )
    )
    masked_hits = await tk_masked.literature_search("Mn Ni Tb OER overpotential", limit=5)
    assert isinstance(masked_hits, list)
    assert masked_hits and masked_hits[0].get("hit") is False
    assert "No results" in (masked_hits[0].get("message") or "")
