"""
src/ingestion/chunker.py

Section-aware chunking for Pakistani legal documents.

Why not simple fixed-size chunking?
  Legal documents have meaningful boundaries (Sections, Articles, Clauses).
  Crossing these boundaries in a chunk destroys retrieval precision — you get
  an answer that mixes Section 300 (murder) with Section 302 (punishment for
  murder). We preserve these boundaries as primary split points, then fall back
  to token-based splitting within long sections.

Strategy: RecursiveLegalChunker
  1. Split on section/article/clause headers (highest priority)
  2. Within long sections, split on paragraph breaks
  3. Final fallback: LangChain RecursiveCharacterTextSplitter

Usage:
    chunker = LegalChunker()
    chunks = chunker.chunk_documents(langchain_docs)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from loguru import logger

from src.utils.config import get_settings


# ── Chunk data model ───────────────────────────────────────────────────────

@dataclass
class LegalChunk:
    """A text chunk enriched with legal metadata for retrieval."""
    chunk_id: str                 # unique: {source_file}_p{page}_c{idx}
    text: str
    source_name: str
    source_file: str
    law_type: str
    page_number: int
    section: str
    chapter: str
    article: str
    language: str
    char_count: int
    metadata: dict

    def to_langchain_doc(self) -> Document:
        return Document(
            page_content=self.text,
            metadata={
                "chunk_id": self.chunk_id,
                "source_name": self.source_name,
                "source_file": self.source_file,
                "law_type": self.law_type,
                "page_number": self.page_number,
                "section": self.section,
                "chapter": self.chapter,
                "article": self.article,
                "language": self.language,
                **self.metadata,
            }
        )


# ── Section header patterns ───────────────────────────────────────────────

# These are the primary split points for Pakistani legal texts
LEGAL_SECTION_PATTERNS = [
    r"^(Chapter\s+[IVXLCDM]+\.?\s*[-–—]?\s*[\w\s]{3,60})$",
    r"^(Section\s+\d+[\w\-]*[A-Z]?\.?\s*[-–—]?\s*[\w\s]{2,60})$",
    r"^(Article\s+\d+[\w\-]*\.?\s*[-–—]?\s*[\w\s]{2,60})$",
    r"^(Clause\s+\d+[\w\-]*\.?\s*[-–—]?\s*[\w\s]{2,60})$",
    r"^(Rule\s+\d+[\w\-]*\.?\s*[-–—]?\s*[\w\s]{2,60})$",
    r"^(Schedule\s+[IVXLCDM\d]+\.?\s*[-–—]?\s*[\w\s]{2,40})$",
    r"^(\d+\.\s+[A-Z][^.]{5,60})$",   # Numbered clauses: "1. General provisions"
]

SECTION_REGEX = re.compile(
    "|".join(LEGAL_SECTION_PATTERNS),
    re.MULTILINE | re.IGNORECASE
)


# ── LegalChunker ───────────────────────────────────────────────────────────

class LegalChunker:
    """
    Section-aware chunker that respects legal document structure.

    Chunking hierarchy:
      1. Section/Article boundaries (primary)
      2. Paragraph breaks (secondary)
      3. Token-based recursive splitting (fallback for long sections)
    """

    def __init__(self, config=None):
        cfg = config or get_settings().chunking
        self.chunk_size = cfg.chunk_size
        self.chunk_overlap = cfg.chunk_overlap

        # Fallback token-based splitter
        self.token_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size * 4,   # approx 4 chars per token
            chunk_overlap=self.chunk_overlap * 4,
            separators=["\n\n", "\n", ". ", " "],
            length_function=len,
        )

    # ── Public API ─────────────────────────────────────────────────────

    def chunk_documents(self, documents: list[Document]) -> list[Document]:
        """
        Chunk a list of LangChain Documents.
        Returns a flat list of chunk Documents with enriched metadata.
        """
        all_chunks: list[Document] = []
        for doc in documents:
            chunks = self._chunk_single_doc(doc)
            all_chunks.extend(chunks)

        logger.info(
            f"Chunked {len(documents)} docs → {len(all_chunks)} chunks "
            f"(avg {len(all_chunks)//max(len(documents),1)} per doc)"
        )
        return all_chunks

    # ── Core chunking logic ────────────────────────────────────────────

    def _chunk_single_doc(self, doc: Document) -> list[Document]:
        text = doc.page_content
        meta = doc.metadata.copy()

        # 1. Try section-aware splitting
        sections = self._split_on_sections(text)

        if len(sections) <= 1:
            # No section boundaries found → fall back to token-based
            sections = self._fallback_split(text)

        chunks: list[Document] = []
        for idx, (section_header, section_text) in enumerate(sections):
            # If the section itself is too long, split further
            sub_texts = self._split_if_too_long(section_text)

            for sub_idx, sub_text in enumerate(sub_texts):
                sub_text = sub_text.strip()
                if len(sub_text) < 50:
                    continue

                # Build chunk metadata
                chunk_meta = meta.copy()
                if section_header:
                    # Update section tag from header
                    chunk_meta["section"] = self._clean_header(
                        section_header, meta.get("section", "")
                    )
                chunk_meta["chunk_index"] = idx * 100 + sub_idx
                chunk_meta["chunk_id"] = self._make_chunk_id(meta, idx, sub_idx)
                chunk_meta["char_count"] = len(sub_text)

                # Prepend section header to chunk for context
                full_text = (
                    f"{section_header}\n{sub_text}"
                    if section_header and section_header not in sub_text
                    else sub_text
                )

                chunks.append(Document(
                    page_content=full_text,
                    metadata=chunk_meta,
                ))

        return chunks

    def _split_on_sections(self, text: str) -> list[tuple[str, str]]:
        """
        Split text at legal section headers.
        Returns list of (header, body) tuples.
        """
        parts: list[tuple[str, str]] = []
        matches = list(SECTION_REGEX.finditer(text))

        if not matches:
            return [("", text)]

        # Text before first section header
        if matches[0].start() > 0:
            preamble = text[:matches[0].start()].strip()
            if preamble:
                parts.append(("", preamble))

        for i, match in enumerate(matches):
            header = match.group(0).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                parts.append((header, body))

        return parts if parts else [("", text)]

    def _fallback_split(self, text: str) -> list[tuple[str, str]]:
        """Token-based fallback when no section headers found."""
        chunks = self.token_splitter.split_text(text)
        return [("", c) for c in chunks]

    def _split_if_too_long(self, text: str) -> list[str]:
        """Split a single section body if it exceeds chunk_size."""
        if len(text) <= self.chunk_size * 4:
            return [text]
        return self.token_splitter.split_text(text)

    # ── Helpers ───────────────────────────────────────────────────────

    def _clean_header(self, header: str, existing_section: str) -> str:
        """Return the most specific section label."""
        h = header.strip()[:100]
        if re.match(r"(Section|Article|Clause|Rule)\s+\d+", h, re.I):
            return h
        return existing_section or h

    def _make_chunk_id(self, meta: dict, idx: int, sub_idx: int) -> str:
        source = meta.get("source_file", "unknown")
        page = meta.get("page_number", 0)
        return f"{source}_p{page}_c{idx}_{sub_idx}"


# ── Chunk statistics ───────────────────────────────────────────────────────

def print_chunk_stats(chunks: list[Document]) -> None:
    """Print useful diagnostics about the chunks produced."""
    lengths = [len(c.page_content) for c in chunks]
    sources = {c.metadata.get("source_name", "?") for c in chunks}
    law_types = {}
    for c in chunks:
        lt = c.metadata.get("law_type", "unknown")
        law_types[lt] = law_types.get(lt, 0) + 1

    print(f"\n{'='*50}")
    print(f"Total chunks  : {len(chunks)}")
    print(f"Avg length    : {sum(lengths)//len(lengths)} chars")
    print(f"Min length    : {min(lengths)} chars")
    print(f"Max length    : {max(lengths)} chars")
    print(f"Sources       : {len(sources)}")
    print(f"By law type   : {law_types}")
    print(f"{'='*50}\n")
