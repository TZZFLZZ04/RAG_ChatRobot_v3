from types import SimpleNamespace

import pytest

from app.schemas.chat import RetrievedChunk
from app.schemas.rag_eval import RagEvaluationDataset
from app.services.rag_evaluation_service import RagEvaluationService
import app.services.rag_evaluation_service as rag_evaluation_module
from app.services.retrieval_service import RetrievalService


class FakeVectorStoreService:
    def __init__(self, *, dense_results=None, keyword_results=None) -> None:
        self.dense_results = dense_results or []
        self.keyword_results = keyword_results or []

    def similarity_search(self, *, collection_id: str, query: str, top_k: int, score_threshold: float = 0.0):
        return list(self.dense_results)

    def keyword_search(self, *, collection_id: str, query: str, top_k: int, score_threshold: float = 0.0):
        return list(self.keyword_results)


def make_chunk(
    chunk_id: str,
    *,
    score: float,
    document_id: str = "document-1",
    content: str = "员工年假制度包含年假天数、审批流程和请假规则。",
    metadata: dict | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=document_id,
        chunk_id=chunk_id,
        source_name="employee-handbook.pdf",
        source_path="data/raw/employee-handbook.pdf",
        chunk_index=0,
        score=score,
        content=content,
        metadata=metadata or {},
    )


def build_evaluation_service(
    vector_store_service: FakeVectorStoreService,
    *,
    answer_generator=None,
    llm_judge_evaluator=None,
    openai_api_key: str | None = None,
    retry_count: int = 2,
    retry_base_seconds: float = 0.0,
) -> RagEvaluationService:
    settings = SimpleNamespace(
        rag_top_k=5,
        rag_score_threshold=0.0,
        rag_use_hybrid_search=True,
        rag_use_rerank=False,
        rag_hybrid_candidate_multiplier=3,
        rag_hybrid_rrf_k=60,
        rag_keyword_score_threshold=0.2,
        rag_max_context_chars=8000,
        openai_api_key=openai_api_key,
        openai_model="gpt-4o-mini",
        openai_base_url="https://api.openai.com/v1",
        rag_eval_llm_judge_model="gpt-4o-mini",
        rag_eval_llm_max_retries=retry_count,
        rag_eval_llm_retry_base_seconds=retry_base_seconds,
    )
    retrieval_service = RetrievalService(vector_store_service, settings)
    return RagEvaluationService(
        retrieval_service,
        settings=settings,
        answer_generator=answer_generator,
        llm_judge_evaluator=llm_judge_evaluator,
    )


def test_evaluate_retrieval_dataset_aggregates_primary_answer_and_judge_metrics() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[
            make_chunk("chunk-1", score=0.95, document_id="document-1"),
            make_chunk("chunk-2", score=0.88, document_id="document-2"),
        ],
        keyword_results=[],
    )
    service = build_evaluation_service(
        vector_store,
        llm_judge_evaluator=lambda payload: {
            "overall_score": 0.9,
            "groundedness_score": 0.88,
            "relevance_score": 0.91,
            "completeness_score": 0.87,
            "factual_consistency_score": 0.92,
            "strengths": ["Uses the right policy terms"],
            "weaknesses": ["Could be more detailed"],
            "rationale": f"Judged for {payload['query']}",
        },
    )
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "retrieval-eval",
            "default_collection_id": "collection-1",
            "default_top_k": 2,
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "员工年假制度是什么？",
                    "relevant_chunk_ids": ["chunk-1"],
                    "candidate_answer": "员工年假制度包含年假天数和审批流程。",
                    "expected_answer_contains": ["年假", "审批流程"],
                },
                {
                    "case_id": "case-2",
                    "query": "远程办公审批流程",
                    "relevant_document_ids": ["document-2"],
                    "candidate_answer": "远程办公需要审批流程支持。",
                },
            ],
        }
    )

    report = service.evaluate_retrieval_dataset(
        dataset,
        answer_mode="dataset",
        llm_judge_mode="auto",
    )

    assert report.summary.total_cases == 2
    assert report.summary.primary_metrics.case_count == 2
    assert report.summary.answer_metrics is not None
    assert report.summary.llm_judge_metrics is not None
    assert report.summary.llm_judge_metrics.case_count == 2
    assert report.case_results[0].llm_judge_metrics is not None
    assert report.case_results[0].llm_judge_metrics.overall_score == 0.9


def test_evaluate_retrieval_dataset_reports_progress_after_each_case() -> None:
    service = build_evaluation_service(FakeVectorStoreService())
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "progress-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "问题一",
                    "relevant_document_ids": ["document-1"],
                },
                {
                    "case_id": "case-2",
                    "query": "问题二",
                    "relevant_document_ids": ["document-2"],
                },
            ],
        }
    )
    progress_updates: list[tuple[int, int]] = []

    service.evaluate_retrieval_dataset(
        dataset,
        progress_callback=lambda completed, total: progress_updates.append((completed, total)),
    )

    assert progress_updates == [(1, 2), (2, 2)]


def test_evaluate_retrieval_case_prefers_chunk_labels_when_present() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[
            make_chunk("chunk-2", score=0.97, document_id="document-2"),
            make_chunk("chunk-1", score=0.91, document_id="document-1"),
        ],
        keyword_results=[],
    )
    service = build_evaluation_service(vector_store)
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "retrieval-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "员工年假制度是什么？",
                    "relevant_chunk_ids": ["chunk-1"],
                    "relevant_document_ids": ["document-2"],
                }
            ],
        }
    )

    result = service.evaluate_retrieval_case(dataset.cases[0], dataset=dataset)

    assert result.primary_label_level == "chunk"
    assert result.chunk_metrics is not None
    assert result.document_metrics is not None
    assert result.primary_metrics.mrr_at_k == 0.5
    assert result.document_metrics.mrr_at_k == 1.0
    assert result.latency_metrics is not None
    assert result.latency_metrics.retrieval_ms >= 0


def test_evaluate_retrieval_case_scores_expected_sources() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[
            make_chunk(
                "chunk-1",
                score=0.95,
                document_id="document-1",
            )
        ],
        keyword_results=[],
    )
    service = build_evaluation_service(vector_store)
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "source-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "employee handbook",
                    "expected_sources": ["employee-handbook.pdf"],
                }
            ],
        }
    )

    result = service.evaluate_retrieval_case(dataset.cases[0], dataset=dataset)

    assert result.primary_label_level == "source-only"
    assert result.primary_metrics is None
    assert result.source_metrics is not None
    assert result.source_metrics.source_match == 1.0


def test_source_only_dataset_summary_is_unmeasurable_instead_of_zero() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[make_chunk("chunk-1", score=0.95)],
        keyword_results=[],
    )
    service = build_evaluation_service(vector_store)
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "source-only-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "employee handbook",
                    "expected_sources": ["employee-handbook.pdf"],
                }
            ],
        }
    )

    report = service.evaluate_retrieval_dataset(dataset)

    assert report.summary.primary_label_level == "source-only"
    assert report.summary.primary_metrics is None
    assert report.summary.source_metrics is not None
    assert report.summary.source_metrics.source_match == 1.0


def test_retrieved_item_preserves_page_content_and_metadata() -> None:
    metadata = {
        "page": 0,
        "section": "introduction",
        "retrieval_channels": ["dense", "keyword"],
    }
    vector_store = FakeVectorStoreService(
        dense_results=[
            make_chunk(
                "chunk-1",
                score=0.95,
                content="第一页原始证据内容。",
                metadata=metadata,
            )
        ],
        keyword_results=[],
    )
    service = build_evaluation_service(vector_store)
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "metadata-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "第一页说了什么？",
                    "relevant_chunk_ids": ["chunk-1"],
                }
            ],
        }
    )

    result = service.evaluate_retrieval_case(dataset.cases[0], dataset=dataset)

    assert result.retrieved[0].page == 0
    assert result.retrieved[0].content == "第一页原始证据内容。"
    assert result.retrieved[0].metadata == metadata
    assert result.retrieved[0].retrieval_channels == ["dense", "keyword"]


class FakeRateLimitError(Exception):
    status_code = 429


def test_rate_limit_retries_allow_all_31_cases_to_finish_with_answers_and_judges() -> None:
    answer_attempts: dict[str, int] = {}
    judge_attempts: dict[str, int] = {}

    def answer_generator(query: str, chunks: list[RetrievedChunk]) -> str:
        answer_attempts[query] = answer_attempts.get(query, 0) + 1
        if answer_attempts[query] == 1:
            raise FakeRateLimitError("HTTP 429 answer rate limit")
        return f"{query} 的完整答案"

    def judge_evaluator(payload: dict) -> dict:
        query = payload["query"]
        judge_attempts[query] = judge_attempts.get(query, 0) + 1
        if judge_attempts[query] == 1:
            raise FakeRateLimitError("HTTP 429 judge rate limit")
        return {
            "overall_score": 0.9,
            "groundedness_score": 0.9,
            "relevance_score": 0.9,
            "completeness_score": 0.9,
            "factual_consistency_score": 0.9,
            "strengths": ["complete"],
            "weaknesses": [],
            "rationale": "retry succeeded",
        }

    service = build_evaluation_service(
        FakeVectorStoreService(dense_results=[make_chunk("chunk-1", score=0.95)]),
        answer_generator=answer_generator,
        llm_judge_evaluator=judge_evaluator,
        retry_count=1,
        retry_base_seconds=0.0,
    )
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "31-case-rate-limit-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": f"case-{index}",
                    "query": f"问题 {index}",
                    "expected_sources": ["employee-handbook.pdf"],
                }
                for index in range(1, 32)
            ],
        }
    )

    report = service.evaluate_retrieval_dataset(
        dataset,
        answer_mode="generate",
        llm_judge_mode="auto",
    )

    assert len(report.case_results) == 31
    assert all(result.answer for result in report.case_results)
    assert all(result.llm_judge_metrics is not None for result in report.case_results)
    assert all(answer_attempts[result.query] == 2 for result in report.case_results)
    assert all(judge_attempts[result.query] == 2 for result in report.case_results)
    assert all(sum("HTTP 429" in note for note in result.notes) == 2 for result in report.case_results)


def test_rate_limit_retry_uses_configured_exponential_backoff(monkeypatch) -> None:
    service = build_evaluation_service(
        FakeVectorStoreService(),
        retry_count=3,
        retry_base_seconds=0.25,
    )
    delays: list[float] = []
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            raise FakeRateLimitError("HTTP 429 rate limit")
        return "completed"

    monkeypatch.setattr(rag_evaluation_module, "sleep", delays.append)
    notes: list[str] = []

    result = service._run_with_rate_limit_retry(
        operation=operation,
        operation_name="test operation",
        notes=notes,
    )

    assert result == "completed"
    assert delays == [0.25, 0.5, 1.0]
    assert len(notes) == 3


def test_extract_token_usage_normalizes_openai_response_shapes() -> None:
    service = build_evaluation_service(FakeVectorStoreService())
    usage = service._extract_token_usage(
        SimpleNamespace(
            response_metadata={
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 7,
                    "total_tokens": 17,
                }
            }
        )
    )

    assert usage is not None
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 7
    assert usage.total_tokens == 17


def test_evaluate_retrieval_case_scores_dataset_candidate_answer_groundedness() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[
            make_chunk(
                "chunk-1",
                score=0.95,
                content="员工年假制度包含年假天数、审批流程和请假规则。",
            )
        ],
        keyword_results=[],
    )
    service = build_evaluation_service(vector_store)
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "retrieval-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "员工年假制度是什么？",
                    "relevant_document_ids": ["document-1"],
                    "candidate_answer": "员工年假制度包含年假天数和审批流程。另有报销规则。",
                    "expected_answer_contains": ["年假天数", "审批流程"],
                    "reference_answer": "员工年假制度包含年假天数与审批流程。",
                }
            ],
        }
    )

    result = service.evaluate_retrieval_case(
        dataset.cases[0],
        dataset=dataset,
        answer_mode="dataset",
    )

    assert result.answer_source == "dataset"
    assert result.answer_metrics is not None
    assert result.answer_metrics.expected_term_recall == 1.0
    assert result.answer_metrics.reference_similarity is not None
    assert result.answer_metrics.unsupported_statement_count == 1
    assert "另有报销规则" in result.answer_metrics.unsupported_statements[0]


def test_evaluate_retrieval_case_generates_answer_when_requested() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[make_chunk("chunk-1", score=0.9)],
        keyword_results=[],
    )
    service = build_evaluation_service(
        vector_store,
        answer_generator=lambda query, chunks: "员工年假制度包含年假天数和审批流程。",
    )
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "retrieval-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "员工年假制度是什么？",
                    "relevant_document_ids": ["document-1"],
                    "expected_answer_contains": ["年假天数", "审批流程"],
                }
            ],
        }
    )

    result = service.evaluate_retrieval_case(
        dataset.cases[0],
        dataset=dataset,
        answer_mode="generate",
    )

    assert result.answer_source == "generated"
    assert result.answer == "员工年假制度包含年假天数和审批流程。"
    assert result.answer_metrics is not None
    assert result.answer_metrics.overall_answer_score > 0.5


def test_evaluate_retrieval_case_records_note_when_dataset_answer_missing() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[],
        keyword_results=[],
    )
    service = build_evaluation_service(vector_store)
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "retrieval-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "员工年假制度是什么？",
                    "relevant_document_ids": ["document-1"],
                }
            ],
        }
    )

    result = service.evaluate_retrieval_case(
        dataset.cases[0],
        dataset=dataset,
        answer_mode="dataset",
    )

    assert result.answer is None
    assert result.answer_metrics is None
    assert any("answer_mode=dataset" in note for note in result.notes)
    assert any("No chunks were retrieved" in note for note in result.notes)


def test_llm_judge_auto_mode_skips_when_no_judge_is_available() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[make_chunk("chunk-1", score=0.9)],
        keyword_results=[],
    )
    service = build_evaluation_service(vector_store)
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "retrieval-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "员工年假制度是什么？",
                    "relevant_document_ids": ["document-1"],
                    "candidate_answer": "员工年假制度包含年假天数和审批流程。",
                }
            ],
        }
    )

    result = service.evaluate_retrieval_case(
        dataset.cases[0],
        dataset=dataset,
        answer_mode="dataset",
        llm_judge_mode="auto",
    )

    assert result.llm_judge_metrics is None
    assert any("LLM judge skipped" in note for note in result.notes)


def test_llm_judge_require_mode_raises_when_judge_fails() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[make_chunk("chunk-1", score=0.9)],
        keyword_results=[],
    )
    service = build_evaluation_service(
        vector_store,
        llm_judge_evaluator=lambda payload: (_ for _ in ()).throw(ValueError("judge unavailable")),
    )
    dataset = RagEvaluationDataset.model_validate(
        {
            "dataset_name": "retrieval-eval",
            "default_collection_id": "collection-1",
            "cases": [
                {
                    "case_id": "case-1",
                    "query": "员工年假制度是什么？",
                    "relevant_document_ids": ["document-1"],
                    "candidate_answer": "员工年假制度包含年假天数和审批流程。",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="judge unavailable"):
        service.evaluate_retrieval_case(
            dataset.cases[0],
            dataset=dataset,
            answer_mode="dataset",
            llm_judge_mode="require",
        )
