from __future__ import annotations

from langchain_core.documents import Document

from app.rag.splitters import build_text_splitter, split_documents


def test_recursive_splitter_prefers_chinese_sentence_boundaries() -> None:
    text = "第一句介绍部署流程。第二句说明回滚步骤！第三句记录验收结果？"

    chunks = build_text_splitter(chunk_size=18, chunk_overlap=0).split_text(text)

    assert chunks == [
        "第一句介绍部署流程。",
        "第二句说明回滚步骤！",
        "第三句记录验收结果？",
    ]


def test_recursive_splitter_prefers_english_sentence_boundaries() -> None:
    text = (
        "First sentence explains deployment. "
        "Second sentence covers rollback! "
        "Third sentence records verification?"
    )

    chunks = build_text_splitter(chunk_size=40, chunk_overlap=0).split_text(text)

    assert chunks == [
        "First sentence explains deployment.",
        "Second sentence covers rollback!",
        "Third sentence records verification?",
    ]


def test_recursive_splitter_falls_back_for_unbroken_text() -> None:
    text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    chunks = build_text_splitter(chunk_size=10, chunk_overlap=0).split_text(text)

    assert "".join(chunks) == text
    assert all(len(chunk) <= 10 for chunk in chunks)


def test_split_documents_preserves_metadata_and_assigns_deterministic_ids() -> None:
    documents = [
        Document(page_content="ABCDEFGHIJ", metadata={"page": 1, "section": "intro"}),
        Document(page_content="KLMNOP", metadata={"page": 2}),
    ]
    arguments = {
        "collection_id": "collection-1",
        "document_id": "document-1",
        "source_name": "handbook.txt",
        "source_path": "raw/handbook.txt",
        "chunk_size": 5,
        "chunk_overlap": 0,
    }

    first = split_documents(documents, **arguments)
    second = split_documents(documents, **arguments)

    assert [chunk.chunk_id for chunk in first] == [
        "document-1-0",
        "document-1-1",
        "document-1-2",
        "document-1-3",
    ]
    assert [chunk.chunk_index for chunk in first] == [0, 1, 2, 3]
    assert [chunk.metadata for chunk in first] == [
        {"page": 1, "section": "intro"},
        {"page": 1, "section": "intro"},
        {"page": 2},
        {"page": 2},
    ]
    assert first == second
