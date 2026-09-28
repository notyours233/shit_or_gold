from pathlib import Path

from utu.literature.chem_performance_masking import load_doi_map_from_tsv


def test_load_doi_map_from_tsv_extracts_only_wanted_ids(tmp_path: Path):
    tsv = tmp_path / "mock.tsv"
    tsv.write_text(
        "\t".join(["index", "title", "doi"]) + "\n"
        + "\t".join(["24", "paper a", "10.0000/a"]) + "\n"
        + "\t".join(["108", "paper b", "10.0000/b"]) + "\n",
        encoding="utf-8",
    )

    mapping = load_doi_map_from_tsv(tsv, wanted_ids={108})
    assert mapping == {108: "10.0000/b"}

    mapping2 = load_doi_map_from_tsv(tsv, wanted_ids={24, 108})
    assert mapping2[24] == "10.0000/a"
    assert mapping2[108] == "10.0000/b"


def test_load_doi_map_from_tsv_empty_wanted_ids_is_empty(tmp_path: Path):
    tsv = tmp_path / "mock.tsv"
    tsv.write_text("index\tdoi\n0\t10.0000/x\n", encoding="utf-8")
    assert load_doi_map_from_tsv(tsv, wanted_ids=set()) == {}

