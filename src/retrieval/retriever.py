"""
src/retrieval/retriever.py

Two-stage retrieval pipeline:
  Stage 1: Hybrid FAISS + BM25 search → top-k candidates
  Stage 2: Cross-encoder reranking   → top-r final documents

Why cross-encoder reranking?
  Bi-encoder (FAISS) is fast but approximate. The cross-encoder sees query +
  document together and produces a more accurate relevance score. Reranking
  15-20 candidates down to 3-5 consistently outperforms raw bi-encoder top-5.

Usage:
    retriever = LegalRetriever(vector_store)
    result = retriever.retrieve("What is the punishment for cybercrime?")
    for doc, score in result.documents:
        print(doc.metadata['source_name'], score)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain.schema import Document
from loguru import logger
from sentence_transformers import CrossEncoder

from src.retrieval.vector_store import VectorStore
from src.utils.config import get_settings


# ── Result model ───────────────────────────────────────────────────────────

@dataclass
class RetrievalResult:
    """Structured output of the retrieval pipeline."""
    query: str
    documents: list[tuple[Document, float]]   # (doc, relevance_score)
    found: bool = True
    explanation: str = ""

    def get_context_text(self) -> str:
        """Build a formatted context block for the LLM prompt."""
        parts = []
        for i, (doc, score) in enumerate(self.documents, 1):
            meta = doc.metadata
            source = meta.get("source_name", "Unknown Source")
            section = meta.get("section", "")
            page = meta.get("page_number", "")

            citation = source
            if section:
                citation += f" — {section}"
            if page:
                citation += f" (p.{page})"

            parts.append(f"[Source {i}: {citation}]\n{doc.page_content}")

        return "\n\n---\n\n".join(parts)

    def get_citations(self) -> list[dict]:
        """Return structured citation list for the UI."""
        citations = []
        for i, (doc, score) in enumerate(self.documents, 1):
            meta = doc.metadata
            citations.append({
                "index": i,
                "source_name": meta.get("source_name", "Unknown"),
                "source_file": meta.get("source_file", ""),
                "section": meta.get("section", ""),
                "chapter": meta.get("chapter", ""),
                "page_number": meta.get("page_number", ""),
                "law_type": meta.get("law_type", ""),
                "relevance_score": round(score, 4),
                "url": meta.get("source_url", ""),
            })
        return citations


# ── LegalRetriever ────────────────────────────────────────────────────────

class LegalRetriever:
    """
    Production-grade two-stage retriever for Pakistani legal documents.

    Attributes:
        vector_store:     Hybrid FAISS+BM25 index.
        reranker:         Cross-encoder reranking model (lazy loaded).
    """

    RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self, vector_store: VectorStore, config=None):
        self.vector_store = vector_store
        cfg = config or get_settings()
        self.ret_cfg = cfg.retrieval
        self.safety_cfg = cfg.safety
        self._reranker: CrossEncoder | None = None

    # ── Public API ─────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        use_reranker: bool = True,
    ) -> RetrievalResult:
        """
        Retrieve relevant legal documents for a query.

        Args:
            query:        User question (English or Urdu).
            top_k:        Number of final documents to return.
            filters:      Metadata filters e.g. {"law_type": "cyber"}.
            use_reranker: Whether to apply cross-encoder reranking.

        Returns:
            RetrievalResult with ranked documents and citations.
        """
        top_k = top_k or self.ret_cfg.rerank_top_k

        # Stage 1: Hybrid search
        k_candidates = self.ret_cfg.top_k
        candidates = self.vector_store.search(
            query, top_k=k_candidates, filters=filters
        )

        if not candidates:
            logger.warning(f"No candidates found for: {query[:60]}")
            return RetrievalResult(
                query=query,
                documents=[],
                found=False,
                explanation="No relevant documents found in the knowledge base.",
            )

        # Stage 2: Cross-encoder reranking
        if use_reranker and len(candidates) > top_k:
            candidates = self._rerank(query, candidates, top_k)
        else:
            candidates = candidates[:top_k]

        # Filter by score threshold
        threshold = self.ret_cfg.score_threshold
        filtered = [(doc, score) for doc, score in candidates if score >= threshold]

        if not filtered and self.safety_cfg.require_sources:
            logger.warning(f"All candidates below threshold {threshold} for: {query[:60]}")
            return RetrievalResult(
                query=query,
                documents=[],
                found=False,
                explanation=f"Confidence too low. Max score: {max(s for _,s in candidates):.3f}",
            )

        result = filtered if filtered else candidates[:top_k]
        logger.info(
            f"Retrieved {len(result)} docs for query: {query[:60]}... "
            f"(scores: {[round(s,3) for _,s in result]})"
        )

        return RetrievalResult(query=query, documents=result, found=True)

    def retrieve_for_summary(self, topic: str, top_k: int = 5) -> RetrievalResult:
        """
        Retrieve documents for summarization tasks.
        Uses a higher top_k and no score threshold.
        """
        candidates = self.vector_store.search(topic, top_k=top_k)
        if not candidates:
            return RetrievalResult(query=topic, documents=[], found=False)

        if len(candidates) > top_k:
            candidates = self._rerank(topic, candidates, top_k)

        return RetrievalResult(query=topic, documents=candidates[:top_k], found=True)

    # ── Cross-encoder reranking ────────────────────────────────────────

    def _rerank(
        self,
        query: str,
        candidates: list[tuple[Document, float]],
        top_k: int,
    ) -> list[tuple[Document, float]]:
        """
        Re-score candidates with a cross-encoder and return top_k.

        The cross-encoder sees (query, document_text) together, producing
        a much more accurate relevance score than the bi-encoder alone.
        """
        reranker = self._get_reranker()
        pairs = [[query, doc.page_content[:512]] for doc, _ in candidates]

        try:
            scores = reranker.predict(pairs)
        except Exception as e:
            logger.warning(f"Reranker failed ({e}), using original scores")
            return candidates[:top_k]

        # Combine with original score for stability
        combined = [
            (doc, float(scores[i]) * 0.8 + orig_score * 0.2)
            for i, (doc, orig_score) in enumerate(candidates)
        ]
        combined.sort(key=lambda x: x[1], reverse=True)
        return combined[:top_k]

    def _get_reranker(self) -> CrossEncoder:
        if self._reranker is None:
            logger.info(f"Loading reranker: {self.RERANKER_MODEL}")
            self._reranker = CrossEncoder(self.RERANKER_MODEL)
        return self._reranker

    # ── Utility ────────────────────────────────────────────────────────

    def get_law_type_filter(self, query: str) -> dict | None:
        """
        Simple heuristic: detect query intent and apply pre-filter.
        Reduces search space and improves precision for clear-cut queries.
        """
        query_lower = query.lower()

        cyber_keywords = ["cybercrime", "peca", "online", "hacking", "social media", "digital"]
        criminal_keywords = ["murder", "theft", "robbery", "assault", "fir", "arrest", "bail"]
        service_keywords = ["domicile", "driving license", "cnic", "nadra", "apply", "procedure", "documents required"]
        const_keywords = ["fundamental rights", "constitution", "article 25", "human rights"]

        if any(k in query_lower for k in cyber_keywords):
            return {"law_type": "cyber"}
        elif any(k in query_lower for k in service_keywords):
            return {"law_type": "service"}
        elif any(k in query_lower for k in const_keywords):
            return {"law_type": "constitutional"}
        elif any(k in query_lower for k in criminal_keywords):
            return {"law_type": ["criminal", "procedure"]}

        return None   # no pre-filter, search everything
