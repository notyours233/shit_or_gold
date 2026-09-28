from __future__ import annotations

import unittest
from pathlib import Path

import yaml


def _matches_where(metadata, where):
    if not where:
        return True
    for key, expected in where.items():
        actual = (metadata or {}).get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if actual not in (expected.get("$in") or []):
                return False
            continue
        if actual != expected:
            return False
    return True


class _DummyRAG:
    collection_name = "test_collection"

    def __init__(self):
        self.last_query = None
        self.last_top_k = None
        self.last_where = None

    def retrieve(self, query: str, top_k: int = 5, where=None):
        self.last_query = query
        self.last_top_k = top_k
        self.last_where = where
        rows = [
            {
                "text": (
                    "### Oxygen Evolution Reaction\n"
                    "This is a sufficiently long dummy chunk about oxygen evolution reaction (OER), "
                    "included to test reaction_type hard filtering."
                ),
                "score": 0.95,
                "metadata": {"doc_id": "10.1234/dummy", "chunk_id": 1, "reaction_type": "OER"},
            },
            {
                "text": (
                    "This is a sufficiently long dummy chunk about oxygen reduction reaction (ORR) "
                    "showing typical metrics and considerations for catalysts in alkaline media."
                ),
                "score": 0.9,
                "metadata": {"doc_id": "10.1234/dummy", "chunk_id": 2, "reaction_type": "ORR"},
            }
        ]
        return [r for r in rows if _matches_where(r.get("metadata"), where)][:top_k]


class _DummyCollection:
    def __init__(self, metadata):
        self.metadata = dict(metadata or {})

    def get(self, *args, **kwargs):
        return {
            "ids": ["10.1234/dummy#chunk:1"],
            "documents": ["A sufficiently long dummy literature chunk."],
            "metadatas": [dict(self.metadata)],
        }


class _DummyClient:
    def __init__(self, metadata):
        self.metadata = dict(metadata or {})

    def get_collection(self, name: str):
        self.last_collection = name
        return _DummyCollection(self.metadata)


class _DummyVectorStore:
    def __init__(self, metadata):
        self.client = _DummyClient(metadata)


class _DummyFetchRAG:
    collection_name = "material_property_literature_agent1"

    def __init__(self, metadata):
        self.vector_store = _DummyVectorStore(metadata)


class RAGReactionFilterTests(unittest.TestCase):
    def test_default_rag_config_uses_single_chroma_persist_directory(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        vector_store = cfg.get("vector_store") or {}

        self.assertEqual(vector_store.get("persist_directory"), "./data/chroma_db")
        self.assertEqual(vector_store.get("reaction_persist_directory"), "./data/chroma_db")
        self.assertEqual(vector_store.get("collection_names", {}).get("material_property"), "literature")
        self.assertEqual(vector_store.get("collection_names", {}).get("reaction"), "literature")

    def test_reaction_type_where_filter_is_passed_to_rag_adapter(self):
        from agents.react_agent import ReActAgent
        from agents.react_reasoning import ReActTrajectory

        rag = _DummyRAG()
        agent = ReActAgent(
            agent_id="t2",
            name="test",
            model_config={
                "rag_filter_by_reaction_type": True,
                "rag_filter_junk_chunks": False,  # irrelevant for this test
            },
            rag_system=rag,
            experience_store=None,
            system_prompt="",
            verbose=False,
        )

        agent.current_trajectory = ReActTrajectory(
            query="Reaction Type: ORR\nMetal catalyst elements: Pt, Cu, Ni, Fe, Co"
        )

        out = agent._tool_search_literature(query="orr activity", top_k=1)
        self.assertEqual(rag.last_where, {"reaction_type": "ORR"})
        data = out.data or []
        self.assertEqual(len(data), 1)
        self.assertEqual(((data[0].get("metadata") or {}).get("reaction_type") or "").upper(), "ORR")

    def test_material_literature_where_filter_accepts_chroma_metadata_aliases(self):
        from agents.react_agent import ReActAgent
        from agents.react_reasoning import ReActTrajectory

        class _ThermalRAG(_DummyRAG):
            def retrieve(self, query: str, top_k: int = 5, where=None):
                self.last_query = query
                self.last_top_k = top_k
                self.last_where = where
                rows = [
                    {
                        "text": (
                            "This is a sufficiently long dummy chunk about thermal conductivity "
                            "with measured W m-1 K-1 values for a multi-metal material."
                        ),
                        "score": 0.95,
                        "metadata": {
                            "doc_id": "10.1234/thermal",
                            "chunk_id": 1,
                            "reaction_type": "thermal conductivity",
                        },
                    }
                ]
                return [r for r in rows if _matches_where(r.get("metadata"), where)][:top_k]

        rag = _ThermalRAG()
        agent = ReActAgent(
            agent_id="t2",
            name="test",
            model_config={
                "rag_filter_by_reaction_type": True,
                "rag_filter_junk_chunks": False,
            },
            rag_system=rag,
            rag_systems_by_family={"material_property": rag},
            experience_store=None,
            system_prompt="",
            verbose=False,
        )

        agent.current_trajectory = ReActTrajectory(
            query="Task family: material_property\nReaction Type: thermal_conductivity\nMetal elements: Cu, Ag"
        )

        out = agent._tool_search_literature(query="thermal conductivity", top_k=1)
        aliases = ((rag.last_where or {}).get("reaction_type") or {}).get("$in") or []
        self.assertIn("thermal_conductivity", aliases)
        self.assertIn("thermal conductivity", aliases)
        data = out.data or []
        self.assertEqual(len(data), 1)
        self.assertEqual((data[0].get("metadata") or {}).get("reaction_type"), "thermal conductivity")

    def test_reaction_task_uses_available_collection_with_metadata_where_filter(self):
        from agents.react_agent import ReActAgent
        from agents.react_reasoning import ReActTrajectory

        shared_rag = _DummyRAG()
        agent = ReActAgent(
            agent_id="t2",
            name="test",
            model_config={
                "rag_filter_by_reaction_type": True,
                "rag_filter_junk_chunks": False,
            },
            rag_system=shared_rag,
            rag_systems_by_family={"material_property": shared_rag},
            experience_store=None,
            system_prompt="",
            verbose=False,
        )

        agent.current_trajectory = ReActTrajectory(
            query="Task family: reaction\nReaction Type: ORR\nMetal catalyst elements: Pt, Cu, Ni"
        )

        out = agent._tool_search_literature(query="orr activity", top_k=1)
        self.assertEqual(shared_rag.last_where, {"reaction_type": "ORR"})
        data = out.data or []
        self.assertEqual(len(data), 1)
        self.assertEqual(((data[0].get("metadata") or {}).get("reaction_type") or "").upper(), "ORR")

    def test_fetch_literature_chunk_blocks_wrong_task_metadata(self):
        from agents.react_agent import ReActAgent
        from agents.react_reasoning import ReActTrajectory

        rag = _DummyFetchRAG({"doc_id": "10.1234/dummy", "chunk_index": 1, "reaction_type": "conductivity"})
        agent = ReActAgent(
            agent_id="t2",
            name="test",
            model_config={},
            rag_system=rag,
            rag_systems_by_family={"material_property": rag},
            experience_store=None,
            system_prompt="",
            verbose=False,
        )
        agent.current_trajectory = ReActTrajectory(
            query="Task family: material_property\nReaction Type: thermal_conductivity\nMetal elements: Cu, Ag"
        )

        out = agent._tool_fetch_literature_chunk(
            "rag:chroma/material_property_literature_agent1/doi:10.1234/dummy#chunk:1"
        )
        self.assertEqual(out.data, [])
        self.assertIn("Blocked off-task", out.observation)
	
	
if __name__ == "__main__":
    unittest.main()
