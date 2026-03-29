"""
src/pipeline.py

The main RAG pipeline — a single entry point that wires together:
  retriever + generator + language utils

This is what the API and Streamlit app both import.
No need to manage components individually after this.

Usage:
    pipeline = PakistanLawPipeline()
    response = pipeline.ask("What is the punishment for cybercrime in Pakistan?")
    print(response.answer)

    # Urdu query — auto-translates for retrieval, responds in Urdu
    response = pipeline.ask("سائبر کرائم کی سزا کیا ہے؟")
"""
from __future__ import annotations

from loguru import logger

from src.generation.generator import LegalAnswerGenerator, LegalResponse
from src.retrieval.retriever import LegalRetriever
from src.retrieval.vector_store import VectorStore
from src.utils.config import get_settings
from src.utils.language import LanguageUtils


class PakistanLawPipeline:
    """
    End-to-end RAG pipeline for Pakistani law queries.

    Lazy-loads all heavy components (embeddings, index) on first use.
    Thread-safe for Streamlit and FastAPI concurrent access.
    """

    def __init__(self, config=None):
        self.cfg = config or get_settings()
        self._vector_store: VectorStore | None = None
        self._retriever: LegalRetriever | None = None
        self._generator = LegalAnswerGenerator(self.cfg)
        self._lang = LanguageUtils()

    # ── Initialization ─────────────────────────────────────────────────

    def load(self) -> "PakistanLawPipeline":
        """
        Load vector store from disk. Call once before first query.
        Returns self for chaining: pipeline = PakistanLawPipeline().load()
        """
        self._vector_store = VectorStore(self.cfg)
        self._vector_store.load()
        self._retriever = LegalRetriever(self._vector_store, self.cfg)
        logger.success(
            f"Pipeline ready: {self._vector_store.total_documents} chunks loaded."
        )
        return self

    @property
    def is_ready(self) -> bool:
        return (
            self._vector_store is not None
            and self._vector_store.total_documents > 0
        )

    # ── Main public methods ────────────────────────────────────────────

    def ask(
        self,
        question: str,
        top_k: int = 3,
        filters: dict | None = None,
        language: str | None = None,
    ) -> LegalResponse:
        """
        Answer a legal question end-to-end.

        Flow:
          1. Detect language
          2. Translate Urdu → English for retrieval (if needed)
          3. Auto-detect law_type filter
          4. Hybrid retrieval (FAISS + BM25)
          5. Cross-encoder reranking
          6. Grounded LLM generation with citations
          7. Return structured LegalResponse

        Args:
            question: User question in English or Urdu.
            top_k:    Number of source documents to use.
            filters:  Optional metadata filters.
            language: Override detected language ("en" or "ur").

        Returns:
            LegalResponse with answer, citations, and disclaimer.
        """
        self._ensure_ready()

        # Step 1: Detect language
        detected_lang = self._lang.detect(question)
        response_lang = language or detected_lang

        # Step 2: Translate Urdu → English for retrieval
        retrieval_query = self._lang.expand_query_for_retrieval(question)

        # Step 3: Auto-detect law type filter
        if not filters:
            filters = self._retriever.get_law_type_filter(retrieval_query)

        # Step 4 + 5: Retrieve + rerank
        retrieval = self._retriever.retrieve(
            retrieval_query,
            top_k=top_k,
            filters=filters,
        )

        # Step 6: Generate answer
        response = self._generator.generate(
            question,           # original question (may be Urdu)
            retrieval,
            language=response_lang,
        )

        return response

    def summarize(self, topic: str, language: str = "en") -> LegalResponse:
        """
        Generate a structured summary of a legal topic or law.

        Args:
            topic:    Topic to summarize (e.g. "PECA 2016", "bail provisions").
            language: Response language.

        Returns:
            LegalResponse with structured summary and citations.
        """
        self._ensure_ready()

        retrieval_topic = self._lang.expand_query_for_retrieval(topic)
        retrieval = self._retriever.retrieve_for_summary(retrieval_topic, top_k=5)

        return self._generator.summarize(topic, retrieval, language=language)

    def add_document(
        self,
        pdf_path: str,
        source_name: str,
        law_type: str = "general",
        language: str = "en",
    ) -> int:
        """
        Ingest a new PDF document at runtime.

        Args:
            pdf_path:    Path to the PDF file.
            source_name: Human-readable name for citations.
            law_type:    Category tag.
            language:    Document language.

        Returns:
            Number of chunks added.
        """
        self._ensure_ready()

        from src.ingestion.chunker import LegalChunker
        from src.ingestion.pdf_extractor import PDFExtractor

        extractor = PDFExtractor()
        chunker = LegalChunker()

        raw_docs = extractor.extract(pdf_path, source_name, law_type, language)
        langchain_docs = [d.to_langchain_doc() for d in raw_docs]
        chunks = chunker.chunk_documents(langchain_docs)

        self._vector_store.add_documents(chunks)
        self._vector_store.save()

        logger.success(f"Added {len(chunks)} chunks from {source_name}")
        return len(chunks)

    def get_stats(self) -> dict:
        """Return runtime stats about the loaded index."""
        if not self.is_ready:
            return {"ready": False}

        source_counts: dict[str, int] = {}
        for doc in self._vector_store._documents:
            name = doc.metadata.get("source_name", "Unknown")
            source_counts[name] = source_counts.get(name, 0) + 1

        return {
            "ready": True,
            "total_chunks": self._vector_store.total_documents,
            "sources": source_counts,
        }

    # ── Internal ───────────────────────────────────────────────────────

    def _ensure_ready(self):
        if not self.is_ready:
            raise RuntimeError(
                "Pipeline not loaded. Call pipeline.load() first, "
                "or run scripts/ingest_documents.py to build the index."
            )
