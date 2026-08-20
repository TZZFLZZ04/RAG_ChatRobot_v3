from __future__ import annotations

from datetime import datetime, timezone
import json
from math import ceil
from math import log2
from pathlib import Path
import re
from time import perf_counter, sleep
from typing import Any, Callable, Iterable, Literal, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError
from app.rag.prompts import build_system_prompt
from app.rag.retrieval import compute_keyword_score, extract_search_terms, normalize_search_text
from app.schemas.chat import RetrievedChunk
from app.schemas.rag_eval import (
    RagAnswerMetricBundle,
    RagAnswerMetricSummary,
    RagEvaluationCase,
    RagEvaluationCaseResult,
    RagEvaluationDataset,
    RagEvaluationReport,
    RagEvaluationSummary,
    RagLatencyMetricBundle,
    RagLatencyMetricSummary,
    RagLlmJudgeMetricBundle,
    RagLlmJudgeMetricSummary,
    RagMetricBundle,
    RagMetricSummary,
    RagRetrievedItem,
    RagSourceMetricBundle,
    RagSourceMetricSummary,
    RagTokenUsageBundle,
    RagTokenUsageSummary,
)
from app.services.retrieval_service import RetrievalService

T = TypeVar("T")
AnswerMode = Literal["off", "auto", "dataset", "generate"]
JudgeMode = Literal["off", "auto", "require"]

_SENTENCE_SPLIT_PATTERN = re.compile(r"[。！？!?；;\n]+")
_JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ordered_unique(values: Iterable[T]) -> list[T]:
    seen: set[T] = set()
    ordered: list[T] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


class RagEvaluationService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        settings: Settings | None = None,
        answer_generator: Callable[[str, list[RetrievedChunk]], str] | None = None,
        llm_judge_evaluator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ):
        self.retrieval_service = retrieval_service
        self.settings = settings
        self.answer_generator = answer_generator
        self.llm_judge_evaluator = llm_judge_evaluator
        self._answer_llm: ChatOpenAI | None = None
        self._judge_llm: ChatOpenAI | None = None

    def evaluate_retrieval_dataset(
        self,
        dataset: RagEvaluationDataset,
        *,
        collection_id_override: str | None = None,
        top_k_override: int | None = None,
        use_hybrid_search_override: bool | None = None,
        use_rerank_override: bool | None = None,
        answer_mode: AnswerMode = "auto",
        llm_judge_mode: JudgeMode = "off",
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> RagEvaluationReport:
        case_results: list[RagEvaluationCaseResult] = []
        summary_top_k = top_k_override or dataset.default_top_k
        total_cases = len(dataset.cases)

        for completed_cases, case in enumerate(dataset.cases, start=1):
            case_results.append(
                self.evaluate_retrieval_case(
                    case,
                    dataset=dataset,
                    collection_id_override=collection_id_override,
                    top_k_override=top_k_override,
                    use_hybrid_search_override=use_hybrid_search_override,
                    use_rerank_override=use_rerank_override,
                    answer_mode=answer_mode,
                    llm_judge_mode=llm_judge_mode,
                )
            )
            if progress_callback is not None:
                progress_callback(completed_cases, total_cases)

        return RagEvaluationReport(
            dataset_name=dataset.dataset_name,
            description=dataset.description,
            evaluated_at=_utc_now(),
            summary=self._build_summary(
                dataset=dataset,
                case_results=case_results,
                summary_top_k=summary_top_k,
            ),
            case_results=case_results,
        )

    def evaluate_retrieval_case(
        self,
        case: RagEvaluationCase,
        *,
        dataset: RagEvaluationDataset,
        collection_id_override: str | None = None,
        top_k_override: int | None = None,
        use_hybrid_search_override: bool | None = None,
        use_rerank_override: bool | None = None,
        answer_mode: AnswerMode = "auto",
        llm_judge_mode: JudgeMode = "off",
    ) -> RagEvaluationCaseResult:
        collection_id = collection_id_override or case.collection_id or dataset.default_collection_id
        if not collection_id:
            raise ValueError(
                f"Evaluation case '{case.case_id}' is missing collection_id and dataset default_collection_id."
            )

        top_k = top_k_override or case.top_k or dataset.default_top_k
        use_hybrid_search = self._resolve_optional_override(
            use_hybrid_search_override,
            case.use_hybrid_search,
            dataset.default_use_hybrid_search,
        )
        use_rerank = self._resolve_optional_override(
            use_rerank_override,
            case.use_rerank,
            dataset.default_use_rerank,
        )

        retrieval_started_at = perf_counter()
        retrieved_chunks = self.retrieval_service.retrieve(
            query=case.query,
            collection_id=collection_id,
            top_k=top_k,
            use_hybrid_search=use_hybrid_search,
            use_rerank=use_rerank,
        )
        retrieval_ms = (perf_counter() - retrieval_started_at) * 1000

        chunk_metrics = self._build_metrics(
            retrieved_ids=[chunk.chunk_id for chunk in retrieved_chunks],
            relevant_ids=case.relevant_chunk_ids,
            top_k=top_k,
        ) if case.relevant_chunk_ids else None

        document_metrics = self._build_metrics(
            retrieved_ids=_ordered_unique(chunk.document_id for chunk in retrieved_chunks),
            relevant_ids=case.relevant_document_ids,
            top_k=top_k,
        ) if case.relevant_document_ids else None

        if chunk_metrics is not None:
            primary_label_level = "chunk"
            primary_metrics = chunk_metrics
        elif document_metrics is not None:
            primary_label_level = "document"
            primary_metrics = document_metrics
        elif case.expected_sources:
            primary_label_level = "source-only"
            primary_metrics = None
        else:
            primary_label_level = "unavailable"
            primary_metrics = None

        source_metrics = self._build_source_metrics(
            retrieved_chunks=retrieved_chunks[:top_k],
            expected_sources=case.expected_sources,
        ) if case.expected_sources else None

        notes = self._build_case_notes(retrieved_chunks=retrieved_chunks)
        answer_source, answer, answer_token_usage, answer_generation_ms = self._resolve_answer(
            case=case,
            query=case.query,
            retrieved_chunks=retrieved_chunks,
            answer_mode=answer_mode,
            notes=notes,
        )

        answer_metrics = None
        if answer:
            answer_metrics = self._build_answer_metrics(
                query=case.query,
                answer=answer,
                retrieved_chunks=retrieved_chunks,
                expected_answer_contains=case.expected_answer_contains,
                reference_answer=case.reference_answer,
            )

        llm_judge_metrics, llm_judge_ms = self._resolve_llm_judge_metrics(
            case=case,
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            llm_judge_mode=llm_judge_mode,
            notes=notes,
        )
        token_usage = answer_token_usage
        total_ms = retrieval_ms + (answer_generation_ms or 0.0) + (llm_judge_ms or 0.0)

        return RagEvaluationCaseResult(
            case_id=case.case_id,
            query=case.query,
            collection_id=collection_id,
            top_k=top_k,
            relevant_chunk_ids=case.relevant_chunk_ids,
            relevant_document_ids=case.relevant_document_ids,
            expected_sources=case.expected_sources,
            retrieved=[
                RagRetrievedItem(
                    rank=index,
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    source_name=chunk.source_name,
                    source_path=chunk.source_path,
                    score=chunk.score,
                    retrieval_channels=list((chunk.metadata or {}).get("retrieval_channels", [])),
                    page=(chunk.metadata or {}).get("page"),
                    content=chunk.content,
                    metadata=dict(chunk.metadata or {}),
                )
                for index, chunk in enumerate(retrieved_chunks, start=1)
            ],
            primary_label_level=primary_label_level,
            primary_metrics=primary_metrics,
            chunk_metrics=chunk_metrics,
            document_metrics=document_metrics,
            source_metrics=source_metrics,
            answer_source=answer_source,
            answer=answer,
            answer_metrics=answer_metrics,
            llm_judge_metrics=llm_judge_metrics,
            latency_metrics=RagLatencyMetricBundle(
                retrieval_ms=round(retrieval_ms, 3),
                answer_generation_ms=round(answer_generation_ms, 3)
                if answer_generation_ms is not None
                else None,
                llm_judge_ms=round(llm_judge_ms, 3) if llm_judge_ms is not None else None,
                total_ms=round(total_ms, 3),
            ),
            token_usage=token_usage,
            notes=notes,
        )

    def _build_case_notes(
        self,
        *,
        retrieved_chunks: list[RetrievedChunk],
    ) -> list[str]:
        notes: list[str] = []
        if not retrieved_chunks:
            notes.append("No chunks were retrieved for this query.")
        return notes

    def _build_summary(
        self,
        *,
        dataset: RagEvaluationDataset,
        case_results: list[RagEvaluationCaseResult],
        summary_top_k: int,
    ) -> RagEvaluationSummary:
        chunk_metric_bundles = [item.chunk_metrics for item in case_results if item.chunk_metrics is not None]
        document_metric_bundles = [
            item.document_metrics for item in case_results if item.document_metrics is not None
        ]
        answer_metric_bundles = [item.answer_metrics for item in case_results if item.answer_metrics is not None]
        source_metric_bundles = [item.source_metrics for item in case_results if item.source_metrics is not None]
        latency_metric_bundles = [item.latency_metrics for item in case_results if item.latency_metrics is not None]
        token_usage_bundles = [item.token_usage for item in case_results if item.token_usage is not None]
        llm_judge_metric_bundles = [
            item.llm_judge_metrics for item in case_results if item.llm_judge_metrics is not None
        ]
        primary_metric_bundles = [
            item.primary_metrics for item in case_results if item.primary_metrics is not None
        ]
        primary_label_levels = {item.primary_label_level for item in case_results}
        if len(primary_label_levels) == 1:
            primary_label_level = next(iter(primary_label_levels))
        elif primary_label_levels:
            primary_label_level = "mixed"
        else:
            primary_label_level = "unavailable"

        return RagEvaluationSummary(
            dataset_name=dataset.dataset_name,
            total_cases=len(case_results),
            top_k=summary_top_k,
            primary_label_level=primary_label_level,
            primary_metrics=self._aggregate_metric_summary(primary_metric_bundles)
            if primary_metric_bundles
            else None,
            chunk_metrics=self._aggregate_metric_summary(chunk_metric_bundles) if chunk_metric_bundles else None,
            document_metrics=self._aggregate_metric_summary(document_metric_bundles)
            if document_metric_bundles
            else None,
            source_metrics=self._aggregate_source_metric_summary(source_metric_bundles)
            if source_metric_bundles
            else None,
            answer_metrics=self._aggregate_answer_metric_summary(answer_metric_bundles)
            if answer_metric_bundles
            else None,
            llm_judge_metrics=self._aggregate_llm_judge_metric_summary(llm_judge_metric_bundles)
            if llm_judge_metric_bundles
            else None,
            latency_metrics=self._aggregate_latency_metric_summary(latency_metric_bundles)
            if latency_metric_bundles
            else None,
            token_usage=self._aggregate_token_usage_summary(token_usage_bundles)
            if token_usage_bundles
            else None,
        )

    def _aggregate_metric_summary(
        self,
        metric_bundles: list[RagMetricBundle],
    ) -> RagMetricSummary:
        case_count = len(metric_bundles)
        if case_count == 0:
            return RagMetricSummary(
                case_count=0,
                precision_at_k=0.0,
                recall_at_k=0.0,
                hit_rate_at_k=0.0,
                mrr_at_k=0.0,
                average_precision_at_k=0.0,
                ndcg_at_k=0.0,
            )

        return RagMetricSummary(
            case_count=case_count,
            precision_at_k=round(sum(item.precision_at_k for item in metric_bundles) / case_count, 6),
            recall_at_k=round(sum(item.recall_at_k for item in metric_bundles) / case_count, 6),
            hit_rate_at_k=round(sum(item.hit_rate_at_k for item in metric_bundles) / case_count, 6),
            mrr_at_k=round(sum(item.mrr_at_k for item in metric_bundles) / case_count, 6),
            average_precision_at_k=round(
                sum(item.average_precision_at_k for item in metric_bundles) / case_count,
                6,
            ),
            ndcg_at_k=round(sum(item.ndcg_at_k for item in metric_bundles) / case_count, 6),
        )

    def _aggregate_answer_metric_summary(
        self,
        metric_bundles: list[RagAnswerMetricBundle],
    ) -> RagAnswerMetricSummary:
        case_count = len(metric_bundles)
        expected_term_scores = [item.expected_term_recall for item in metric_bundles if item.expected_term_recall is not None]
        reference_scores = [item.reference_similarity for item in metric_bundles if item.reference_similarity is not None]

        return RagAnswerMetricSummary(
            case_count=case_count,
            overall_answer_score=round(sum(item.overall_answer_score for item in metric_bundles) / case_count, 6),
            expected_term_recall=round(sum(expected_term_scores) / len(expected_term_scores), 6)
            if expected_term_scores
            else None,
            query_term_coverage=round(sum(item.query_term_coverage for item in metric_bundles) / case_count, 6),
            groundedness_score=round(sum(item.groundedness_score for item in metric_bundles) / case_count, 6),
            grounded_sentence_ratio=round(
                sum(item.grounded_sentence_ratio for item in metric_bundles) / case_count,
                6,
            ),
            reference_similarity=round(sum(reference_scores) / len(reference_scores), 6)
            if reference_scores
            else None,
            unsupported_statement_count=round(
                sum(item.unsupported_statement_count for item in metric_bundles) / case_count,
                6,
            ),
        )

    def _aggregate_source_metric_summary(
        self,
        metric_bundles: list[RagSourceMetricBundle],
    ) -> RagSourceMetricSummary:
        case_count = len(metric_bundles)
        return RagSourceMetricSummary(
            case_count=case_count,
            source_match=round(sum(item.source_match for item in metric_bundles) / case_count, 6),
            source_hit_rate=round(sum(item.source_hit_rate for item in metric_bundles) / case_count, 6),
        )

    def _aggregate_latency_metric_summary(
        self,
        metric_bundles: list[RagLatencyMetricBundle],
    ) -> RagLatencyMetricSummary:
        retrieval_values = [item.retrieval_ms for item in metric_bundles]
        answer_values = [
            item.answer_generation_ms
            for item in metric_bundles
            if item.answer_generation_ms is not None
        ]
        judge_values = [
            item.llm_judge_ms
            for item in metric_bundles
            if item.llm_judge_ms is not None
        ]
        total_values = [item.total_ms for item in metric_bundles]

        return RagLatencyMetricSummary(
            case_count=len(metric_bundles),
            avg_retrieval_ms=self._average(retrieval_values),
            p50_retrieval_ms=self._percentile(retrieval_values, 50),
            p95_retrieval_ms=self._percentile(retrieval_values, 95),
            max_retrieval_ms=round(max(retrieval_values), 3),
            avg_answer_generation_ms=self._average(answer_values) if answer_values else None,
            p50_answer_generation_ms=self._percentile(answer_values, 50) if answer_values else None,
            p95_answer_generation_ms=self._percentile(answer_values, 95) if answer_values else None,
            max_answer_generation_ms=round(max(answer_values), 3) if answer_values else None,
            avg_llm_judge_ms=self._average(judge_values) if judge_values else None,
            p50_llm_judge_ms=self._percentile(judge_values, 50) if judge_values else None,
            p95_llm_judge_ms=self._percentile(judge_values, 95) if judge_values else None,
            max_llm_judge_ms=round(max(judge_values), 3) if judge_values else None,
            avg_total_ms=self._average(total_values),
            p50_total_ms=self._percentile(total_values, 50),
            p95_total_ms=self._percentile(total_values, 95),
            max_total_ms=round(max(total_values), 3),
        )

    def _aggregate_token_usage_summary(
        self,
        token_usage_bundles: list[RagTokenUsageBundle],
    ) -> RagTokenUsageSummary:
        case_count = len(token_usage_bundles)
        prompt_tokens = sum(item.prompt_tokens for item in token_usage_bundles)
        completion_tokens = sum(item.completion_tokens for item in token_usage_bundles)
        total_tokens = sum(item.total_tokens for item in token_usage_bundles)
        return RagTokenUsageSummary(
            case_count=case_count,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            avg_prompt_tokens=round(prompt_tokens / case_count, 3),
            avg_completion_tokens=round(completion_tokens / case_count, 3),
            avg_total_tokens=round(total_tokens / case_count, 3),
        )

    def _aggregate_llm_judge_metric_summary(
        self,
        metric_bundles: list[RagLlmJudgeMetricBundle],
    ) -> RagLlmJudgeMetricSummary:
        case_count = len(metric_bundles)
        return RagLlmJudgeMetricSummary(
            case_count=case_count,
            overall_score=round(sum(item.overall_score for item in metric_bundles) / case_count, 6),
            groundedness_score=round(sum(item.groundedness_score for item in metric_bundles) / case_count, 6),
            relevance_score=round(sum(item.relevance_score for item in metric_bundles) / case_count, 6),
            completeness_score=round(sum(item.completeness_score for item in metric_bundles) / case_count, 6),
            factual_consistency_score=round(
                sum(item.factual_consistency_score for item in metric_bundles) / case_count,
                6,
            ),
        )

    def _build_metrics(
        self,
        *,
        retrieved_ids: list[str],
        relevant_ids: list[str],
        top_k: int,
    ) -> RagMetricBundle:
        relevant_set = set(relevant_ids)
        ranked_ids = retrieved_ids[:top_k]
        binary_relevance = [1 if item_id in relevant_set else 0 for item_id in ranked_ids]
        relevant_retrieved_count = sum(binary_relevance)
        relevant_total_count = len(relevant_set)

        precision = relevant_retrieved_count / len(ranked_ids) if ranked_ids else 0.0
        recall = relevant_retrieved_count / relevant_total_count if relevant_total_count else 0.0
        hit_rate = 1.0 if relevant_retrieved_count > 0 else 0.0

        reciprocal_rank = 0.0
        for index, is_relevant in enumerate(binary_relevance, start=1):
            if is_relevant:
                reciprocal_rank = 1.0 / index
                break

        precision_sum = 0.0
        hits_so_far = 0
        for index, is_relevant in enumerate(binary_relevance, start=1):
            if not is_relevant:
                continue
            hits_so_far += 1
            precision_sum += hits_so_far / index
        average_precision = precision_sum / relevant_total_count if relevant_total_count else 0.0

        dcg = sum(is_relevant / log2(index + 1) for index, is_relevant in enumerate(binary_relevance, start=1))
        ideal_relevance = [1] * min(relevant_total_count, len(ranked_ids))
        idcg = sum(is_relevant / log2(index + 1) for index, is_relevant in enumerate(ideal_relevance, start=1))
        ndcg = dcg / idcg if idcg else 0.0

        return RagMetricBundle(
            precision_at_k=round(precision, 6),
            recall_at_k=round(recall, 6),
            hit_rate_at_k=round(hit_rate, 6),
            mrr_at_k=round(reciprocal_rank, 6),
            average_precision_at_k=round(average_precision, 6),
            ndcg_at_k=round(ndcg, 6),
            relevant_retrieved_count=relevant_retrieved_count,
            relevant_total_count=relevant_total_count,
        )

    def _build_source_metrics(
        self,
        *,
        retrieved_chunks: list[RetrievedChunk],
        expected_sources: list[str],
    ) -> RagSourceMetricBundle:
        retrieved_identifiers: set[str] = set()
        for chunk in retrieved_chunks:
            retrieved_identifiers.update(self._source_identifiers(chunk))

        matched_sources: list[str] = []
        for expected_source in expected_sources:
            normalized_expected = self._normalize_source_identifier(expected_source)
            if any(
                normalized_expected == candidate
                or normalized_expected in candidate
                or candidate in normalized_expected
                for candidate in retrieved_identifiers
            ):
                matched_sources.append(expected_source)

        return RagSourceMetricBundle(
            source_match=round(len(matched_sources) / len(expected_sources), 6)
            if expected_sources
            else 0.0,
            source_hit_rate=1.0 if matched_sources else 0.0,
            matched_sources=matched_sources,
            expected_source_count=len(expected_sources),
        )

    def _resolve_answer(
        self,
        *,
        case: RagEvaluationCase,
        query: str,
        retrieved_chunks: list[RetrievedChunk],
        answer_mode: AnswerMode,
        notes: list[str],
    ) -> tuple[str | None, str | None, RagTokenUsageBundle | None, float | None]:
        if answer_mode == "off":
            return None, None, None, None

        if answer_mode in {"auto", "dataset"} and case.candidate_answer:
            return "dataset", case.candidate_answer, None, None

        if answer_mode == "dataset":
            notes.append("answer_mode=dataset but candidate_answer is missing, so answer scoring was skipped.")
            return None, None, None, None

        if answer_mode in {"auto", "generate"}:
            try:
                started_at = perf_counter()
                answer, token_usage = self._run_with_rate_limit_retry(
                    operation=lambda: self._generate_answer(
                        query=query,
                        retrieved_chunks=retrieved_chunks,
                    ),
                    operation_name="Automatic answer generation",
                    notes=notes,
                )
                return "generated", answer, token_usage, (perf_counter() - started_at) * 1000
            except Exception as exc:
                notes.append(f"Automatic answer generation failed: {exc}")
                return None, None, None, None

        return None, None, None, None

    def _resolve_llm_judge_metrics(
        self,
        *,
        case: RagEvaluationCase,
        answer: str | None,
        retrieved_chunks: list[RetrievedChunk],
        llm_judge_mode: JudgeMode,
        notes: list[str],
    ) -> tuple[RagLlmJudgeMetricBundle | None, float | None]:
        if llm_judge_mode == "off":
            return None, None
        if not answer:
            notes.append("LLM judge skipped because no answer was available.")
            return None, None

        if llm_judge_mode == "auto" and not self._can_run_llm_judge():
            notes.append("LLM judge skipped because no judge evaluator or OpenAI API key is available.")
            return None, None

        try:
            started_at = perf_counter()
            result = self._run_with_rate_limit_retry(
                operation=lambda: self._run_llm_judge(
                    query=case.query,
                    answer=answer,
                    retrieved_chunks=retrieved_chunks,
                    expected_answer_contains=case.expected_answer_contains,
                    reference_answer=case.reference_answer,
                ),
                operation_name="LLM judge evaluation",
                notes=notes,
            )
            return result, (perf_counter() - started_at) * 1000
        except Exception as exc:
            notes.append(f"LLM judge evaluation failed: {exc}")
            if llm_judge_mode == "require":
                raise
            return None, None

    def _run_with_rate_limit_retry(
        self,
        *,
        operation: Callable[[], T],
        operation_name: str,
        notes: list[str],
    ) -> T:
        max_retries = max(int(getattr(self.settings, "rag_eval_llm_max_retries", 5)), 0)
        base_seconds = max(float(getattr(self.settings, "rag_eval_llm_retry_base_seconds", 1.0)), 0.0)
        for retry_index in range(max_retries + 1):
            try:
                return operation()
            except Exception as exc:
                if not self._is_rate_limit_error(exc) or retry_index >= max_retries:
                    raise
                delay_seconds = base_seconds * (2**retry_index)
                notes.append(
                    f"{operation_name} failed with HTTP 429; retry "
                    f"{retry_index + 1}/{max_retries} in {delay_seconds:g}s."
                )
                if delay_seconds:
                    sleep(delay_seconds)
        raise RuntimeError(f"{operation_name} retry loop ended unexpectedly.")

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        if getattr(exc, "status_code", None) == 429:
            return True
        response = getattr(exc, "response", None)
        if getattr(response, "status_code", None) == 429:
            return True
        message = str(exc).lower()
        return "429" in message and (
            "rate limit" in message or "too many requests" in message
        )

    def _generate_answer(self, *, query: str, retrieved_chunks: list[RetrievedChunk]) -> tuple[str, RagTokenUsageBundle | None]:
        if self.answer_generator is not None:
            return self.answer_generator(query, retrieved_chunks), None

        llm = self._get_answer_llm()
        context = self._build_context(retrieved_chunks)
        response = llm.invoke(
            [
                SystemMessage(content=build_system_prompt(context)),
                HumanMessage(content=query),
            ]
        )
        return self._normalize_content(response.content).strip(), self._extract_token_usage(response)

    def _run_llm_judge(
        self,
        *,
        query: str,
        answer: str,
        retrieved_chunks: list[RetrievedChunk],
        expected_answer_contains: list[str],
        reference_answer: str | None,
    ) -> RagLlmJudgeMetricBundle:
        payload = {
            "query": query,
            "answer": answer,
            "retrieved_context": [
                {
                    "rank": index,
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.chunk_id,
                    "source_name": chunk.source_name,
                    "content": chunk.content,
                }
                for index, chunk in enumerate(retrieved_chunks, start=1)
            ],
            "expected_answer_contains": expected_answer_contains,
            "reference_answer": reference_answer,
        }

        if self.llm_judge_evaluator is not None:
            result = self.llm_judge_evaluator(payload)
            return RagLlmJudgeMetricBundle.model_validate(result)

        llm = self._get_judge_llm()
        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "You are an expert RAG evaluator. "
                        "Judge the answer against the query and retrieved context. "
                        "Return JSON only with keys: overall_score, groundedness_score, relevance_score, "
                        "completeness_score, factual_consistency_score, strengths, weaknesses, rationale. "
                        "All score fields must be floats between 0 and 1. "
                        "Groundedness means whether the answer is supported by the retrieved context. "
                        "Factual consistency means whether the answer avoids contradicting the context or reference answer. "
                        "Keep strengths and weaknesses concise with at most 3 items each."
                    )
                ),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False, indent=2)),
            ]
        )
        parsed = self._parse_llm_judge_response(self._normalize_content(response.content))
        return RagLlmJudgeMetricBundle.model_validate(parsed)

    def _can_run_llm_judge(self) -> bool:
        if self.llm_judge_evaluator is not None:
            return True
        return bool(self.settings and self.settings.openai_api_key)

    def _get_answer_llm(self) -> ChatOpenAI:
        if self.answer_generator is not None:
            raise ServiceUnavailableError(
                code="ANSWER_GENERATOR_NOT_REQUIRED",
                message="A custom answer generator was provided; LLM initialization is not required.",
            )
        if self.settings is None:
            raise ServiceUnavailableError(
                code="EVAL_SETTINGS_REQUIRED",
                message="Settings are required for automatic answer generation.",
            )
        if self._answer_llm is None:
            if not self.settings.openai_api_key:
                raise ServiceUnavailableError(
                    code="OPENAI_API_KEY_MISSING",
                    message="OPENAI_API_KEY is required for automatic answer generation.",
                )
            self._answer_llm = ChatOpenAI(
                model=self.settings.openai_model,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                temperature=0,
                timeout=60,
                max_retries=0,
            )
        return self._answer_llm

    def _get_judge_llm(self) -> ChatOpenAI:
        if self.settings is None:
            raise ServiceUnavailableError(
                code="EVAL_SETTINGS_REQUIRED",
                message="Settings are required for LLM judge evaluation.",
            )
        if self._judge_llm is None:
            if not self.settings.openai_api_key:
                raise ServiceUnavailableError(
                    code="OPENAI_API_KEY_MISSING",
                    message="OPENAI_API_KEY is required for LLM judge evaluation.",
                )
            model_name = self.settings.rag_eval_llm_judge_model or self.settings.openai_model
            self._judge_llm = ChatOpenAI(
                model=model_name,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                temperature=0,
                timeout=60,
                max_retries=0,
            )
        return self._judge_llm

    def _build_context(self, retrieved_chunks: list[RetrievedChunk]) -> str:
        context = "\n\n".join(
            f"[{index + 1}] {chunk.source_name}\n{chunk.content}"
            for index, chunk in enumerate(retrieved_chunks)
        )
        if self.settings is not None:
            return context[: self.settings.rag_max_context_chars]
        return context

    def _normalize_content(self, content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)

    def _extract_token_usage(self, response) -> RagTokenUsageBundle | None:
        response_metadata = getattr(response, "response_metadata", {}) or {}
        token_usage = response_metadata.get("token_usage")
        if not token_usage:
            usage_metadata = getattr(response, "usage_metadata", None)
            token_usage = dict(usage_metadata) if usage_metadata else None
        if not token_usage:
            return None

        prompt_tokens = token_usage.get("prompt_tokens", token_usage.get("input_tokens", 0)) or 0
        completion_tokens = token_usage.get("completion_tokens", token_usage.get("output_tokens", 0)) or 0
        total_tokens = token_usage.get("total_tokens", 0) or 0
        if not total_tokens:
            total_tokens = int(prompt_tokens) + int(completion_tokens)

        return RagTokenUsageBundle(
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            total_tokens=int(total_tokens),
        )

    def _normalize_source_identifier(self, value: str) -> str:
        return value.replace("\\", "/").strip().lower()

    def _source_identifiers(self, chunk: RetrievedChunk) -> set[str]:
        values = {
            chunk.document_id,
            chunk.chunk_id,
            chunk.source_name,
            chunk.source_path,
            Path(chunk.source_path).name if chunk.source_path else "",
        }
        return {self._normalize_source_identifier(value) for value in values if value}

    def _average(self, values: list[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    def _percentile(self, values: list[float], percentile_value: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, ceil((percentile_value / 100) * len(ordered)) - 1))
        return round(ordered[index], 3)

    def _build_answer_metrics(
        self,
        *,
        query: str,
        answer: str,
        retrieved_chunks: list[RetrievedChunk],
        expected_answer_contains: list[str],
        reference_answer: str | None,
    ) -> RagAnswerMetricBundle:
        normalized_answer = normalize_search_text(answer)
        query_terms = extract_search_terms(query)
        query_term_coverage = 0.0
        if query_terms:
            matched_query_terms = sum(1 for term in query_terms if term in normalized_answer)
            query_term_coverage = matched_query_terms / len(query_terms)

        expected_term_recall = None
        if expected_answer_contains:
            normalized_expected_terms = [normalize_search_text(item) for item in expected_answer_contains]
            matched_expected_terms = sum(1 for item in normalized_expected_terms if item and item in normalized_answer)
            expected_term_recall = matched_expected_terms / len(normalized_expected_terms)

        groundedness_score, grounded_sentence_ratio, unsupported_statements = self._score_groundedness(
            answer=answer,
            retrieved_chunks=retrieved_chunks,
        )

        reference_similarity = None
        if reference_answer:
            reference_similarity = self._compute_reference_similarity(
                answer=answer,
                reference_answer=reference_answer,
            )

        weighted_values: list[tuple[float, float]] = [
            (groundedness_score, 0.45),
            (grounded_sentence_ratio, 0.2),
            (query_term_coverage, 0.1),
        ]
        if expected_term_recall is not None:
            weighted_values.append((expected_term_recall, 0.15))
        if reference_similarity is not None:
            weighted_values.append((reference_similarity, 0.1))

        weight_sum = sum(weight for _, weight in weighted_values) or 1.0
        overall_answer_score = sum(value * weight for value, weight in weighted_values) / weight_sum
        sentence_count = max(len(self._split_answer_sentences(answer)), 1)

        return RagAnswerMetricBundle(
            answer_present=bool(answer.strip()),
            expected_term_recall=round(expected_term_recall, 6) if expected_term_recall is not None else None,
            query_term_coverage=round(query_term_coverage, 6),
            groundedness_score=round(groundedness_score, 6),
            grounded_sentence_ratio=round(grounded_sentence_ratio, 6),
            reference_similarity=round(reference_similarity, 6) if reference_similarity is not None else None,
            unsupported_statement_count=len(unsupported_statements),
            evaluated_sentence_count=sentence_count,
            overall_answer_score=round(overall_answer_score, 6),
            unsupported_statements=unsupported_statements[:5],
        )

    def _score_groundedness(
        self,
        *,
        answer: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> tuple[float, float, list[str]]:
        sentences = self._split_answer_sentences(answer)
        if not sentences:
            return 0.0, 0.0, []
        if not retrieved_chunks:
            return 0.0, 0.0, sentences[:5]

        support_scores: list[float] = []
        unsupported_statements: list[str] = []

        for sentence in sentences:
            sentence_support = max(
                compute_keyword_score(
                    sentence,
                    content=chunk.content,
                    source_name=chunk.source_name,
                )
                for chunk in retrieved_chunks
            )
            support_scores.append(sentence_support)
            if sentence_support < 0.35:
                unsupported_statements.append(sentence)

        groundedness_score = sum(support_scores) / len(support_scores)
        grounded_sentence_ratio = sum(1 for score in support_scores if score >= 0.35) / len(support_scores)
        return groundedness_score, grounded_sentence_ratio, unsupported_statements

    def _split_answer_sentences(self, answer: str) -> list[str]:
        return [
            sentence.strip()
            for sentence in _SENTENCE_SPLIT_PATTERN.split(answer)
            if sentence and sentence.strip()
        ]

    def _compute_reference_similarity(self, *, answer: str, reference_answer: str) -> float:
        answer_terms = set(extract_search_terms(answer))
        reference_terms = set(extract_search_terms(reference_answer))
        if not answer_terms or not reference_terms:
            return 0.0

        overlap = len(answer_terms & reference_terms)
        precision = overlap / len(answer_terms)
        recall = overlap / len(reference_terms)
        if precision + recall == 0:
            return 0.0
        return (2 * precision * recall) / (precision + recall)

    def _parse_llm_judge_response(self, raw_content: str) -> dict[str, Any]:
        content = raw_content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = _JSON_BLOCK_PATTERN.search(content)
            if not match:
                raise ValueError("LLM judge did not return valid JSON.")
            return json.loads(match.group(0))

    def _resolve_optional_override(
        self,
        override_value: bool | None,
        case_value: bool | None,
        dataset_value: bool | None,
    ) -> bool | None:
        if override_value is not None:
            return override_value
        if case_value is not None:
            return case_value
        return dataset_value
