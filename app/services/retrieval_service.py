from __future__ import annotations

from app.core.config import Settings
from app.rag.retrieval import reciprocal_rank_fuse, rerank_chunk_score
from app.schemas.chat import RetrievedChunk
from app.services.vector_store_service import VectorStoreService


class RetrievalService:
    def __init__(self, vector_store_service: VectorStoreService, settings: Settings):
        self.vector_store_service = vector_store_service
        self.settings = settings

    def _dense_candidate_limit(self, top_k: int) -> int:
        return max(top_k, top_k * max(self.settings.rag_hybrid_candidate_multiplier, 1))

    def _keyword_candidate_limit(self, top_k: int) -> int:
        return max(top_k, top_k * max(self.settings.rag_hybrid_candidate_multiplier, 1))

    def _use_hybrid_search(self, use_hybrid_search: bool | None) -> bool:
        if use_hybrid_search is None:
            return self.settings.rag_use_hybrid_search
        return use_hybrid_search

    def _use_rerank(self, use_rerank: bool | None) -> bool:
        if use_rerank is None:
            return self.settings.rag_use_rerank
        return use_rerank

    def _dense_search(
        self,
        *,
        query: str,
        collection_id: str,
        top_k: int,
        score_threshold: float,
    ) -> list[RetrievedChunk]:
        return self.vector_store_service.similarity_search(
            collection_id=collection_id,
            query=query,
            top_k=self._dense_candidate_limit(top_k),
            score_threshold=score_threshold,
        )

    def _keyword_search(
        self,
        *,
        query: str,
        collection_id: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        return self.vector_store_service.keyword_search(
            collection_id=collection_id,
            query=query,
            top_k=self._keyword_candidate_limit(top_k),
            score_threshold=self.settings.rag_keyword_score_threshold,
        )

    def _hybrid_search(
        self,
        *,
        query: str,
        collection_id: str,
        top_k: int,
        score_threshold: float,
    ) -> list[RetrievedChunk]:
        dense_results = self._dense_search(
            query=query,
            collection_id=collection_id,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        keyword_results = self._keyword_search(
            query=query,
            collection_id=collection_id,
            top_k=top_k,
        )
        if not keyword_results:
            return dense_results[:top_k]
        if not dense_results:
            return keyword_results[:top_k]
        return reciprocal_rank_fuse(
            [
                ("dense", dense_results),
                ("keyword", keyword_results),
            ],
            rrf_k=self.settings.rag_hybrid_rrf_k,
        )[: self._dense_candidate_limit(top_k)]

    def _rerank(self, *, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        reranked = [chunk.model_copy(deep=True) for chunk in chunks]
        for chunk in reranked:
            chunk.metadata = dict(chunk.metadata or {})
            chunk.metadata["pre_rerank_score"] = float(chunk.score or 0.0)
            chunk.score = rerank_chunk_score(query, chunk)
            chunk.metadata["rerank_score"] = float(chunk.score or 0.0)

        reranked.sort(
            key=lambda item: (
                float(item.score or 0.0),
                float(item.metadata.get("pre_rerank_score", 0.0)),
            ),
            reverse=True,
        )
        return reranked[:top_k]

    def retrieve(
        self,
        *,
        query: str,
        collection_id: str,
        top_k: int | None = None,
        score_threshold: float | None = None,
        use_hybrid_search: bool | None = None,
        use_rerank: bool | None = None,
    ) -> list[RetrievedChunk]:
        effective_top_k = top_k or self.settings.rag_top_k
        effective_score_threshold = (
            self.settings.rag_score_threshold
            if score_threshold is None
            else score_threshold
        )

        if self._use_hybrid_search(use_hybrid_search):
            candidates = self._hybrid_search(
                query=query,
                collection_id=collection_id,
                top_k=effective_top_k,
                score_threshold=effective_score_threshold,
            )
        else:
            candidates = self._dense_search(
                query=query,
                collection_id=collection_id,
                top_k=effective_top_k,
                score_threshold=effective_score_threshold,
            )

        if self._use_rerank(use_rerank):
            return self._rerank(
                query=query,
                chunks=candidates,
                top_k=effective_top_k,
            )

        return candidates[:effective_top_k]
