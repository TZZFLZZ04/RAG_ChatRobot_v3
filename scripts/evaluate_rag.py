from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import datetime, timezone
import json
from math import ceil, log2
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api import deps
from app.rag.prompts import build_system_prompt
from app.schemas.chat import RetrievedChunk


DEFAULT_DATASET_PATH = PROJECT_ROOT / "eval" / "datasets" / "rag_eval.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a lightweight offline RAG evaluation from JSONL. "
            "No LangSmith or Langfuse dependency is required."
        )
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="Path to the JSONL evaluation dataset.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the JSON report.",
    )
    parser.add_argument(
        "--collection-id",
        help="Optional collection id override applied to all cases.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        help="Optional top-k override applied to all cases.",
    )
    parser.add_argument(
        "--use-hybrid-search",
        type=parse_optional_bool,
        choices=[True, False],
        help="Optional override for use_hybrid_search: true or false.",
    )
    parser.add_argument(
        "--use-rerank",
        type=parse_optional_bool,
        choices=[True, False],
        help="Optional override for use_rerank: true or false.",
    )
    parser.add_argument(
        "--answer-mode",
        choices=["off", "generate"],
        default="off",
        help="Use 'generate' to call the chat model and record answer latency/token usage.",
    )
    parser.add_argument(
        "--max-context-chars",
        type=int,
        help="Optional context character limit for generated answers.",
    )
    return parser


def ensure_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def first_list(payload: dict[str, Any], keys: Iterable[str]) -> list[str]:
    for key in keys:
        values = ensure_string_list(payload.get(key))
        if values:
            return values
    return []


def load_jsonl_dataset(dataset_path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Line {line_number} must be a JSON object.")
            payload.setdefault("case_id", f"case-{line_number}")
            cases.append(payload)
    if not cases:
        raise ValueError(f"No evaluation cases found in {dataset_path}.")
    return cases


def ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def compute_rank_metrics(
    *,
    retrieved_ids: list[str],
    relevant_ids: list[str],
    top_k: int,
) -> dict[str, Any] | None:
    relevant_set = set(relevant_ids)
    if not relevant_set:
        return None

    ranked_ids = retrieved_ids[:top_k]
    binary_relevance = [1 if item_id in relevant_set else 0 for item_id in ranked_ids]
    hit_count = sum(binary_relevance)

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
    average_precision = precision_sum / len(relevant_set)

    dcg = sum(is_relevant / log2(index + 1) for index, is_relevant in enumerate(binary_relevance, start=1))
    ideal_relevance = [1] * min(len(relevant_set), len(ranked_ids))
    idcg = sum(is_relevant / log2(index + 1) for index, is_relevant in enumerate(ideal_relevance, start=1))
    ndcg = dcg / idcg if idcg else 0.0

    return {
        "precision_at_k": round(hit_count / len(ranked_ids), 6) if ranked_ids else 0.0,
        "recall_at_k": round(hit_count / len(relevant_set), 6),
        "mrr_at_k": round(reciprocal_rank, 6),
        "hit_rate_at_k": 1.0 if hit_count else 0.0,
        "average_precision_at_k": round(average_precision, 6),
        "ndcg_at_k": round(ndcg, 6),
        "relevant_retrieved_count": hit_count,
        "relevant_total_count": len(relevant_set),
    }


def normalize_source_value(value: str) -> str:
    return value.replace("\\", "/").strip().lower()


def source_identifiers(chunk: RetrievedChunk) -> set[str]:
    values = {
        chunk.document_id,
        chunk.chunk_id,
        chunk.source_name,
        chunk.source_path,
        Path(chunk.source_path).name if chunk.source_path else "",
    }
    return {normalize_source_value(value) for value in values if value}


def compute_source_match(
    *,
    retrieved_chunks: list[RetrievedChunk],
    expected_sources: list[str],
) -> dict[str, Any] | None:
    if not expected_sources:
        return None

    retrieved_identifiers: set[str] = set()
    for chunk in retrieved_chunks:
        retrieved_identifiers.update(source_identifiers(chunk))

    matched_sources: list[str] = []
    for expected_source in expected_sources:
        normalized_expected = normalize_source_value(expected_source)
        if any(
            normalized_expected == candidate
            or normalized_expected in candidate
            or candidate in normalized_expected
            for candidate in retrieved_identifiers
        ):
            matched_sources.append(expected_source)

    return {
        "source_match": round(len(matched_sources) / len(expected_sources), 6),
        "source_hit_rate": 1.0 if matched_sources else 0.0,
        "matched_sources": matched_sources,
        "expected_source_count": len(expected_sources),
    }


def normalize_content(content: Any) -> str:
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


def extract_token_usage(response: Any) -> dict[str, Any] | None:
    response_metadata = getattr(response, "response_metadata", {}) or {}
    token_usage = response_metadata.get("token_usage")
    if token_usage:
        return dict(token_usage)
    usage_metadata = getattr(response, "usage_metadata", None)
    if usage_metadata:
        return dict(usage_metadata)
    return None


def normalize_token_usage(token_usage: dict[str, Any] | None) -> dict[str, int] | None:
    if not token_usage:
        return None

    prompt_tokens = token_usage.get("prompt_tokens", token_usage.get("input_tokens", 0)) or 0
    completion_tokens = token_usage.get("completion_tokens", token_usage.get("output_tokens", 0)) or 0
    total_tokens = token_usage.get("total_tokens", 0) or 0
    if not total_tokens:
        total_tokens = int(prompt_tokens) + int(completion_tokens)

    return {
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_tokens": int(total_tokens),
    }


def build_context(retrieved_chunks: list[RetrievedChunk], max_context_chars: int) -> str:
    context = "\n\n".join(
        f"[{index}] {chunk.source_name}\n{chunk.content}"
        for index, chunk in enumerate(retrieved_chunks, start=1)
    )
    return context[:max_context_chars]


def build_llm(settings: Any) -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required when --answer-mode generate is used.")
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
        timeout=60,
        max_retries=2,
    )


def generate_answer(
    *,
    llm: ChatOpenAI,
    settings: Any,
    query: str,
    retrieved_chunks: list[RetrievedChunk],
    max_context_chars: int | None,
) -> tuple[str, dict[str, int] | None]:
    context_limit = max_context_chars or settings.rag_max_context_chars
    response = llm.invoke(
        [
            SystemMessage(content=build_system_prompt(build_context(retrieved_chunks, context_limit))),
            HumanMessage(content=query),
        ]
    )
    return normalize_content(response.content).strip(), normalize_token_usage(extract_token_usage(response))


def evaluate_case(
    *,
    payload: dict[str, Any],
    retrieval_service: Any,
    settings: Any,
    llm: ChatOpenAI | None,
    collection_id_override: str | None,
    top_k_override: int | None,
    use_hybrid_search_override: bool | None,
    use_rerank_override: bool | None,
    answer_mode: str,
    max_context_chars: int | None,
) -> dict[str, Any]:
    case_id = str(payload["case_id"])
    query = str(payload.get("query", "")).strip()
    if not query:
        raise ValueError(f"Case '{case_id}' is missing query.")

    collection_id = collection_id_override or payload.get("collection_id")
    if not collection_id:
        raise ValueError(f"Case '{case_id}' is missing collection_id.")

    top_k = top_k_override or int(payload.get("top_k") or settings.rag_top_k)
    use_hybrid_search = (
        use_hybrid_search_override
        if use_hybrid_search_override is not None
        else payload.get("use_hybrid_search")
    )
    use_rerank = use_rerank_override if use_rerank_override is not None else payload.get("use_rerank")

    retrieval_start = perf_counter()
    retrieved_chunks = retrieval_service.retrieve(
        query=query,
        collection_id=str(collection_id),
        top_k=top_k,
        use_hybrid_search=use_hybrid_search,
        use_rerank=use_rerank,
    )
    retrieval_latency_ms = (perf_counter() - retrieval_start) * 1000

    relevant_chunk_ids = first_list(payload, ["relevant_chunk_ids", "expected_chunk_ids"])
    relevant_document_ids = first_list(payload, ["relevant_document_ids", "expected_document_ids"])
    expected_sources = first_list(payload, ["expected_sources", "expected_source_names", "source_names"])

    chunk_metrics = compute_rank_metrics(
        retrieved_ids=[chunk.chunk_id for chunk in retrieved_chunks],
        relevant_ids=relevant_chunk_ids,
        top_k=top_k,
    )
    document_metrics = compute_rank_metrics(
        retrieved_ids=ordered_unique(chunk.document_id for chunk in retrieved_chunks),
        relevant_ids=relevant_document_ids,
        top_k=top_k,
    )
    primary_label_level = "chunk" if chunk_metrics is not None else "document"
    primary_metrics = chunk_metrics or document_metrics
    source_match = compute_source_match(
        retrieved_chunks=retrieved_chunks[:top_k],
        expected_sources=expected_sources,
    )

    answer = None
    token_usage = None
    generation_latency_ms = None
    if answer_mode == "generate":
        if llm is None:
            raise RuntimeError("LLM was not initialized for answer generation.")
        generation_start = perf_counter()
        answer, token_usage = generate_answer(
            llm=llm,
            settings=settings,
            query=query,
            retrieved_chunks=retrieved_chunks,
            max_context_chars=max_context_chars,
        )
        generation_latency_ms = (perf_counter() - generation_start) * 1000

    total_latency_ms = retrieval_latency_ms + (generation_latency_ms or 0.0)

    return {
        "case_id": case_id,
        "query": query,
        "collection_id": str(collection_id),
        "top_k": top_k,
        "primary_label_level": primary_label_level if primary_metrics is not None else None,
        "primary_metrics": primary_metrics,
        "chunk_metrics": chunk_metrics,
        "document_metrics": document_metrics,
        "source_match": source_match,
        "latency_ms": {
            "retrieval": round(retrieval_latency_ms, 3),
            "generation": round(generation_latency_ms, 3) if generation_latency_ms is not None else None,
            "total": round(total_latency_ms, 3),
        },
        "token_usage": token_usage,
        "answer": answer,
        "retrieved": [
            {
                "rank": index,
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "source_name": chunk.source_name,
                "source_path": chunk.source_path,
                "chunk_index": chunk.chunk_index,
                "score": chunk.score,
            }
            for index, chunk in enumerate(retrieved_chunks[:top_k], start=1)
        ],
        "expected": {
            "relevant_chunk_ids": relevant_chunk_ids,
            "relevant_document_ids": relevant_document_ids,
            "sources": expected_sources,
        },
        "metadata": payload.get("metadata", {}),
    }


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil((percentile_value / 100) * len(ordered)) - 1))
    return round(ordered[index], 3)


def summarize_metric_bundle(case_results: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    bundles = [item[key] for item in case_results if item.get(key) is not None]
    if not bundles:
        return None
    return {
        "case_count": len(bundles),
        "precision_at_k": average([item["precision_at_k"] for item in bundles]),
        "recall_at_k": average([item["recall_at_k"] for item in bundles]),
        "mrr_at_k": average([item["mrr_at_k"] for item in bundles]),
        "hit_rate_at_k": average([item["hit_rate_at_k"] for item in bundles]),
        "average_precision_at_k": average([item["average_precision_at_k"] for item in bundles]),
        "ndcg_at_k": average([item["ndcg_at_k"] for item in bundles]),
    }


def summarize_source_match(case_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    bundles = [item["source_match"] for item in case_results if item.get("source_match") is not None]
    if not bundles:
        return None
    return {
        "case_count": len(bundles),
        "source_match": average([item["source_match"] for item in bundles]),
        "source_hit_rate": average([item["source_hit_rate"] for item in bundles]),
    }


def summarize_latency(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("retrieval", "generation", "total"):
        values = [
            item["latency_ms"][key]
            for item in case_results
            if item.get("latency_ms", {}).get(key) is not None
        ]
        summary[key] = {
            "case_count": len(values),
            "avg_ms": average(values),
            "p50_ms": percentile(values, 50),
            "p95_ms": percentile(values, 95),
            "max_ms": round(max(values), 3) if values else None,
        }
    return summary


def summarize_token_usage(case_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    usages = [item["token_usage"] for item in case_results if item.get("token_usage") is not None]
    if not usages:
        return None
    totals = {
        "prompt_tokens": sum(item.get("prompt_tokens", 0) for item in usages),
        "completion_tokens": sum(item.get("completion_tokens", 0) for item in usages),
        "total_tokens": sum(item.get("total_tokens", 0) for item in usages),
    }
    return {
        "case_count": len(usages),
        "total": totals,
        "average_per_case": {
            key: round(value / len(usages), 3)
            for key, value in totals.items()
        },
    }


def build_summary(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_cases": len(case_results),
        "primary_metrics": summarize_metric_bundle(case_results, "primary_metrics"),
        "chunk_metrics": summarize_metric_bundle(case_results, "chunk_metrics"),
        "document_metrics": summarize_metric_bundle(case_results, "document_metrics"),
        "source_match": summarize_source_match(case_results),
        "latency": summarize_latency(case_results),
        "token_usage": summarize_token_usage(case_results),
    }


def main() -> None:
    args = build_argument_parser().parse_args()
    dataset_path = Path(args.dataset)
    output_path = Path(args.output) if args.output else None

    settings = deps.get_settings()
    retrieval_service = deps.get_retrieval_service()
    llm = build_llm(settings) if args.answer_mode == "generate" else None
    cases = load_jsonl_dataset(dataset_path)

    case_results = [
        evaluate_case(
            payload=payload,
            retrieval_service=retrieval_service,
            settings=settings,
            llm=llm,
            collection_id_override=args.collection_id,
            top_k_override=args.top_k,
            use_hybrid_search_override=args.use_hybrid_search,
            use_rerank_override=args.use_rerank,
            answer_mode=args.answer_mode,
            max_context_chars=args.max_context_chars,
        )
        for payload in cases
    ]
    report = {
        "dataset_path": str(dataset_path),
        "evaluated_at": utc_now(),
        "answer_mode": args.answer_mode,
        "summary": build_summary(case_results),
        "case_results": case_results,
    }

    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_json, encoding="utf-8")
    print(report_json)


if __name__ == "__main__":
    main()
