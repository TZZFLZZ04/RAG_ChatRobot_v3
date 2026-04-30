from types import SimpleNamespace

from app.schemas.chat import RetrievedChunk
from app.services.retrieval_service import RetrievalService


class FakeVectorStoreService:
    def __init__(self, *, dense_results=None, keyword_results=None) -> None:
        self.dense_results = dense_results or []
        self.keyword_results = keyword_results or []
        self.calls: list[dict] = []

    def similarity_search(self, *, collection_id: str, query: str, top_k: int, score_threshold: float = 0.0):
        self.calls.append(
            {
                "method": "dense",
                "collection_id": collection_id,
                "query": query,
                "top_k": top_k,
                "score_threshold": score_threshold,
            }
        )
        return list(self.dense_results)

    def keyword_search(self, *, collection_id: str, query: str, top_k: int, score_threshold: float = 0.0):
        self.calls.append(
            {
                "method": "keyword",
                "collection_id": collection_id,
                "query": query,
                "top_k": top_k,
                "score_threshold": score_threshold,
            }
        )
        return list(self.keyword_results)


def make_chunk(
    chunk_id: str,
    *,
    score: float,
    content: str,
    source_name: str = "employee-handbook.pdf",
) -> RetrievedChunk:
    return RetrievedChunk(
        document_id="document-1",
        chunk_id=chunk_id,
        source_name=source_name,
        source_path=f"raw/{source_name}",
        chunk_index=0,
        score=score,
        content=content,
        metadata={},
    )


def build_service(vector_store_service: FakeVectorStoreService, **settings_overrides) -> RetrievalService:
    settings_payload = {
        "rag_top_k": 3,
        "rag_score_threshold": 0.0,
        "rag_use_hybrid_search": True,
        "rag_use_rerank": False,
        "rag_hybrid_candidate_multiplier": 3,
        "rag_hybrid_rrf_k": 60,
        "rag_keyword_score_threshold": 0.2,
    }
    settings_payload.update(settings_overrides)
    settings = SimpleNamespace(**settings_payload)
    return RetrievalService(vector_store_service, settings)


def test_hybrid_search_fuses_dense_and_keyword_candidates() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[
            make_chunk("dense-1", score=0.92, content="远程办公审批规则"),
            make_chunk("shared", score=0.88, content="员工请假制度与审批流"),
        ],
        keyword_results=[
            make_chunk("shared", score=0.97, content="员工请假制度与审批流"),
            make_chunk("keyword-1", score=0.85, content="请假制度包含年假与病假"),
        ],
    )
    service = build_service(vector_store)

    results = service.retrieve(
        query="员工请假制度",
        collection_id="collection-1",
        top_k=2,
        use_hybrid_search=True,
        use_rerank=False,
    )

    assert [chunk.chunk_id for chunk in results] == ["shared", "dense-1"]
    assert vector_store.calls[0]["method"] == "dense"
    assert vector_store.calls[1]["method"] == "keyword"
    assert results[0].metadata["retrieval_channels"] == ["dense", "keyword"]


def test_rerank_promotes_exact_match_candidate() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[
            make_chunk("dense-1", score=0.98, content="这是泛化的制度说明"),
            make_chunk("dense-2", score=0.76, content="员工请假制度包含年假、病假和调休"),
        ],
        keyword_results=[
            make_chunk("dense-2", score=0.95, content="员工请假制度包含年假、病假和调休"),
        ],
    )
    service = build_service(vector_store, rag_use_rerank=True)

    results = service.retrieve(
        query="员工请假制度",
        collection_id="collection-1",
        top_k=1,
        use_hybrid_search=True,
        use_rerank=True,
    )

    assert [chunk.chunk_id for chunk in results] == ["dense-2"]
    assert results[0].metadata["rerank_score"] >= results[0].metadata["pre_rerank_score"]


def test_dense_only_mode_skips_keyword_search() -> None:
    vector_store = FakeVectorStoreService(
        dense_results=[make_chunk("dense-1", score=0.9, content="handbook content")]
    )
    service = build_service(vector_store, rag_use_hybrid_search=False)

    results = service.retrieve(
        query="handbook",
        collection_id="collection-1",
        top_k=1,
        use_hybrid_search=False,
    )

    assert [chunk.chunk_id for chunk in results] == ["dense-1"]
    assert [call["method"] for call in vector_store.calls] == ["dense"]
