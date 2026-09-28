from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from chemcouncil.jobs import JobStore
from chemcouncil.server import TASK_TYPES, _run_job_guarded, handle_recommend_rank, handle_recommendations_list
from chemcouncil.workflows import RepoPaths


class _DummyRequest:
    def __init__(self, app: dict, payload: dict | None = None, query: dict | None = None):
        self.app = app
        self._payload = payload or {}
        self.query = query or {}

    async def json(self) -> dict:
        return self._payload


def _call_recommend_rank(*, app: dict, payload: dict, monkeypatch) -> tuple[int, dict]:
    class _DummyTask:
        pass

    def _fake_create_task(coro):
        frame = getattr(coro, "cr_frame", None)
        if frame is not None:
            inner = frame.f_locals.get("coro")
            if inner is not None and hasattr(inner, "close"):
                inner.close()
        coro.close()
        return _DummyTask()

    monkeypatch.setattr("chemcouncil.server.asyncio.create_task", _fake_create_task)
    response = asyncio.run(handle_recommend_rank(_DummyRequest(app, payload)))
    return response.status, json.loads(response.text)


def _make_app(tmp_path: Path) -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    return {
        "store": JobStore(tmp_path / "jobs"),
        "paths": RepoPaths.from_root(repo_root),
        "python_bin": sys.executable,
        "tasks": {},
    }


def _create_completed_recommendation(app: dict, payload: dict) -> str:
    job = app["store"].create("mad_rank", payload)
    job.status = "completed"
    app["store"].save(job)
    return job.id


def _list_recommendations(app: dict, query: dict | None = None) -> dict:
    response = asyncio.run(handle_recommendations_list(_DummyRequest(app, query=query)))
    assert response.status == 200
    return json.loads(response.text)


def test_recommend_rank_requires_material_name(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    status, body = _call_recommend_rank(app=app, payload={"custom_prompt": "only description"}, monkeypatch=monkeypatch)
    assert status == 400
    assert body["error"] == "missing required 'material_name'"


def test_recommend_rank_accepts_name_only_material(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    status, body = _call_recommend_rank(
        app=app,
        payload={"material_name": "CuO", "task_types": ["conductivity"]},
        monkeypatch=monkeypatch,
    )
    assert status == 200
    job = app["store"].load(str(body["job_id"]))
    assert job is not None
    assert job.payload["material_name"] == "CuO"
    assert job.payload["material_input"] == {"material_name": "CuO"}
    assert job.payload["detected_elements"] == ["Cu", "O"]
    assert job.payload["selection_mode"] == "single"
    assert job.payload["direction_count"] == 1
    assert job.payload["top_k_properties"] == 1
    assert job.payload["max_parallel_properties"] == 1
    assert job.payload["debate_scope"] == "single_task_per_debate"


def test_recommend_rank_preserves_structured_and_custom_input(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    material_input = {
        "material_name": "MoS2负载CuO纳米颗粒",
        "precursors": ["MoS2", "Cu(NO3)2"],
        "feed_ratio": "1:2",
        "preparation_method": "水热法",
        "elements": ["Mo", "S", "Cu", "O"],
        "custom_prompt": "CuO颗粒平均粒径约8 nm。",
    }
    status, body = _call_recommend_rank(
        app=app,
        payload={
            "material_input": material_input,
            "task_types": "photocatalytic_h2o2,thermoelectric",
            "top_k_properties": 8,
            "max_parallel_properties": 9,
        },
        monkeypatch=monkeypatch,
    )
    assert status == 200
    job = app["store"].load(str(body["job_id"]))
    assert job is not None
    assert job.payload["material_input"] == material_input
    assert job.payload["task_types"] == ["photocatalytic_h2o2", "thermoelectric"]
    assert job.payload["selection_mode"] == "subset"
    assert job.payload["direction_count"] == 2
    assert job.payload["top_k_properties"] == 2
    assert job.payload["max_parallel_properties"] == 2


def test_recommend_rank_preserves_positive_material_serial(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    status, body = _call_recommend_rank(
        app=app,
        payload={
            "material_input": {
                "material_serial_no": "17",
                "material_name": "CuO",
            },
            "task_types": ["conductivity"],
        },
        monkeypatch=monkeypatch,
    )
    assert status == 200
    job = app["store"].load(str(body["job_id"]))
    assert job is not None
    assert job.payload["material_serial_no"] == 17
    assert job.payload["material_input"]["material_serial_no"] == 17


def test_recommend_rank_accepts_material_no_alias(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    status, body = _call_recommend_rank(
        app=app,
        payload={"material_no": 23, "material_name": "CuO", "task_types": ["conductivity"]},
        monkeypatch=monkeypatch,
    )
    assert status == 200
    job = app["store"].load(str(body["job_id"]))
    assert job is not None
    assert job.payload["material_serial_no"] == 23


def test_recommend_rank_rejects_invalid_material_serials(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    for invalid in (0, -1, 1.5, "abc", True):
        status, body = _call_recommend_rank(
            app=app,
            payload={"material_serial_no": invalid, "material_name": "CuO", "task_types": ["conductivity"]},
            monkeypatch=monkeypatch,
        )
        assert status == 400
        assert body["error"] == "material_serial_no must be a positive integer"


def test_recommend_rank_defaults_to_all_19_tasks(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    status, body = _call_recommend_rank(app=app, payload={"material_name": "Bi2Te3"}, monkeypatch=monkeypatch)
    assert status == 200
    job = app["store"].load(str(body["job_id"]))
    assert job is not None
    assert len(TASK_TYPES) == 19
    assert job.payload["task_types"] == TASK_TYPES
    assert job.payload["selection_mode"] == "all"
    assert job.payload["direction_count"] == 19
    assert job.payload["top_k_properties"] == 2
    assert job.payload["max_parallel_properties"] == 1
    assert "HER" in TASK_TYPES
    assert "furfural_hydrogenation" in TASK_TYPES


def test_recommend_rank_accepts_mixed_task_aliases(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    status, body = _call_recommend_rank(
        app=app,
        payload={"material_name": "CuO", "task_types": "OER,antimicrobial,furfural hydrogenation"},
        monkeypatch=monkeypatch,
    )
    assert status == 200
    job = app["store"].load(str(body["job_id"]))
    assert job is not None
    assert job.payload["task_types"] == ["OER", "antibacterial", "furfural_hydrogenation"]


def test_recommend_rank_accepts_all_selector_and_new_controls(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    status, body = _call_recommend_rank(
        app=app,
        payload={
            "material_name": "CuO",
            "task_types": ["all"],
            "top_k_properties": 4,
            "max_parallel_properties": 3,
            "save_each_task": False,
        },
        monkeypatch=monkeypatch,
    )
    assert status == 200
    job = app["store"].load(str(body["job_id"]))
    assert job is not None
    assert job.payload["task_types"] == TASK_TYPES
    assert job.payload["selection_mode"] == "all"
    assert job.payload["top_k_properties"] == 4
    assert job.payload["max_parallel_properties"] == 3
    assert job.payload["save_each_task"] is False


def test_recommend_rank_rejects_empty_task_list(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    status, body = _call_recommend_rank(
        app=app,
        payload={"material_name": "CuO", "task_types": []},
        monkeypatch=monkeypatch,
    )
    assert status == 400
    assert "at least one task direction" in body["error"]


def test_recommend_rank_rejects_out_of_range_controls(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    status, body = _call_recommend_rank(
        app=app,
        payload={"material_name": "CuO", "task_types": ["OER"], "top_k_properties": 0},
        monkeypatch=monkeypatch,
    )
    assert status == 400
    assert "top_k_properties" in body["error"]


def test_recommend_rank_accepts_legacy_control_aliases(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    status, body = _call_recommend_rank(
        app=app,
        payload={
            "material_name": "CuO",
            "task_types": ["OER", "HER"],
            "top_k_reactions": 1,
            "max_parallel_reactions": 2,
            "save_each_reaction": False,
        },
        monkeypatch=monkeypatch,
    )
    assert status == 200
    job = app["store"].load(str(body["job_id"]))
    assert job is not None
    assert job.payload["top_k_properties"] == 1
    assert job.payload["max_parallel_properties"] == 2
    assert job.payload["save_each_task"] is False


def test_recommendations_list_is_material_first_and_legacy_is_opt_in(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    legacy_id = _create_completed_recommendation(
        app,
        {
            "components": "Cu(67.72%), Al(19.42%), Fe(12.87%)",
            "task_types": ["OER"],
        },
    )
    material_id = _create_completed_recommendation(
        app,
        {
            "material_name": "MoS2负载CuO纳米颗粒",
            "material_serial_no": 17,
            "components": "Mo, S, Cu, O",
            "material_input": {
                "material_serial_no": 17,
                "material_name": "MoS2负载CuO纳米颗粒",
                "precursors": ["MoS2", "Cu(NO3)2"],
                "preparation_method": "水热法",
                "elements": ["Mo", "S", "Cu", "O"],
                "custom_prompt": "CuO颗粒平均粒径约8 nm。",
            },
            "task_types": ["photothermal_conversion_efficiency"],
        },
    )

    default_items = _list_recommendations(app, {"limit": "20"})["items"]
    assert [item["job_id"] for item in default_items] == [material_id]
    assert default_items[0]["material_name"] == "MoS2负载CuO纳米颗粒"
    assert default_items[0]["material_serial_no"] == 17
    assert default_items[0]["is_legacy_material_record"] is False

    description_matches = _list_recommendations(app, {"q": "水热法 8 nm"})["items"]
    assert [item["job_id"] for item in description_matches] == [material_id]

    serial_matches = _list_recommendations(app, {"q": "17"})["items"]
    assert [item["job_id"] for item in serial_matches] == [material_id]

    component_matches = _list_recommendations(app, {"q": "67.72%", "include_legacy": "1"})["items"]
    assert component_matches == []

    with_legacy = _list_recommendations(app, {"limit": "20", "include_legacy": "1"})["items"]
    by_id = {item["job_id"]: item for item in with_legacy}
    assert set(by_id) == {legacy_id, material_id}
    assert by_id[legacy_id]["material_name"] == ""
    assert by_id[legacy_id]["material_serial_no"] is None
    assert by_id[legacy_id]["is_legacy_material_record"] is True


def test_recommendation_semaphore_runs_material_jobs_in_parallel(tmp_path: Path) -> None:
    """The recommendation pool must allow multiple material jobs to overlap."""

    async def _exercise() -> int:
        active = 0
        max_active = 0
        lock = asyncio.Lock()
        app = {
            "store": JobStore(tmp_path / "jobs"),
            "job_semaphore": asyncio.Semaphore(1),
            "recommendation_semaphore": asyncio.Semaphore(2),
            "tasks": {},
        }

        async def _work() -> None:
            nonlocal active, max_active
            async with lock:
                active += 1
                max_active = max(max_active, active)
            # Yield while both recommendation slots are occupied. If the
            # semaphore were accidentally serial, max_active would be 1.
            await asyncio.sleep(0.02)
            async with lock:
                active -= 1

        await asyncio.gather(
            *(
                _run_job_guarded(
                    app,
                    f"recommendation-{idx}",
                    _work(),
                    semaphore_key="recommendation_semaphore",
                )
                for idx in range(4)
            )
        )
        return max_active

    assert asyncio.run(_exercise()) == 2


def test_general_job_semaphore_remains_independent_from_recommendations(tmp_path: Path) -> None:
    """Experience/update jobs still use the general one-slot pool."""

    async def _exercise() -> int:
        active = 0
        max_active = 0
        lock = asyncio.Lock()
        app = {
            "store": JobStore(tmp_path / "jobs"),
            "job_semaphore": asyncio.Semaphore(1),
            "recommendation_semaphore": asyncio.Semaphore(4),
            "tasks": {},
        }

        async def _work() -> None:
            nonlocal active, max_active
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1

        await asyncio.gather(
            *(
                _run_job_guarded(app, f"general-{idx}", _work())
                for idx in range(3)
            )
        )
        return max_active

    assert asyncio.run(_exercise()) == 1
