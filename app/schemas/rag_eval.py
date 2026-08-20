from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class RagEvaluationCase(BaseModel):
    case_id: str
    query: str = Field(min_length=1, max_length=4000)
    collection_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    use_hybrid_search: bool | None = None
    use_rerank: bool | None = None
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    relevant_document_ids: list[str] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)
    reference_answer: str | None = None
    candidate_answer: str | None = None
    expected_answer_contains: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_relevance_targets(self) -> "RagEvaluationCase":
        if not self.relevant_chunk_ids and not self.relevant_document_ids and not self.expected_sources:
            raise ValueError(
                "Each evaluation case must define relevant_chunk_ids, relevant_document_ids, or expected_sources."
            )
        return self


class RagEvaluationDataset(BaseModel):
    dataset_name: str
    description: str | None = None
    default_collection_id: str | None = None
    default_top_k: int = Field(default=5, ge=1, le=50)
    default_use_hybrid_search: bool | None = None
    default_use_rerank: bool | None = None
    cases: list[RagEvaluationCase] = Field(default_factory=list)


class RagEvaluationDatasetSummary(BaseModel):
    dataset_path: str
    dataset_name: str
    description: str | None = None
    case_count: int
    updated_at: str


class RagRetrievedItem(BaseModel):
    rank: int
    document_id: str
    chunk_id: str
    source_name: str
    source_path: str | None = None
    score: float | None = None
    retrieval_channels: list[str] = Field(default_factory=list)
    page: int | None = None
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagMetricBundle(BaseModel):
    precision_at_k: float
    recall_at_k: float
    hit_rate_at_k: float
    mrr_at_k: float
    average_precision_at_k: float
    ndcg_at_k: float
    relevant_retrieved_count: int
    relevant_total_count: int


class RagAnswerMetricBundle(BaseModel):
    answer_present: bool
    expected_term_recall: float | None = None
    query_term_coverage: float
    groundedness_score: float
    grounded_sentence_ratio: float
    reference_similarity: float | None = None
    unsupported_statement_count: int
    evaluated_sentence_count: int
    overall_answer_score: float
    unsupported_statements: list[str] = Field(default_factory=list)


class RagSourceMetricBundle(BaseModel):
    source_match: float
    source_hit_rate: float
    matched_sources: list[str] = Field(default_factory=list)
    expected_source_count: int


class RagLatencyMetricBundle(BaseModel):
    retrieval_ms: float
    answer_generation_ms: float | None = None
    llm_judge_ms: float | None = None
    total_ms: float


class RagTokenUsageBundle(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class RagLlmJudgeMetricBundle(BaseModel):
    overall_score: float
    groundedness_score: float
    relevance_score: float
    completeness_score: float
    factual_consistency_score: float
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    rationale: str = ""


class RagEvaluationCaseResult(BaseModel):
    case_id: str
    query: str
    collection_id: str
    top_k: int
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    relevant_document_ids: list[str] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)
    retrieved: list[RagRetrievedItem] = Field(default_factory=list)
    primary_label_level: str
    primary_metrics: RagMetricBundle | None = None
    chunk_metrics: RagMetricBundle | None = None
    document_metrics: RagMetricBundle | None = None
    source_metrics: RagSourceMetricBundle | None = None
    answer_source: str | None = None
    answer: str | None = None
    answer_metrics: RagAnswerMetricBundle | None = None
    llm_judge_metrics: RagLlmJudgeMetricBundle | None = None
    latency_metrics: RagLatencyMetricBundle | None = None
    token_usage: RagTokenUsageBundle | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def upgrade_legacy_source_only_metrics(self) -> "RagEvaluationCaseResult":
        if self.relevant_chunk_ids or self.relevant_document_ids:
            return self
        if self.expected_sources:
            self.primary_label_level = "source-only"
        else:
            self.primary_label_level = "unavailable"
        self.primary_metrics = None
        return self


class RagMetricSummary(BaseModel):
    case_count: int
    precision_at_k: float
    recall_at_k: float
    hit_rate_at_k: float
    mrr_at_k: float
    average_precision_at_k: float
    ndcg_at_k: float


class RagAnswerMetricSummary(BaseModel):
    case_count: int
    overall_answer_score: float
    expected_term_recall: float | None = None
    query_term_coverage: float
    groundedness_score: float
    grounded_sentence_ratio: float
    reference_similarity: float | None = None
    unsupported_statement_count: float


class RagSourceMetricSummary(BaseModel):
    case_count: int
    source_match: float
    source_hit_rate: float


class RagLatencyMetricSummary(BaseModel):
    case_count: int
    avg_retrieval_ms: float
    p50_retrieval_ms: float
    p95_retrieval_ms: float
    max_retrieval_ms: float
    avg_answer_generation_ms: float | None = None
    p50_answer_generation_ms: float | None = None
    p95_answer_generation_ms: float | None = None
    max_answer_generation_ms: float | None = None
    avg_llm_judge_ms: float | None = None
    p50_llm_judge_ms: float | None = None
    p95_llm_judge_ms: float | None = None
    max_llm_judge_ms: float | None = None
    avg_total_ms: float
    p50_total_ms: float
    p95_total_ms: float
    max_total_ms: float


class RagTokenUsageSummary(BaseModel):
    case_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    avg_prompt_tokens: float
    avg_completion_tokens: float
    avg_total_tokens: float


class RagLlmJudgeMetricSummary(BaseModel):
    case_count: int
    overall_score: float
    groundedness_score: float
    relevance_score: float
    completeness_score: float
    factual_consistency_score: float


class RagEvaluationSummary(BaseModel):
    dataset_name: str
    total_cases: int
    top_k: int
    primary_label_level: str = "unavailable"
    primary_metrics: RagMetricSummary | None = None
    chunk_metrics: RagMetricSummary | None = None
    document_metrics: RagMetricSummary | None = None
    source_metrics: RagSourceMetricSummary | None = None
    answer_metrics: RagAnswerMetricSummary | None = None
    llm_judge_metrics: RagLlmJudgeMetricSummary | None = None
    latency_metrics: RagLatencyMetricSummary | None = None
    token_usage: RagTokenUsageSummary | None = None

    @model_validator(mode="after")
    def preserve_legacy_measurable_summary(self) -> "RagEvaluationSummary":
        if self.primary_metrics is not None and "primary_label_level" not in self.model_fields_set:
            self.primary_label_level = "legacy"
        return self


class RagEvaluationReport(BaseModel):
    dataset_name: str
    description: str | None = None
    evaluated_at: str
    summary: RagEvaluationSummary
    case_results: list[RagEvaluationCaseResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def upgrade_legacy_primary_summary(self) -> "RagEvaluationReport":
        if not self.case_results:
            return self
        label_levels = {item.primary_label_level for item in self.case_results}
        if len(label_levels) == 1:
            self.summary.primary_label_level = next(iter(label_levels))
        else:
            self.summary.primary_label_level = "mixed"
        if not any(item.primary_metrics is not None for item in self.case_results):
            self.summary.primary_metrics = None
        return self


class RagEvaluationRunRequest(BaseModel):
    dataset_path: str = Field(min_length=1)
    collection_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    use_hybrid_search: bool | None = None
    use_rerank: bool | None = None
    answer_mode: str = "auto"
    llm_judge_mode: str = "off"
    persist: bool = True


class RagEvaluationStoredReport(BaseModel):
    report_id: str
    report_filename: str
    dataset_path: str
    created_at: str
    answer_mode: str
    llm_judge_mode: str
    report: RagEvaluationReport


class RagEvaluationTaskStatus(BaseModel):
    task_id: str
    status: str
    completed_cases: int = 0
    total_cases: int = 0
    report_id: str | None = None
    stored_report: RagEvaluationStoredReport | None = None
    error: str | None = None


class RagEvaluationStoredReportSummary(BaseModel):
    report_id: str
    report_filename: str
    dataset_path: str
    created_at: str
    answer_mode: str
    llm_judge_mode: str
    dataset_name: str
    evaluated_at: str
    summary: RagEvaluationSummary
