from __future__ import annotations

import argparse
import os

from app.core.config import get_settings
from app.db.session import get_session_factory, init_db
from app.repositories.document_repository import DocumentRepository
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import IngestionService
from app.services.vector_store_service import VectorStoreService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild vector indexes for all or part of the document corpus.",
    )
    parser.add_argument(
        "--backend",
        choices=["faiss", "milvus"],
        help="Target vector backend. Overrides VECTOR_BACKEND for this run.",
    )
    parser.add_argument("--collection-id", help="Only rebuild one collection.")
    parser.add_argument("--document-id", help="Only rebuild one document.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.backend:
        os.environ["VECTOR_BACKEND"] = args.backend
        get_settings.cache_clear()

    settings = get_settings()
    init_db()

    document_repository = DocumentRepository(get_session_factory())
    vector_store_service = VectorStoreService(
        settings=settings,
        embedding_service=EmbeddingService(settings),
    )
    ingestion_service = IngestionService(
        settings=settings,
        document_repository=document_repository,
        vector_store_service=vector_store_service,
    )

    documents = document_repository.list_documents(collection_id=args.collection_id)
    if args.document_id:
        documents = [item for item in documents if item["id"] == args.document_id]

    rebuilt_count = 0
    for document in documents:
        if document["status"] == "deleted":
            continue
        vector_store_service.delete_by_document_id(
            collection_id=document["collection_id"],
            document_id=document["id"],
        )
        document_repository.touch(
            document["id"],
            status="uploaded",
            chunk_count=0,
            error_message=None,
        )
        result = ingestion_service.ingest_document(document["id"])
        rebuilt_count += 1
        print(
            f"Rebuilt document {result['id']} into backend "
            f"'{settings.vector_backend}' with status={result['status']} "
            f"chunk_count={result['chunk_count']}"
        )

    print(f"Rebuild finished. Documents processed: {rebuilt_count}")


if __name__ == "__main__":
    main()
