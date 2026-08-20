from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_rag_evaluation_report_service, get_task_queue_service
from app.main import create_app


class FakeRagEvaluationReportService:
    def list_datasets(self):
        return [
            {
                "dataset_path": "sample_retrieval_eval.json",
                "dataset_name": "sample-retrieval-eval",
                "description": "Sample dataset",
                "case_count": 2,
                "updated_at": "2026-05-08T00:00:00+00:00",
            }
        ]

    def list_reports(self):
        return [
            {
                "report_id": "report-1",
                "report_filename": "report-1.json",
                "dataset_path": "sample_retrieval_eval.json",
                "created_at": "2026-05-08T00:00:00+00:00",
                "answer_mode": "dataset",
                "llm_judge_mode": "auto",
                "dataset_name": "sample-retrieval-eval",
                "evaluated_at": "2026-05-08T00:00:00+00:00",
                "summary": {
                    "dataset_name": "sample-retrieval-eval",
                    "total_cases": 2,
                    "top_k": 5,
                    "primary_metrics": {
                        "case_count": 2,
                        "precision_at_k": 1.0,
                        "recall_at_k": 1.0,
                        "hit_rate_at_k": 1.0,
                        "mrr_at_k": 1.0,
                        "average_precision_at_k": 1.0,
                        "ndcg_at_k": 1.0,
                    },
                },
            }
        ]

    def get_report(self, report_id: str):
        assert report_id == "report-1"
        return {
            "report_id": "report-1",
            "report_filename": "report-1.json",
            "dataset_path": "sample_retrieval_eval.json",
            "created_at": "2026-05-08T00:00:00+00:00",
            "answer_mode": "dataset",
            "llm_judge_mode": "auto",
            "report": {
                "dataset_name": "sample-retrieval-eval",
                "description": "Sample dataset",
                "evaluated_at": "2026-05-08T00:00:00+00:00",
                "summary": {
                    "dataset_name": "sample-retrieval-eval",
                    "total_cases": 2,
                    "top_k": 5,
                    "primary_metrics": {
                        "case_count": 2,
                        "precision_at_k": 1.0,
                        "recall_at_k": 1.0,
                        "hit_rate_at_k": 1.0,
                        "mrr_at_k": 1.0,
                        "average_precision_at_k": 1.0,
                        "ndcg_at_k": 1.0,
                    },
                },
                "case_results": [],
            },
        }

    def get_dataset_case_count(self, dataset_path: str) -> int:
        assert dataset_path == "sample_retrieval_eval.json"
        return 31


class FakeTaskQueueService:
    def enqueue_rag_evaluation(self, payload, owner_id: str) -> str:
        assert payload.dataset_path == "sample_retrieval_eval.json"
        assert payload.answer_mode == "dataset"
        assert payload.llm_judge_mode == "auto"
        assert owner_id == "user-1"
        return "task-1"

    def get_rag_evaluation_status(self, task_id: str, owner_id: str):
        assert task_id == "task-1"
        assert owner_id == "user-1"
        return {
            "task_id": task_id,
            "status": "running",
            "completed_cases": 12,
            "total_cases": 31,
            "report_id": None,
            "stored_report": None,
            "error": None,
        }


def build_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-1", "username": "alice"}
    app.dependency_overrides[get_rag_evaluation_report_service] = lambda: FakeRagEvaluationReportService()
    app.dependency_overrides[get_task_queue_service] = lambda: FakeTaskQueueService()
    return TestClient(app)


def test_list_rag_evaluation_datasets() -> None:
    client = build_client()

    response = client.get("/api/v1/evaluations/rag/datasets")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["dataset_name"] == "sample-retrieval-eval"


def test_list_rag_evaluation_reports() -> None:
    client = build_client()

    response = client.get("/api/v1/evaluations/rag/reports")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["report_id"] == "report-1"


def test_get_rag_evaluation_report() -> None:
    client = build_client()

    response = client.get("/api/v1/evaluations/rag/reports/report-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["report"]["dataset_name"] == "sample-retrieval-eval"


def test_run_rag_evaluation() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/evaluations/rag/run",
        json={
            "dataset_path": "sample_retrieval_eval.json",
            "answer_mode": "dataset",
            "llm_judge_mode": "auto",
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload == {
        "task_id": "task-1",
        "status": "queued",
        "completed_cases": 0,
        "total_cases": 31,
        "report_id": None,
        "stored_report": None,
        "error": None,
    }


def test_get_rag_evaluation_run_progress() -> None:
    client = build_client()

    response = client.get("/api/v1/evaluations/rag/runs/task-1")

    assert response.status_code == 200
    assert response.json()["completed_cases"] == 12
    assert response.json()["total_cases"] == 31
