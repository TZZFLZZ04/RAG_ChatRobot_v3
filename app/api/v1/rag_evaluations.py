from fastapi import APIRouter, Depends, status

from app.api.deps import (
    get_current_user,
    get_rag_evaluation_report_service,
    get_task_queue_service,
)
from app.schemas.rag_eval import (
    RagEvaluationDatasetSummary,
    RagEvaluationRunRequest,
    RagEvaluationStoredReport,
    RagEvaluationStoredReportSummary,
    RagEvaluationTaskStatus,
)
from app.services.rag_evaluation_report_service import RagEvaluationReportService
from app.services.task_queue_service import TaskQueueService

router = APIRouter()


@router.get("/datasets", response_model=list[RagEvaluationDatasetSummary])
def list_rag_evaluation_datasets(
    service: RagEvaluationReportService = Depends(get_rag_evaluation_report_service),
    current_user: dict = Depends(get_current_user),
) -> list[RagEvaluationDatasetSummary]:
    _ = current_user
    return service.list_datasets()


@router.get("/reports", response_model=list[RagEvaluationStoredReportSummary])
def list_rag_evaluation_reports(
    service: RagEvaluationReportService = Depends(get_rag_evaluation_report_service),
    current_user: dict = Depends(get_current_user),
) -> list[RagEvaluationStoredReportSummary]:
    _ = current_user
    return service.list_reports()


@router.get("/reports/{report_id}", response_model=RagEvaluationStoredReport)
def get_rag_evaluation_report(
    report_id: str,
    service: RagEvaluationReportService = Depends(get_rag_evaluation_report_service),
    current_user: dict = Depends(get_current_user),
) -> RagEvaluationStoredReport:
    _ = current_user
    return service.get_report(report_id)


@router.post("/run", response_model=RagEvaluationTaskStatus, status_code=status.HTTP_202_ACCEPTED)
def run_rag_evaluation(
    payload: RagEvaluationRunRequest,
    service: RagEvaluationReportService = Depends(get_rag_evaluation_report_service),
    task_queue_service: TaskQueueService = Depends(get_task_queue_service),
    current_user: dict = Depends(get_current_user),
) -> RagEvaluationTaskStatus:
    total_cases = service.get_dataset_case_count(payload.dataset_path)
    task_id = task_queue_service.enqueue_rag_evaluation(payload, owner_id=current_user["id"])
    return RagEvaluationTaskStatus(
        task_id=task_id,
        status="queued",
        completed_cases=0,
        total_cases=total_cases,
    )


@router.get("/runs/{task_id}", response_model=RagEvaluationTaskStatus)
def get_rag_evaluation_run_status(
    task_id: str,
    task_queue_service: TaskQueueService = Depends(get_task_queue_service),
    current_user: dict = Depends(get_current_user),
) -> RagEvaluationTaskStatus:
    return task_queue_service.get_rag_evaluation_status(task_id, owner_id=current_user["id"])
