from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError


class EmbeddingService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._embeddings = None

    def get_embeddings(self) -> OpenAIEmbeddings:
        if self._embeddings is None:
            if not self.settings.openai_api_key:
                raise ServiceUnavailableError(
                    code="OPENAI_API_KEY_MISSING",
                    message="OPENAI_API_KEY is required for embeddings.",
                )

            self._embeddings = OpenAIEmbeddings(
                model=self.settings.openai_embedding_model,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
            )

        return self._embeddings
