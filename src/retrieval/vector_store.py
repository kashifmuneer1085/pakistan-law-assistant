"""
src/retrieval/vector_store.py

Dual-index vector store:
  - FAISS  → dense semantic search via multilingual-e5-large embeddings
  - BM25   → sparse keyword search (rank-bm25)
  - Hybrid → Reciprocal Rank Fusion combining both scores

Why multilingual-e5-large?
  Supports English and Urdu in the same embedding space, so bilingual
  queries work without language detection routing.

Usage:
    store = VectorStore()
    store.build(chunks)
    store.save()

    store = VectorStore()
    store.load()
    results = store.search("punishment for cybercrime in Pakistan", top_k=5)
"""
from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from langchain.schema import Document
from loguru import logger
from sentence_transformers import SentenceTransformer

from src.utils.config import get_settings


class VectorStore:
    """
    Hybrid FAISS + BM25 vector store for legal document retrieval.

    Public methods:
        build(docs)        — build both indexes from Document list
        save()             — persist to disk
        load()             — load from disk
        search(query, k)   — hybrid search, returns top-k Documents
    """

    def __init__(self, config=None):
        cfg = config or get_settings()
        self.emb_cfg = cfg.embeddings
        self.vec_cfg = cfg.vector_db
        self.ret_cfg = cfg.retrieval

        self._embed_model: SentenceTransformer | None = None
        self._faiss_index = None          # faiss.Index
        self._bm25_index = None           # BM25Okapi
        self._documents: list[Document] = []
        self._tokenized_corpus: list[list[str]] = []

    # ── Build ──────────────────────────────────────────────────────────

    def build(self, documents: list[Document]) -> None:
        """
        Build FAISS and BM25 indexes from a list of LangChain Documents.
        Call save() afterwards to persist.
        """
        if not documents:
            raise ValueError("Cannot build index from empty document list.")

        logger.info(f"Building indexes from {len(documents)} chunks...")
        self._documents = documents
        texts = [d.page_content for d in documents]

        # 1. Build dense FAISS index
        self._build_faiss(texts)

        # 2. Build sparse BM25 index
        self._build_bm25(texts)

        logger.success("Indexes built successfully.")

    def _build_faiss(self, texts: list[str]) -> None:
        import faiss

        model = self._get_embed_model()
        logger.info(f"Encoding {len(texts)} chunks with {self.emb_cfg.model}...")

        embeddings = model.encode(
            texts,
            batch_size=self.emb_cfg.batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,   # cosine similarity via inner product
        )
        embeddings = np.array(embeddings, dtype=np.float32)
        dim = embeddings.shape[1]

        # IVF index for large corpora (>10k docs), flat for small
        if len(texts) > 10_000:
            n_cells = min(int(len(texts) ** 0.5), 1024)
            quantizer = faiss.IndexFlatIP(dim)
            self._faiss_index = faiss.IndexIVFFlat(
                quantizer, dim, n_cells, faiss.METRIC_INNER_PRODUCT
            )
            self._faiss_index.train(embeddings)
        else:
            self._faiss_index = faiss.IndexFlatIP(dim)

        self._faiss_index.add(embeddings)
        logger.info(f"FAISS index: {self._faiss_index.ntotal} vectors, dim={dim}")

    def _build_bm25(self, texts: list[str]) -> None:
        from rank_bm25 import BM25Okapi

        self._tokenized_corpus = [self._tokenize(t) for t in texts]
        self._bm25_index = BM25Okapi(self._tokenized_corpus)
        logger.info(f"BM25 index: {len(self._tokenized_corpus)} documents")

    # ── Search ─────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        """
        Hybrid search: combine FAISS (semantic) + BM25 (keyword) via RRF.

        Args:
            query:    User query string (English or Urdu).
            top_k:    Number of results to return.
            filters:  Optional metadata filters e.g. {"law_type": "criminal"}.

        Returns:
            List of (Document, score) sorted by descending relevance.
        """
        if not self._faiss_index or not self._bm25_index:
            raise RuntimeError("Index not built or loaded. Call build() or load() first.")

        top_k = top_k or self.ret_cfg.top_k
        alpha = self.ret_cfg.hybrid_alpha   # 0=pure BM25, 1=pure FAISS

        # Get candidates from both indexes (fetch 2× for RRF headroom)
        k_candidates = min(top_k * 4, len(self._documents))

        faiss_results = self._search_faiss(query, k_candidates)
        bm25_results = self._search_bm25(query, k_candidates)

        # Reciprocal Rank Fusion
        rrf_scores = self._reciprocal_rank_fusion(
            faiss_results, bm25_results, alpha=alpha
        )

        # Apply metadata filters
        if filters:
            rrf_scores = [
                (doc, score) for doc, score in rrf_scores
                if self._matches_filters(doc, filters)
            ]

        # Return top_k
        results = rrf_scores[:top_k]
        return results

    def _search_faiss(
        self, query: str, k: int
    ) -> list[tuple[int, float]]:
        """Returns (doc_index, score) pairs from FAISS."""
        model = self._get_embed_model()
        q_embed = model.encode(
            [query], normalize_embeddings=True
        ).astype(np.float32)

        scores, indices = self._faiss_index.search(q_embed, k)
        return [(int(idx), float(score)) for idx, score in zip(indices[0], scores[0]) if idx >= 0]

    def _search_bm25(
        self, query: str, k: int
    ) -> list[tuple[int, float]]:
        """Returns (doc_index, score) pairs from BM25."""
        tokens = self._tokenize(query)
        scores = self._bm25_index.get_scores(tokens)
        top_indices = np.argsort(scores)[::-1][:k]
        return [(int(i), float(scores[i])) for i in top_indices if scores[i] > 0]

    def _reciprocal_rank_fusion(
        self,
        faiss_results: list[tuple[int, float]],
        bm25_results: list[tuple[int, float]],
        alpha: float = 0.7,
        k_rrf: int = 60,
    ) -> list[tuple[Document, float]]:
        """
        Combine two ranked lists with Reciprocal Rank Fusion.
        alpha=0.7 → 70% weight to semantic, 30% to keyword.
        """
        scores: dict[int, float] = {}

        for rank, (idx, _) in enumerate(faiss_results):
            scores[idx] = scores.get(idx, 0.0) + alpha / (k_rrf + rank + 1)

        for rank, (idx, _) in enumerate(bm25_results):
            scores[idx] = scores.get(idx, 0.0) + (1 - alpha) / (k_rrf + rank + 1)

        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            (self._documents[idx], score)
            for idx, score in sorted_items
            if idx < len(self._documents)
        ]

    # ── Persist ────────────────────────────────────────────────────────

    def save(self) -> None:
        """Save FAISS index + BM25 index + documents to disk."""
        import faiss

        faiss_path = Path(self.vec_cfg.index_path)
        faiss_path.parent.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._faiss_index, str(faiss_path) + ".faiss")

        bm25_path = Path(self.ret_cfg.bm25_index_path)
        bm25_path.parent.mkdir(parents=True, exist_ok=True)

        with open(bm25_path, "wb") as f:
            pickle.dump({
                "bm25": self._bm25_index,
                "tokenized_corpus": self._tokenized_corpus,
            }, f)

        docs_path = str(faiss_path) + "_docs.pkl"
        with open(docs_path, "wb") as f:
            pickle.dump(self._documents, f)

        logger.success(
            f"Saved: FAISS ({self._faiss_index.ntotal} vectors), "
            f"BM25 ({len(self._tokenized_corpus)} docs), "
            f"Docs ({len(self._documents)})"
        )

    def load(self) -> None:
        """Load FAISS index + BM25 + documents from disk."""
        import faiss

        faiss_path = str(Path(self.vec_cfg.index_path)) + ".faiss"
        if not os.path.exists(faiss_path):
            raise FileNotFoundError(
                f"FAISS index not found at {faiss_path}. "
                "Run `python scripts/ingest_documents.py` first."
            )

        self._faiss_index = faiss.read_index(faiss_path)
        logger.info(f"Loaded FAISS index: {self._faiss_index.ntotal} vectors")

        with open(self.ret_cfg.bm25_index_path, "rb") as f:
            data = pickle.load(f)
        self._bm25_index = data["bm25"]
        self._tokenized_corpus = data["tokenized_corpus"]
        logger.info(f"Loaded BM25: {len(self._tokenized_corpus)} docs")

        docs_path = str(Path(self.vec_cfg.index_path)) + "_docs.pkl"
        with open(docs_path, "rb") as f:
            self._documents = pickle.load(f)
        logger.info(f"Loaded {len(self._documents)} document chunks")

    def add_documents(self, new_docs: list[Document]) -> None:
        """
        Incrementally add new documents to both indexes.
        Useful for the /upload endpoint without rebuilding from scratch.
        """
        import faiss

        texts = [d.page_content for d in new_docs]
        model = self._get_embed_model()
        embeddings = model.encode(
            texts, batch_size=self.emb_cfg.batch_size, normalize_embeddings=True
        ).astype(np.float32)

        self._faiss_index.add(embeddings)

        # BM25 requires full rebuild (O(n) is acceptable for document uploads)
        all_texts = [d.page_content for d in self._documents] + texts
        from rank_bm25 import BM25Okapi
        self._tokenized_corpus = [self._tokenize(t) for t in all_texts]
        self._bm25_index = BM25Okapi(self._tokenized_corpus)

        self._documents.extend(new_docs)
        logger.info(f"Added {len(new_docs)} docs. Total: {len(self._documents)}")

    # ── Helpers ────────────────────────────────────────────────────────

    def _get_embed_model(self) -> SentenceTransformer:
        if self._embed_model is None:
            logger.info(f"Loading embedding model: {self.emb_cfg.model}")
            self._embed_model = SentenceTransformer(
                self.emb_cfg.model,
                device=self.emb_cfg.device,
            )
        return self._embed_model

    def _tokenize(self, text: str) -> list[str]:
        """Simple whitespace + punctuation tokenizer (language-agnostic)."""
        import re
        tokens = re.findall(r"\b\w+\b", text.lower())
        return tokens

    def _matches_filters(self, doc: Document, filters: dict) -> bool:
        for key, value in filters.items():
            doc_value = doc.metadata.get(key)
            if isinstance(value, list):
                if doc_value not in value:
                    return False
            elif doc_value != value:
                return False
        return True

    @property
    def total_documents(self) -> int:
        return len(self._documents)
