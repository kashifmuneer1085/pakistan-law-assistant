"""
src/utils/config.py
Load and validate the YAML config. Provides a singleton Settings object.
"""
from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator

load_dotenv()

# ── Pydantic models for config sections ────────────────────────────────────

class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: int = 1024
    local_model_path: str | None = None

class EmbeddingConfig(BaseModel):
    model: str = "intfloat/multilingual-e5-large"
    device: str = "cpu"
    batch_size: int = 32

class VectorDBConfig(BaseModel):
    type: str = "faiss"
    index_path: str = "./data/processed/embeddings/faiss_index"
    chroma_path: str = "./data/processed/embeddings/chroma_db"

class ChunkingConfig(BaseModel):
    strategy: str = "recursive_legal"
    chunk_size: int = 512
    chunk_overlap: int = 64
    separators: list[str] = ["\n## ", "\nSection ", "\nArticle ", "\n\n", "\n", " "]

class RetrievalConfig(BaseModel):
    top_k: int = 6
    rerank_top_k: int = 3
    hybrid_alpha: float = 0.7
    bm25_index_path: str = "./data/processed/embeddings/bm25_index.pkl"
    score_threshold: float = 0.35

class DataSourcesConfig(BaseModel):
    pdf_dir: str = "./data/raw/pdfs"
    scraped_dir: str = "./data/raw/scraped"
    chunks_dir: str = "./data/processed/chunks"

class SafetyConfig(BaseModel):
    require_sources: bool = True
    min_sources: int = 1
    disclaimer: str = (
        "This is general legal information, not legal advice. "
        "Consult a qualified lawyer for your specific situation."
    )
    out_of_scope_response: str = (
        "I could not find relevant information in Pakistani legal documents "
        "to answer this question reliably."
    )

class Settings(BaseModel):
    llm: LLMConfig = LLMConfig()
    embeddings: EmbeddingConfig = EmbeddingConfig()
    vector_db: VectorDBConfig = VectorDBConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    data_sources: DataSourcesConfig = DataSourcesConfig()
    safety: SafetyConfig = SafetyConfig()

    # Inject API key from environment at runtime
    @property
    def openai_api_key(self) -> str:
        key = os.getenv("OPENAI_API_KEY", "")
        if not key and self.llm.provider == "openai":
            raise EnvironmentError("OPENAI_API_KEY not set in environment.")
        return key


@lru_cache(maxsize=1)
def get_settings(config_path: str = "configs/config.yaml") -> Settings:
    """Load config from YAML and return a validated Settings object."""
    path = Path(config_path)
    if not path.exists():
        # Fall back to defaults if no config file present
        return Settings()

    with open(path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    return Settings(
        llm=LLMConfig(**raw.get("llm", {})),
        embeddings=EmbeddingConfig(**raw.get("embeddings", {})),
        vector_db=VectorDBConfig(**raw.get("vector_db", {})),
        chunking=ChunkingConfig(**raw.get("chunking", {})),
        retrieval=RetrievalConfig(**raw.get("retrieval", {})),
        data_sources=DataSourcesConfig(**raw.get("data_sources", {})),
        safety=SafetyConfig(**raw.get("safety", {})),
    )
