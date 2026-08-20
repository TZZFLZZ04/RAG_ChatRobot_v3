from pathlib import Path
from types import SimpleNamespace
import json
import logging

from app.schemas.rag_eval import RagEvaluationReport, RagEvaluationRunRequest
from app.services.rag_evaluation_report_service import RagEvaluationReportService


class FakeRagEvaluationService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def evaluate_retrieval_dataset(
        self,
        dataset,
        *,
        collection_id_override=None,
        top_k_override=None,
        use_hybrid_search_override=None,
        use_rerank_override=None,
        answer_mode="auto",
        llm_judge_mode="off",
        progress_callback=None,
    ):
        self.calls.append(
            {
                "dataset_name": dataset.dataset_name,
                "collection_id_override": collection_id_override,
                "top_k_override": top_k_override,
                "use_hybrid_search_override": use_hybrid_search_override,
                "use_rerank_override": use_rerank_override,
                "answer_mode": answer_mode,
                "llm_judge_mode": llm_judge_mode,
                "progress_callback": progress_callback,
            }
        )
        return RagEvaluationReport.model_validate(
            {
                "dataset_name": dataset.dataset_name,
                "description": dataset.description,
                "evaluated_at": "2026-05-08T00:00:00+00:00",
                "summary": {
                    "dataset_name": dataset.dataset_name,
                    "total_cases": len(dataset.cases),
                    "top_k": dataset.default_top_k,
                    "primary_metrics": {
                        "case_count": len(dataset.cases),
                        "precision_at_k": 1.0,
                        "recall_at_k": 1.0,
                        "hit_rate_at_k": 1.0,
                        "mrr_at_k": 1.0,
                        "average_precision_at_k": 1.0,
                        "ndcg_at_k": 1.0,
                    },
                },
                "case_results": [],
            }
        )


def build_service(tmp_path: Path) -> tuple[RagEvaluationReportService, FakeRagEvaluationService]:
    eval_dir = tmp_path / "evals"
    report_dir = eval_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    settings = SimpleNamespace(
        eval_data_dir=eval_dir,
        eval_report_dir=report_dir,
    )
    evaluation_service = FakeRagEvaluationService()
    return RagEvaluationReportService(settings, evaluation_service), evaluation_service


def write_dataset(eval_dir: Path, relative_path: str = "sample.json") -> Path:
    dataset_path = eval_dir / relative_path
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_text(
        """
        {
          "dataset_name": "sample-retrieval-eval",
          "description": "Sample dataset",
          "default_collection_id": "collection-1",
          "default_top_k": 3,
          "cases": [
            {
              "case_id": "case-1",
              "query": "员工年假制度是什么？",
              "relevant_document_ids": ["document-1"]
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )
    return dataset_path


def test_list_datasets_returns_available_dataset_files(tmp_path: Path) -> None:
    service, _ = build_service(tmp_path)
    write_dataset(service.settings.eval_data_dir, "baseline/sample.json")

    datasets = service.list_datasets()

    assert len(datasets) == 1
    assert datasets[0].dataset_name == "sample-retrieval-eval"
    assert datasets[0].dataset_path == "baseline/sample.json"
    assert datasets[0].case_count == 1


def test_list_and_run_jsonl_dataset_files(tmp_path: Path) -> None:
    service, fake_eval_service = build_service(tmp_path)
    dataset_path = service.settings.eval_data_dir / "offline.jsonl"
    dataset_path.write_text(
        """
        {"dataset_name":"offline-rag-eval","case_id":"case-1","query":"employee handbook","collection_id":"collection-1","expected_sources":["employee-handbook.pdf"]}
        """.strip(),
        encoding="utf-8",
    )

    datasets = service.list_datasets()
    stored_report = service.run_evaluation(RagEvaluationRunRequest(dataset_path="offline.jsonl", persist=False))

    assert datasets[0].dataset_name == "offline-rag-eval"
    assert datasets[0].dataset_path == "offline.jsonl"
    assert datasets[0].case_count == 1
    assert fake_eval_service.calls[0]["dataset_name"] == "offline-rag-eval"
    assert stored_report.dataset_path == "offline.jsonl"


def test_run_evaluation_persists_report_and_can_be_loaded(tmp_path: Path) -> None:
    service, fake_eval_service = build_service(tmp_path)
    write_dataset(service.settings.eval_data_dir, "sample.json")

    stored_report = service.run_evaluation(
        RagEvaluationRunRequest(
            dataset_path="sample.json",
            answer_mode="dataset",
            llm_judge_mode="auto",
            persist=True,
        )
    )

    assert fake_eval_service.calls[0]["answer_mode"] == "dataset"
    assert fake_eval_service.calls[0]["llm_judge_mode"] == "auto"
    assert stored_report.report.dataset_name == "sample-retrieval-eval"

    loaded_report = service.get_report(stored_report.report_id)
    listed_reports = service.list_reports()

    assert loaded_report.report_id == stored_report.report_id
    assert listed_reports[0].report_id == stored_report.report_id
    assert listed_reports[0].dataset_name == "sample-retrieval-eval"


def test_get_report_upgrades_legacy_source_only_zero_metrics(tmp_path: Path) -> None:
    service, _ = build_service(tmp_path)
    legacy_report = {
        "report_id": "legacy-source-only",
        "report_filename": "legacy-source-only.json",
        "dataset_path": "legacy.json",
        "created_at": "2026-08-17T00:00:00+00:00",
        "answer_mode": "off",
        "llm_judge_mode": "off",
        "report": {
            "dataset_name": "legacy-source-only",
            "evaluated_at": "2026-08-17T00:00:00+00:00",
            "summary": {
                "dataset_name": "legacy-source-only",
                "total_cases": 1,
                "top_k": 5,
                "primary_metrics": {
                    "case_count": 1,
                    "precision_at_k": 0.0,
                    "recall_at_k": 0.0,
                    "hit_rate_at_k": 0.0,
                    "mrr_at_k": 0.0,
                    "average_precision_at_k": 0.0,
                    "ndcg_at_k": 0.0,
                },
                "source_metrics": {
                    "case_count": 1,
                    "source_match": 1.0,
                    "source_hit_rate": 1.0,
                },
            },
            "case_results": [
                {
                    "case_id": "case-1",
                    "query": "legacy query",
                    "collection_id": "collection-1",
                    "top_k": 5,
                    "expected_sources": ["legacy.pdf"],
                    "retrieved": [
                        {
                            "rank": 1,
                            "document_id": "document-1",
                            "chunk_id": "chunk-1",
                            "source_name": "legacy.pdf",
                        }
                    ],
                    "primary_label_level": "document",
                    "primary_metrics": {
                        "precision_at_k": 0.0,
                        "recall_at_k": 0.0,
                        "hit_rate_at_k": 0.0,
                        "mrr_at_k": 0.0,
                        "average_precision_at_k": 0.0,
                        "ndcg_at_k": 0.0,
                        "relevant_retrieved_count": 0,
                        "relevant_total_count": 0,
                    },
                    "source_metrics": {
                        "source_match": 1.0,
                        "source_hit_rate": 1.0,
                        "matched_sources": ["legacy.pdf"],
                        "expected_source_count": 1,
                    },
                }
            ],
        },
    }
    report_path = service.settings.eval_report_dir / "legacy-source-only.json"
    report_path.write_text(json.dumps(legacy_report), encoding="utf-8")

    loaded = service.get_report("legacy-source-only")

    assert loaded.report.summary.primary_label_level == "source-only"
    assert loaded.report.summary.primary_metrics is None
    assert loaded.report.case_results[0].primary_label_level == "source-only"
    assert loaded.report.case_results[0].primary_metrics is None
    assert loaded.report.case_results[0].retrieved[0].page is None
    assert loaded.report.case_results[0].retrieved[0].content is None
    assert loaded.report.case_results[0].retrieved[0].metadata == {}


def test_list_reports_skips_invalid_files_and_logs_warnings(tmp_path: Path, caplog) -> None:
    service, _ = build_service(tmp_path)
    write_dataset(service.settings.eval_data_dir, "sample.json")
    stored_report = service.run_evaluation(
        RagEvaluationRunRequest(dataset_path="sample.json", persist=True)
    )
    (service.settings.eval_report_dir / "legacy.json").write_text(
        '{"dataset_name": "legacy-report", "case_results": []}',
        encoding="utf-8",
    )
    (service.settings.eval_report_dir / "damaged.json").write_text(
        '{"report_id":',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="app.services.rag_evaluation_report_service"):
        reports = service.list_reports()

    assert [report.report_id for report in reports] == [stored_report.report_id]
    warning_messages = [record.getMessage() for record in caplog.records]
    assert len(warning_messages) == 2
    assert any("legacy.json" in message for message in warning_messages)
    assert any("damaged.json" in message for message in warning_messages)


def test_list_reports_orders_by_created_at_descending(tmp_path: Path) -> None:
    service, _ = build_service(tmp_path)
    write_dataset(service.settings.eval_data_dir, "sample.json")
    base_report = service.run_evaluation(
        RagEvaluationRunRequest(dataset_path="sample.json", persist=False)
    )
    older = base_report.model_copy(
        update={
            "report_id": "z-older",
            "report_filename": "z-older.json",
            "created_at": "2026-05-08T23:00:00+08:00",
        }
    )
    newer = base_report.model_copy(
        update={
            "report_id": "a-newer",
            "report_filename": "a-newer.json",
            "created_at": "2026-05-08T16:00:00+00:00",
        }
    )
    for report in (older, newer):
        (service.settings.eval_report_dir / report.report_filename).write_text(
            json.dumps(report.model_dump(mode="json")),
            encoding="utf-8",
        )

    reports = service.list_reports()

    assert [report.report_id for report in reports] == ["a-newer", "z-older"]


def test_run_evaluation_rejects_report_directory_as_dataset_source(tmp_path: Path) -> None:
    service, _ = build_service(tmp_path)
    report_source = service.settings.eval_report_dir / "bad.json"
    report_source.write_text("{}", encoding="utf-8")

    try:
        service.run_evaluation(RagEvaluationRunRequest(dataset_path="reports/bad.json"))
    except Exception as exc:
        assert "report files cannot be used" in str(exc).lower()
    else:
        raise AssertionError("Expected dataset source validation to fail.")
