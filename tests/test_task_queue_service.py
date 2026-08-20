from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError
from app.schemas.rag_eval import RagEvaluationRunRequest
from app.services.task_queue_service import TaskQueueService
from app.workers.celery_app import celery_app
from app.workers.tasks import run_rag_evaluation_task


def test_get_rag_evaluation_status_maps_progress(monkeypatch) -> None:
    task_result = SimpleNamespace(
        state="PROGRESS",
        info={"owner_id": "user-1", "completed_cases": 12, "total_cases": 31},
        result=None,
    )
    monkeypatch.setattr(celery_app, "AsyncResult", lambda task_id: task_result)

    status = TaskQueueService().get_rag_evaluation_status("task-1", owner_id="user-1")

    assert status.status == "running"
    assert status.completed_cases == 12
    assert status.total_cases == 31


def test_get_rag_evaluation_status_rejects_other_owner(monkeypatch) -> None:
    task_result = SimpleNamespace(
        state="PROGRESS",
        info={"owner_id": "user-2", "completed_cases": 1, "total_cases": 31},
        result=None,
    )
    monkeypatch.setattr(celery_app, "AsyncResult", lambda task_id: task_result)

    with pytest.raises(NotFoundError):
        TaskQueueService().get_rag_evaluation_status("task-1", owner_id="user-1")


def test_enqueue_rag_evaluation_serializes_request(monkeypatch) -> None:
    captured: dict = {}

    def fake_apply_async(*, args, headers):
        captured["args"] = args
        captured["headers"] = headers
        return SimpleNamespace(id="task-1")

    monkeypatch.setattr(run_rag_evaluation_task, "apply_async", fake_apply_async)
    payload = RagEvaluationRunRequest(
        dataset_path="deepseek.json",
        collection_id="collection-1",
    )

    task_id = TaskQueueService().enqueue_rag_evaluation(payload, owner_id="user-1")

    assert task_id == "task-1"
    assert captured["args"][0]["dataset_path"] == "deepseek.json"
    assert captured["args"][1] == "user-1"
    assert captured["headers"]["request_id"]


def test_rag_evaluation_worker_publishes_case_progress(monkeypatch) -> None:
    progress_updates: list[dict] = []

    class FakeReportService:
        def get_dataset_case_count(self, dataset_path: str) -> int:
            assert dataset_path == "deepseek.json"
            return 2

        def run_evaluation(self, payload, progress_callback):
            progress_callback(1, 2)
            progress_callback(2, 2)
            return SimpleNamespace(
                report_id="report-1",
                model_dump=lambda mode: {"report_id": "report-1"},
            )

    monkeypatch.setattr(
        "app.workers.tasks.get_rag_evaluation_report_service",
        lambda: FakeReportService(),
    )
    monkeypatch.setattr(
        run_rag_evaluation_task,
        "update_state",
        lambda *, state, meta: progress_updates.append({"state": state, **meta}),
    )

    result = run_rag_evaluation_task.run(
        {"dataset_path": "deepseek.json", "collection_id": "collection-1"},
        "user-1",
    )

    assert [item["completed_cases"] for item in progress_updates] == [0, 1, 2]
    assert all(item["total_cases"] == 2 for item in progress_updates)
    assert result["report_id"] == "report-1"
