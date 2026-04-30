from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ChatRobot Enterprise RAG"
    app_env: str = "dev"
    app_debug: bool = True
    api_prefix: str = "/api/v1"
    observability_log_json: bool = True
    observability_metrics_enabled: bool = True
    observability_tracing_enabled: bool = False
    observability_service_name: str | None = None
    observability_otlp_endpoint: str = "http://localhost:4318/v1/traces"

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    jwt_secret_key: str = "replace-this-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expires_minutes: int = 60 * 24

    vector_backend: str = "faiss"
    milvus_uri: str | None = None
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_user: str | None = None
    milvus_password: str | None = None
    milvus_token: str | None = None
    milvus_collection: str = "chatrobot_documents"
    milvus_index_type: str = "AUTOINDEX"
    milvus_metric_type: str = "COSINE"
    milvus_consistency_level: str = "Strong"
    milvus_text_max_length: int = 65535
    milvus_path_max_length: int = 2048
    milvus_source_name_max_length: int = 512
    database_url: str | None = None
    db_auto_init: bool = True
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "chatrobot"
    postgres_password: str = "chatrobot"
    postgres_db: str = "chatrobot"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_task_always_eager: bool = False
    celery_task_ignore_result: bool = False
    celery_ingestion_queue: str = "document_ingestion"

    data_dir: Path = Path("data")
    raw_data_dir: Path = Path("data/raw")
    processed_data_dir: Path = Path("data/processed")
    faiss_index_dir: Path = Path("data/faiss_indexes")

    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 80
    rag_top_k: int = 5
    rag_score_threshold: float = 0.0
    rag_use_hybrid_search: bool = True
    rag_use_rerank: bool = True
    rag_hybrid_candidate_multiplier: int = 3
    rag_hybrid_rrf_k: int = 60
    rag_keyword_score_threshold: float = 0.2
    rag_query_rewrite_enabled: bool = True
    rag_query_rewrite_history_messages: int = 6
    rag_query_rewrite_max_chars: int = 300
    rag_max_context_chars: int = 8000

    upload_max_bytes: int = 10 * 1024 * 1024
    allowed_upload_extensions: str = Field(default="pdf,docx,doc,txt")
    default_collection_name: str = "default"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def allowed_extensions(self) -> set[str]:
        return {
            extension.strip().lower()
            for extension in self.allowed_upload_extensions.split(",")
            if extension.strip()
        }

    def ensure_directories(self) -> None:
        for directory in (
            self.data_dir,
            self.raw_data_dir,
            self.processed_data_dir,
            self.faiss_index_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            "postgresql+psycopg2://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def effective_milvus_connection_args(self) -> dict:
        if self.milvus_uri:
            args = {"uri": self.milvus_uri}
        else:
            args = {"host": self.milvus_host, "port": self.milvus_port}

        if self.milvus_token:
            args["token"] = self.milvus_token
        elif self.milvus_user and self.milvus_password:
            args["user"] = self.milvus_user
            args["password"] = self.milvus_password
        return args


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
