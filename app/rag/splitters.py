from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from app.schemas.common import DocumentChunk


def build_text_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def split_documents(
    documents: list[Document],
    *,
    collection_id: str,
    document_id: str,
    source_name: str,
    source_path: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[DocumentChunk]:
    splitter = build_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(documents)

    records: list[DocumentChunk] = []
    for index, chunk in enumerate(chunks):
        records.append(
            DocumentChunk(
                document_id=document_id,
                collection_id=collection_id,
                chunk_id=f"{document_id}-{index}",
                chunk_index=index,
                chunk_text=chunk.page_content,
                source_name=source_name,
                source_path=source_path,
                metadata=chunk.metadata or {},
            )
        )
    return records
