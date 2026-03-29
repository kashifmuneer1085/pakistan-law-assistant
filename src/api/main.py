"""
src/api/main.py

FastAPI backend for the Pakistan Law Assistant.

Endpoints:
  POST /query        — ask a legal question
  POST /summarize    — summarize a legal topic
  POST /upload       — upload a new legal document
  GET  /sources      — list all indexed sources
  GET  /health       — health check

Run:
  uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from src.ingestion.chunker import LegalChunker
from src.ingestion.pdf_extractor import PDFExtractor, PAKISTAN_LAW_SOURCE_MAP
from src.retrieval.retriever import LegalRetriever
from src.retrieval.vector_store import VectorStore
from src.generation.generator import LegalAnswerGenerator
from src.utils.config import get_settings

# ── App setup ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Pakistan Law & Government Assistant API",
    description=(
        "RAG-based API for querying Pakistani laws, regulations, "
        "and government service procedures."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singleton components (loaded once at startup) ──────────────────────────

_vector_store: VectorStore | None = None
_retriever: LegalRetriever | None = None
_generator: LegalAnswerGenerator | None = None
_extractor = PDFExtractor()
_chunker = LegalChunker()


@app.on_event("startup")
async def startup_event():
    """Load the vector store at startup."""
    global _vector_store, _retriever, _generator
    cfg = get_settings()

    _vector_store = VectorStore()
    try:
        _vector_store.load()
        logger.success(
            f"Loaded {_vector_store.total_documents} chunks into memory."
        )
    except FileNotFoundError:
        logger.warning(
            "No FAISS index found. Run `python scripts/ingest_documents.py` first.\n"
            "API will start but /query and /summarize will return errors until indexed."
        )

    _retriever = LegalRetriever(_vector_store)
    _generator = LegalAnswerGenerator()


def get_components():
    """Dependency: ensure components are ready."""
    if not _vector_store or _vector_store.total_documents == 0:
        raise HTTPException(
            status_code=503,
            detail="Knowledge base not indexed. Run ingest_documents.py first.",
        )
    return _retriever, _generator


# ── Request / Response models ──────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    language: str = "en"          # "en" or "ur"
    law_type: str | None = None   # optional filter: criminal/cyber/service/...
    top_k: int = 3


class QueryResponse(BaseModel):
    question: str
    answer: str
    citations: list[dict]
    disclaimer: str
    language: str
    found: bool


class SummarizeRequest(BaseModel):
    topic: str
    language: str = "en"


class UploadResponse(BaseModel):
    message: str
    chunks_added: int
    source_name: str


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Check if the API and index are ready."""
    total = _vector_store.total_documents if _vector_store else 0
    return {
        "status": "ok",
        "indexed_chunks": total,
        "ready": total > 0,
    }


@app.post("/query", response_model=QueryResponse)
async def query_law(request: QueryRequest):
    """
    Answer a legal question using RAG.

    Example:
        POST /query
        {"question": "What is the punishment for cybercrime in Pakistan?"}
    """
    retriever, generator = get_components()

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if len(request.question) > 1000:
        raise HTTPException(status_code=400, detail="Question too long (max 1000 chars).")

    # Auto-detect law_type filter
    filters = None
    if request.law_type:
        filters = {"law_type": request.law_type}
    else:
        filters = retriever.get_law_type_filter(request.question)

    retrieval = retriever.retrieve(
        request.question,
        top_k=request.top_k,
        filters=filters,
    )

    response = generator.generate(
        request.question,
        retrieval,
        language=request.language,
    )

    return QueryResponse(
        question=response.query,
        answer=response.answer,
        citations=response.citations,
        disclaimer=response.disclaimer,
        language=response.language,
        found=response.found,
    )


@app.post("/summarize", response_model=QueryResponse)
async def summarize_topic(request: SummarizeRequest):
    """
    Summarize a legal topic (e.g., "PECA 2016", "FIR registration").
    """
    retriever, generator = get_components()

    retrieval = retriever.retrieve_for_summary(request.topic, top_k=5)
    response = generator.summarize(
        request.topic,
        retrieval,
        language=request.language,
    )

    return QueryResponse(
        question=response.query,
        answer=response.answer,
        citations=response.citations,
        disclaimer=response.disclaimer,
        language=response.language,
        found=response.found,
    )


@app.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    source_name: str = Form(...),
    law_type: str = Form("general"),
    language: str = Form("en"),
):
    """
    Upload a new PDF legal document into the knowledge base.
    The document is chunked and added to both FAISS and BM25 indexes.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50MB).")

    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        # Extract + chunk
        docs = _extractor.extract(tmp_path, source_name, law_type, language)
        langchain_docs = [d.to_langchain_doc() for d in docs]
        chunks = _chunker.chunk_documents(langchain_docs)

        # Add to live indexes
        if not _vector_store:
            raise HTTPException(status_code=503, detail="Index not loaded.")
        _vector_store.add_documents(chunks)
        _vector_store.save()    # persist updated index

        logger.success(f"Uploaded: {file.filename} → {len(chunks)} chunks added")

        return UploadResponse(
            message=f"Successfully indexed {file.filename}",
            chunks_added=len(chunks),
            source_name=source_name,
        )
    except Exception as e:
        logger.error(f"Upload failed for {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/sources")
async def list_sources():
    """List all indexed sources with chunk counts."""
    if not _vector_store or not _vector_store._documents:
        return {"sources": []}

    source_counts: dict[str, dict] = {}
    for doc in _vector_store._documents:
        name = doc.metadata.get("source_name", "Unknown")
        if name not in source_counts:
            source_counts[name] = {
                "source_name": name,
                "law_type": doc.metadata.get("law_type", ""),
                "chunk_count": 0,
            }
        source_counts[name]["chunk_count"] += 1

    return {"sources": list(source_counts.values())}
