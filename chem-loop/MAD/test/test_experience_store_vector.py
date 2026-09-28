import shutil
import unittest
import uuid
from pathlib import Path

from experience import ExperienceStore


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _make_guideline_pack_yaml() -> str:
    return (
        "agent:\n"
        "  instructions: |\n"
        "    [G0]. Format compliance: Strictly enforce STRICT JSON output format.\n"
        "    [G1]. CO2RR sign: For CO2RR, partial current densities are reduction currents.\n"
        "    [G2]. Overpotential: η@10 mA cm-2 is the target for HER/OER/HzOR.\n"
    )


def _make_case_pack_yaml() -> str:
    return (
        "experiences:\n"
        "  - kind: case\n"
        "    components: [\"Pt\", \"Pd\"]\n"
        "    reaction_type: OER\n"
        "    products: N/A\n"
        "    performance: \"310 mV overpotential at 10 mA/cm^2\"\n"
        "    reasoning: \"PtPd alloys often show improved OER kinetics in alkaline conditions.\"\n"
    )


def _make_test_tmp_dir() -> Path:
    base_dir = Path(__file__).resolve().parent
    tmp_dir = base_dir / f"_tmp_es_vec_{uuid.uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=False)
    return tmp_dir


class TestExperienceStoreVector(unittest.TestCase):
    def test_vector_search_prefers_relevant_guideline(self) -> None:
        td_path = _make_test_tmp_dir()
        try:
            _write_text(td_path / "pack_guides.yaml", _make_guideline_pack_yaml())
            json_path = td_path / "experience_db.json"

            store = ExperienceStore(
                storage_path=str(json_path),
                packs_path=str(td_path),
                load_builtin_packs=False,
                experience_search_mode="vector",
                embedding_provider="hash",
                embedding_hash_dim=64,
                embedding_cache_path=str(td_path / "embed_cache.json"),
                guideline_top_k=2,
                always_include_guidelines=True,
            )

            # Query mentions CO2RR -> guideline with "CO2RR" should rank first.
            results = store.query_experiences(["Pt"], top_k=1, query_text="reaction_type: CO2RR metrics_to_predict: partial_current_density")
            self.assertTrue(results, "Expected experiences to be returned in vector mode")
            self.assertEqual(results[0].get("kind"), "guideline")
            self.assertEqual(results[0].get("guideline_id"), "G1")
        finally:
            shutil.rmtree(td_path, ignore_errors=True)

    def test_vector_search_can_surface_case_experience(self) -> None:
        td_path = _make_test_tmp_dir()
        try:
            _write_text(td_path / "pack_guides.yaml", _make_guideline_pack_yaml())
            _write_text(td_path / "pack_cases.yaml", _make_case_pack_yaml())
            json_path = td_path / "experience_db.json"

            store = ExperienceStore(
                storage_path=str(json_path),
                packs_path=str(td_path),
                load_builtin_packs=False,
                experience_search_mode="vector",
                embedding_provider="hash",
                embedding_hash_dim=64,
                embedding_cache_path=str(td_path / "embed_cache.json"),
                guideline_top_k=1,
                always_include_guidelines=True,
            )

            results = store.query_experiences(
                ["Pt", "Pd"],
                top_k=2,
                query_text="reaction_type: OER metals: Pt, Pd overpotential 10 mA cm-2",
            )
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0].get("kind"), "guideline")
            self.assertEqual(results[1].get("kind"), "case")
            self.assertEqual(set(results[1].get("components") or []), {"Pt", "Pd"})
        finally:
            shutil.rmtree(td_path, ignore_errors=True)
