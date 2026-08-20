from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.schemas.rag_eval import (
    RagEvaluationDataset,
    RagEvaluationDatasetSummary,
    RagEvaluationRunRequest,
    RagEvaluationStoredReport,
    RagEvaluationStoredReportSummary,
)
from app.services.rag_evaluation_service import RagEvaluationService

_SAFE_FILE_STEM_PATTERN = re.compile(r"[^a-z0-9_-]+")
logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _created_at_timestamp(value: str) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return float("-inf")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


class RagEvaluationReportService:
    def __init__(self, settings: Settings, evaluation_service: RagEvaluationService):
        self.settings = settings
        self.evaluation_service = evaluation_service

    def list_datasets(self) -> list[RagEvaluationDatasetSummary]:
        dataset_files = sorted(
            path
            for path in self._iter_dataset_files()
            if self._is_dataset_file(path)
        )

        datasets: list[RagEvaluationDatasetSummary] = []
        for dataset_file in dataset_files:
            dataset = self._load_dataset(dataset_file)
            datasets.append(
                RagEvaluationDatasetSummary(
                    dataset_path=self._relative_dataset_path(dataset_file),
                    dataset_name=dataset.dataset_name,
                    description=dataset.description,
                    case_count=len(dataset.cases),
                    updated_at=datetime.fromtimestamp(dataset_file.stat().st_mtime, timezone.utc).isoformat(),
                )
            )
        return datasets

    def list_reports(self) -> list[RagEvaluationStoredReportSummary]:
        report_files = self.settings.eval_report_dir.glob("*.json")
        reports: list[RagEvaluationStoredReportSummary] = []
        for report_file in report_files:
            try:
                stored_report = RagEvaluationStoredReport.model_validate_json(
                    report_file.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, ValidationError) as exc:
                logger.warning(
                    "Skipping invalid RAG evaluation report '%s': %s",
                    report_file.name,
                    exc,
                    extra={
                        "extra_fields": {
                            "event": "rag.evaluation.report.skipped",
                            "report_filename": report_file.name,
                            "error": str(exc),
                        }
                    },
                )
                continue
            reports.append(
                RagEvaluationStoredReportSummary(
                    report_id=stored_report.report_id,
                    report_filename=stored_report.report_filename,
                    dataset_path=stored_report.dataset_path,
                    created_at=stored_report.created_at,
                    answer_mode=stored_report.answer_mode,
                    llm_judge_mode=stored_report.llm_judge_mode,
                    dataset_name=stored_report.report.dataset_name,
                    evaluated_at=stored_report.report.evaluated_at,
                    summary=stored_report.report.summary,
                )
            )
        reports.sort(key=lambda report: _created_at_timestamp(report.created_at), reverse=True)
        return reports

    def get_report(self, report_id: str) -> RagEvaluationStoredReport:
        report_path = self.settings.eval_report_dir / f"{report_id}.json"
        if not report_path.exists():
            raise NotFoundError(
                code="RAG_EVAL_REPORT_NOT_FOUND",
                message=f"RAG evaluation report '{report_id}' not found.",
            )
        return RagEvaluationStoredReport.model_validate_json(report_path.read_text(encoding="utf-8"))

    def get_dataset_case_count(self, dataset_path: str) -> int:
        resolved_path = self._resolve_dataset_path(dataset_path)
        return len(self._load_dataset(resolved_path).cases)

    def run_evaluation(
        self,
        payload: RagEvaluationRunRequest,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> RagEvaluationStoredReport:
        dataset_path = self._resolve_dataset_path(payload.dataset_path)
        dataset = self._load_dataset(dataset_path)

        report = self.evaluation_service.evaluate_retrieval_dataset(
            dataset,
            collection_id_override=payload.collection_id,
            top_k_override=payload.top_k,
            use_hybrid_search_override=payload.use_hybrid_search,
            use_rerank_override=payload.use_rerank,
            answer_mode=payload.answer_mode,
            llm_judge_mode=payload.llm_judge_mode,
            progress_callback=progress_callback,
        )

        created_at = _utc_now()
        report_id = self._build_report_id(dataset.dataset_name)
        stored_report = RagEvaluationStoredReport(
            report_id=report_id,
            report_filename=f"{report_id}.json",
            dataset_path=self._relative_dataset_path(dataset_path),
            created_at=created_at,
            answer_mode=payload.answer_mode,
            llm_judge_mode=payload.llm_judge_mode,
            report=report,
        )

        if payload.persist:
            report_path = self.settings.eval_report_dir / stored_report.report_filename
            report_path.write_text(
                json.dumps(stored_report.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return stored_report

    def _resolve_dataset_path(self, dataset_path: str) -> Path:
        requested_path = (self.settings.eval_data_dir / dataset_path).resolve()
        eval_root = self.settings.eval_data_dir.resolve()

        if eval_root not in requested_path.parents and requested_path != eval_root:
            raise BadRequestError(
                code="RAG_EVAL_DATASET_PATH_INVALID",
                message="Dataset path must stay within data/evals.",
            )
        if not requested_path.exists() or not requested_path.is_file():
            raise NotFoundError(
                code="RAG_EVAL_DATASET_NOT_FOUND",
                message=f"RAG evaluation dataset '{dataset_path}' not found.",
            )
        if requested_path.suffix.lower() not in {".json", ".jsonl"}:
            raise BadRequestError(
                code="RAG_EVAL_DATASET_INVALID",
                message="Only JSON and JSONL datasets are supported.",
            )
        if not self._is_dataset_file(requested_path):
            raise BadRequestError(
                code="RAG_EVAL_DATASET_INVALID",
                message="Report files cannot be used as source datasets.",
            )
        return requested_path

    def _relative_dataset_path(self, dataset_path: Path) -> str:
        return dataset_path.resolve().relative_to(self.settings.eval_data_dir.resolve()).as_posix()

    def _is_dataset_file(self, file_path: Path) -> bool:
        reports_root = self.settings.eval_report_dir.resolve()
        resolved = file_path.resolve()
        return reports_root not in resolved.parents and resolved != reports_root

    def _build_report_id(self, dataset_name: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safe_name = _SAFE_FILE_STEM_PATTERN.sub("-", dataset_name.strip().lower()).strip("-") or "rag-eval"
        return f"{timestamp}-{safe_name}"

    def _iter_dataset_files(self) -> list[Path]:
        return [
            *self.settings.eval_data_dir.rglob("*.json"),
            *self.settings.eval_data_dir.rglob("*.jsonl"),
        ]

    def _load_dataset(self, dataset_path: Path) -> RagEvaluationDataset:
        if dataset_path.suffix.lower() == ".jsonl":
            return self._load_jsonl_dataset(dataset_path)
        return RagEvaluationDataset.model_validate_json(dataset_path.read_text(encoding="utf-8"))

    def _load_jsonl_dataset(self, dataset_path: Path) -> RagEvaluationDataset:
        cases = []
        dataset_name = dataset_path.stem
        description = "JSONL RAG evaluation dataset"

        for line_number, raw_line in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise BadRequestError(
                    code="RAG_EVAL_DATASET_INVALID",
                    message=f"JSONL line {line_number} must be an object.",
                )
            dataset_name = payload.pop("dataset_name", dataset_name)
            description = payload.pop("description", description)
            payload.setdefault("case_id", f"case-{line_number}")
            cases.append(payload)

        return RagEvaluationDataset.model_validate(
            {
                "dataset_name": dataset_name,
                "description": description,
                "cases": cases,
            }
        )
