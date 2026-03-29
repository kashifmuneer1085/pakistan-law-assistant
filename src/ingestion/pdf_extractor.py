"""
src/ingestion/pdf_extractor.py

Extract text from legal PDF documents (PPC, PECA, etc.) using PyMuPDF
and pdfplumber. Returns structured chunks preserving section metadata.

Usage:
    extractor = PDFExtractor()
    docs = extractor.extract("data/raw/pdfs/ppc_1860.pdf",
                              source_name="Pakistan Penal Code",
                              law_type="criminal")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

from loguru import logger


# ── Data models ────────────────────────────────────────────────────────────

@dataclass
class LegalDocument:
    """A raw text block extracted from a legal PDF with full metadata."""
    text: str
    source_file: str
    source_name: str
    law_type: str                   # criminal | civil | cyber | procedure | service
    page_number: int
    section: str = ""               # e.g. "Section 302"
    chapter: str = ""               # e.g. "Chapter XIV"
    article: str = ""               # e.g. "Article 9"
    language: str = "en"            # en | ur | bi (bilingual)
    metadata: dict = field(default_factory=dict)

    def to_langchain_doc(self):
        """Convert to LangChain Document for pipeline compatibility."""
        from langchain.schema import Document
        return Document(
            page_content=self.text,
            metadata={
                "source_file": self.source_file,
                "source_name": self.source_name,
                "law_type": self.law_type,
                "page_number": self.page_number,
                "section": self.section,
                "chapter": self.chapter,
                "article": self.article,
                "language": self.language,
                **self.metadata,
            }
        )


# ── Section header patterns for Pakistani legal texts ──────────────────────

SECTION_PATTERNS = [
    re.compile(r"^(Section\s+\d+[\w\-]*\.?\s*[-–—]?\s*.+)$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(Article\s+\d+[\w\-]*\.?\s*[-–—]?\s*.+)$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(Clause\s+\d+[\w\-]*\.?\s*[-–—]?\s*.+)$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(\d+\.\s+[A-Z].+)$", re.MULTILINE),           # numbered clauses
    re.compile(r"^(Chapter\s+[IVXLCDM]+\.?\s*.+)$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(CHAPTER\s+[IVXLCDM]+\.?\s*.+)$", re.MULTILINE),
]


def detect_section(text: str) -> tuple[str, str]:
    """
    Scan text for the most specific section/article header.
    Returns (section_label, chapter_label).
    """
    section = ""
    chapter = ""
    for line in text.split("\n")[:5]:
        line = line.strip()
        if re.match(r"(Section|Article|Clause)\s+\d+", line, re.IGNORECASE):
            section = line[:80]
        elif re.match(r"Chapter\s+[IVXLCDM]+", line, re.IGNORECASE):
            chapter = line[:80]
    return section, chapter


# ── PDF Extractor ──────────────────────────────────────────────────────────

class PDFExtractor:
    """
    Multi-strategy PDF extractor.

    Strategy 1 (primary): PyMuPDF  — fast, preserves layout, good for structured docs
    Strategy 2 (fallback): pdfplumber — better for tabular/column layouts
    """

    def __init__(self):
        self._check_dependencies()

    def _check_dependencies(self):
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("Install PyMuPDF: pip install pymupdf")

    def extract(
        self,
        pdf_path: str | Path,
        source_name: str,
        law_type: str = "general",
        language: str = "en",
    ) -> list[LegalDocument]:
        """
        Extract all pages from a PDF as LegalDocument objects.

        Args:
            pdf_path:    Path to the PDF file.
            source_name: Human-readable name (e.g. "Pakistan Penal Code 1860").
            law_type:    Category tag for filtering (criminal/cyber/service etc.)
            language:    Primary language of document (en/ur/bi).

        Returns:
            List of LegalDocument objects, one per page.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(f"Extracting: {pdf_path.name} ({law_type})")
        docs: list[LegalDocument] = []

        try:
            docs = self._extract_with_pymupdf(pdf_path, source_name, law_type, language)
        except Exception as e:
            logger.warning(f"PyMuPDF failed ({e}), falling back to pdfplumber")
            docs = self._extract_with_pdfplumber(pdf_path, source_name, law_type, language)

        logger.success(f"Extracted {len(docs)} pages from {pdf_path.name}")
        return docs

    def _extract_with_pymupdf(
        self, path: Path, source_name: str, law_type: str, language: str
    ) -> list[LegalDocument]:
        import fitz

        docs = []
        with fitz.open(str(path)) as pdf:
            for page_num, page in enumerate(pdf, start=1):
                text = page.get_text("text")
                text = self._clean_text(text)
                if len(text.strip()) < 30:     # skip near-empty pages
                    continue

                section, chapter = detect_section(text)
                docs.append(LegalDocument(
                    text=text,
                    source_file=path.name,
                    source_name=source_name,
                    law_type=law_type,
                    page_number=page_num,
                    section=section,
                    chapter=chapter,
                    language=language,
                ))
        return docs

    def _extract_with_pdfplumber(
        self, path: Path, source_name: str, law_type: str, language: str
    ) -> list[LegalDocument]:
        import pdfplumber

        docs = []
        with pdfplumber.open(str(path)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                text = self._clean_text(text)
                if len(text.strip()) < 30:
                    continue

                section, chapter = detect_section(text)
                docs.append(LegalDocument(
                    text=text,
                    source_file=path.name,
                    source_name=source_name,
                    law_type=law_type,
                    page_number=page_num,
                    section=section,
                    chapter=chapter,
                    language=language,
                ))
        return docs

    def _clean_text(self, text: str) -> str:
        """Remove PDF artefacts, normalise whitespace."""
        text = re.sub(r"\x00", "", text)           # null bytes
        text = re.sub(r"[ \t]{2,}", " ", text)     # multiple spaces
        text = re.sub(r"\n{3,}", "\n\n", text)     # excessive blank lines
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # hyphenated line breaks
        return text.strip()

    def extract_directory(
        self,
        pdf_dir: str | Path,
        source_map: dict[str, dict] | None = None,
    ) -> list[LegalDocument]:
        """
        Extract all PDFs from a directory.

        Args:
            pdf_dir:    Directory containing PDFs.
            source_map: Optional dict mapping filename -> {source_name, law_type, language}.
                        Inferred from filename if not provided.

        Returns:
            Combined list of all LegalDocument objects.
        """
        pdf_dir = Path(pdf_dir)
        all_docs: list[LegalDocument] = []
        source_map = source_map or {}

        for pdf_file in sorted(pdf_dir.glob("*.pdf")):
            meta = source_map.get(pdf_file.name, {})
            source_name = meta.get("source_name", pdf_file.stem.replace("_", " ").title())
            law_type = meta.get("law_type", "general")
            language = meta.get("language", "en")

            try:
                docs = self.extract(pdf_file, source_name, law_type, language)
                all_docs.extend(docs)
            except Exception as e:
                logger.error(f"Failed to extract {pdf_file.name}: {e}")

        logger.success(f"Total extracted: {len(all_docs)} pages from {pdf_dir}")
        return all_docs


# ── Predefined source map for Pakistan legal corpus ────────────────────────

PAKISTAN_LAW_SOURCE_MAP = {
    "ppc_1860.pdf": {
        "source_name": "Pakistan Penal Code 1860",
        "law_type": "criminal",
        "language": "en",
    },
    "peca_2016.pdf": {
        "source_name": "Prevention of Electronic Crimes Act 2016",
        "law_type": "cyber",
        "language": "en",
    },
    "fia_cybercrime.pdf": {
        "source_name": "FIA Cyber Crime Laws",
        "law_type": "cyber",
        "language": "en",
    },
    "punjab_service_manual.pdf": {
        "source_name": "Punjab Government Service Manual",
        "law_type": "service",
        "language": "en",
    },
    "nadra_procedures.pdf": {
        "source_name": "NADRA Documentation Procedures",
        "law_type": "service",
        "language": "en",
    },
    "driving_license_punjab.pdf": {
        "source_name": "Punjab Police Driving License Procedure",
        "law_type": "service",
        "language": "en",
    },
    "constitution_1973.pdf": {
        "source_name": "Constitution of Pakistan 1973",
        "law_type": "constitutional",
        "language": "en",
    },
    "crpc.pdf": {
        "source_name": "Code of Criminal Procedure",
        "law_type": "procedure",
        "language": "en",
    },
}
