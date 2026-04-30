from __future__ import annotations

import re
from collections import defaultdict

from app.schemas.chat import RetrievedChunk

_LATIN_TERM_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")
_CJK_TERM_PATTERN = re.compile(r"[\u4e00-\u9fff]+")
_MULTISPACE_PATTERN = re.compile(r"\s+")


def normalize_search_text(text: str) -> str:
    normalized = _MULTISPACE_PATTERN.sub(" ", str(text or "").strip().lower())
    return normalized


def extract_search_terms(text: str) -> list[str]:
    normalized = normalize_search_text(text)
    terms: list[str] = []
    seen: set[str] = set()

    for match in _LATIN_TERM_PATTERN.findall(normalized):
        if len(match) < 2:
            continue
        if match not in seen:
            terms.append(match)
            seen.add(match)

    for sequence in _CJK_TERM_PATTERN.findall(normalized):
        if not sequence:
            continue
        candidates = [sequence]
        if len(sequence) > 1:
            candidates.extend(
                sequence[index : index + 2]
                for index in range(len(sequence) - 1)
            )
        for candidate in candidates:
            if candidate and candidate not in seen:
                terms.append(candidate)
                seen.add(candidate)

    return terms


def compute_keyword_score(query: str, *, content: str, source_name: str = "") -> float:
    normalized_query = normalize_search_text(query)
    query_terms = extract_search_terms(normalized_query)
    if not normalized_query or not query_terms:
        return 0.0

    searchable_text = normalize_search_text(f"{source_name}\n{content}")
    if not searchable_text:
        return 0.0

    weighted_hits = 0.0
    matched_terms = 0
    total_weight = 0.0

    for term in query_terms:
        weight = 1.0 + min(len(term), 8) / 8.0
        total_weight += weight
        hit_count = searchable_text.count(term)
        if hit_count:
            matched_terms += 1
            weighted_hits += weight * min(hit_count, 3)

    if total_weight == 0:
        return 0.0

    coverage = matched_terms / len(query_terms)
    density = min(weighted_hits / total_weight, 1.0)
    phrase_bonus = 1.0 if normalized_query in searchable_text else 0.0
    title_bonus = 1.0 if normalize_search_text(source_name) and any(
        term in normalize_search_text(source_name) for term in query_terms
    ) else 0.0

    score = (0.45 * coverage) + (0.3 * density) + (0.15 * phrase_bonus) + (0.1 * title_bonus)
    return round(min(score, 1.0), 6)


def rerank_chunk_score(query: str, chunk: RetrievedChunk) -> float:
    normalized_query = normalize_search_text(query)
    query_terms = extract_search_terms(normalized_query)
    if not query_terms:
        return float(chunk.score or 0.0)

    normalized_title = normalize_search_text(chunk.source_name)
    normalized_content = normalize_search_text(chunk.content)
    keyword_score = compute_keyword_score(
        normalized_query,
        content=normalized_content,
        source_name=normalized_title,
    )

    matched_terms = sum(1 for term in query_terms if term in normalized_content)
    title_matches = sum(1 for term in query_terms if term in normalized_title)
    coverage = matched_terms / len(query_terms)
    title_bonus = min(title_matches / len(query_terms), 1.0)
    phrase_bonus = 1.0 if normalized_query and normalized_query in normalized_content else 0.0
    base_score = float(chunk.score or 0.0)

    score = (
        (0.35 * base_score)
        + (0.25 * keyword_score)
        + (0.2 * coverage)
        + (0.1 * phrase_bonus)
        + (0.1 * title_bonus)
    )
    return round(min(score, 1.0), 6)


def reciprocal_rank_fuse(
    named_results: list[tuple[str, list[RetrievedChunk]]],
    *,
    rrf_k: int,
) -> list[RetrievedChunk]:
    merged: dict[str, RetrievedChunk] = {}
    fused_scores = defaultdict(float)

    for channel_name, results in named_results:
        for rank, chunk in enumerate(results, start=1):
            chunk_key = chunk.chunk_id or f"{chunk.document_id}:{chunk.chunk_index}"
            if chunk_key not in merged:
                merged[chunk_key] = chunk.model_copy(deep=True)
                merged[chunk_key].metadata = dict(merged[chunk_key].metadata or {})
                merged[chunk_key].metadata["retrieval_channels"] = []

            fused_scores[chunk_key] += 1.0 / (rrf_k + rank)
            merged_chunk = merged[chunk_key]
            merged_chunk.metadata["retrieval_channels"] = sorted(
                {
                    *merged_chunk.metadata.get("retrieval_channels", []),
                    channel_name,
                }
            )
            merged_chunk.metadata[f"{channel_name}_rank"] = rank
            merged_chunk.metadata[f"{channel_name}_score"] = float(chunk.score or 0.0)

    fused = list(merged.values())
    for chunk in fused:
        chunk_key = chunk.chunk_id or f"{chunk.document_id}:{chunk.chunk_index}"
        chunk.score = round(fused_scores[chunk_key], 6)
        chunk.metadata["hybrid_score"] = chunk.score

    fused.sort(
        key=lambda item: (
            float(item.score or 0.0),
            float(item.metadata.get("dense_score", 0.0)),
            float(item.metadata.get("keyword_score", 0.0)),
        ),
        reverse=True,
    )
    return fused
