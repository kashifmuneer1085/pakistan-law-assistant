"""
tests/test_pipeline.py

Unit and integration tests for the Pakistan Law Assistant pipeline.

Run:
    pytest tests/ -v
    pytest tests/test_pipeline.py::test_chunker -v   # single test
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain.schema import Document


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_legal_docs() -> list[Document]:
    """A small set of realistic Pakistani legal document chunks."""
    return [
        Document(
            page_content=(
                "Section 302. Punishment of Qatl-i-amd.\n"
                "Whoever commits qatl-i-amd shall, subject to the provisions of "
                "this Chapter be punished with death as tazir or imprisonment for "
                "life as tazir if the act by which the death is caused is done with "
                "the intention of causing death, or with such bodily injury as was "
                "sufficient to cause death."
            ),
            metadata={
                "source_name": "Pakistan Penal Code 1860",
                "source_file": "ppc_1860.pdf",
                "law_type": "criminal",
                "section": "Section 302 — Punishment of Qatl-i-amd",
                "page_number": 112,
                "language": "en",
                "chunk_id": "ppc_1860.pdf_p112_c0_0",
            }
        ),
        Document(
            page_content=(
                "Section 20. Offences against dignity of a natural person.\n"
                "Whoever intentionally and publicly exhibits or displays or transmits "
                "any false information through any information system, intending to "
                "harm the reputation or privacy of a natural person, shall be "
                "punished with imprisonment for a term which may extend to three "
                "years or with fine which may extend to one million rupees or with both."
            ),
            metadata={
                "source_name": "Prevention of Electronic Crimes Act 2016",
                "source_file": "peca_2016.pdf",
                "law_type": "cyber",
                "section": "Section 20 — Offences against dignity",
                "page_number": 18,
                "language": "en",
                "chunk_id": "peca_2016.pdf_p18_c0_0",
            }
        ),
        Document(
            page_content=(
                "Domicile Certificate Requirements — Punjab.\n"
                "To obtain a domicile certificate in Punjab, the applicant must "
                "provide: (1) Copy of CNIC or B-Form, (2) Proof of residence "
                "(utility bill or property document), (3) Affidavit on Rs. 50 "
                "stamp paper, (4) Two passport-size photographs, "
                "(5) Application form duly filled."
            ),
            metadata={
                "source_name": "Punjab Government Service Manual",
                "source_file": "punjab_service_manual.pdf",
                "law_type": "service",
                "section": "Domicile Certificate Requirements",
                "page_number": 45,
                "language": "en",
                "chunk_id": "punjab_service_manual.pdf_p45_c0_0",
            }
        ),
    ]


@pytest.fixture
def mock_vector_store(sample_legal_docs):
    """VectorStore mock that returns sample docs without loading files."""
    store = MagicMock()
    store.total_documents = len(sample_legal_docs)
    store._documents = sample_legal_docs
    store.search.return_value = [(doc, 0.85) for doc in sample_legal_docs[:2]]
    return store


# ════════════════════════════════════════════════════════════════════════════
# Chunker tests
# ════════════════════════════════════════════════════════════════════════════

class TestLegalChunker:

    def test_section_aware_splitting(self):
        """Chunks should split on Section/Article boundaries."""
        from src.ingestion.chunker import LegalChunker

        chunker = LegalChunker()
        doc = Document(
            page_content=(
                "Section 1. Introduction.\n"
                "This is the introduction to the law. " * 20 + "\n\n"
                "Section 2. Definitions.\n"
                "This section defines all key legal terms used. " * 20 + "\n\n"
                "Section 3. Penalties.\n"
                "Violators shall be fined accordingly. " * 20
            ),
            metadata={
                "source_name": "Test Law",
                "source_file": "test.pdf",
                "law_type": "general",
                "page_number": 1,
                "section": "",
                "chapter": "",
                "article": "",
                "language": "en"
            }
        )
        chunks = chunker.chunk_documents([doc])
        assert len(chunks) >= 1, "Should produce at least one chunk"

    def test_chunk_metadata_preserved(self, sample_legal_docs):
        """Each chunk must carry source_name and law_type."""
        from src.ingestion.chunker import LegalChunker

        chunker = LegalChunker()
        chunks = chunker.chunk_documents(sample_legal_docs)
        for chunk in chunks:
            assert "source_name" in chunk.metadata
            assert "law_type" in chunk.metadata
            assert len(chunk.page_content) > 20

    def test_no_empty_chunks(self, sample_legal_docs):
        """No chunk should be empty or whitespace-only."""
        from src.ingestion.chunker import LegalChunker

        chunker = LegalChunker()
        chunks = chunker.chunk_documents(sample_legal_docs)
        for chunk in chunks:
            assert chunk.page_content.strip(), "Found empty chunk"

    def test_section_header_prepended(self):
        """Section header should appear in chunk text for context."""
        from src.ingestion.chunker import LegalChunker

        chunker = LegalChunker()
        doc = Document(
            page_content=(
                "Section 302. Punishment of Qatl-i-amd.\n"
                "Whoever commits qatl-i-amd shall be punished with "
                "death as tazir or imprisonment for life as tazir "
                "depending on the circumstances of the case."
            ),
            metadata={
                "source_name": "PPC",
                "source_file": "ppc.pdf",
                "law_type": "criminal",
                "page_number": 1,
                "section": "",
                "chapter": "",
                "article": "",
                "language": "en"
            }
        )
        chunks = chunker.chunk_documents([doc])
        assert len(chunks) >= 1, "Should produce at least one chunk"
        assert any("302" in c.page_content for c in chunks)


# ════════════════════════════════════════════════════════════════════════════
# Retriever tests
# ════════════════════════════════════════════════════════════════════════════

class TestLegalRetriever:

    def test_retrieve_returns_result(self, mock_vector_store):
        """retrieve() should return a RetrievalResult with documents."""
        from src.retrieval.retriever import LegalRetriever

        retriever = LegalRetriever(mock_vector_store)
        result = retriever.retrieve("punishment for murder", use_reranker=False)

        assert result.found
        assert len(result.documents) > 0

    def test_no_results_returns_not_found(self, mock_vector_store):
        """Empty search results should produce found=False."""
        from src.retrieval.retriever import LegalRetriever

        mock_vector_store.search.return_value = []
        retriever = LegalRetriever(mock_vector_store)
        result = retriever.retrieve("something completely irrelevant", use_reranker=False)

        assert not result.found
        assert result.documents == []

    def test_context_text_has_citations(self, mock_vector_store, sample_legal_docs):
        """get_context_text() should produce [Source N] labeled blocks."""
        from src.retrieval.retriever import LegalRetriever

        retriever = LegalRetriever(mock_vector_store)
        result = retriever.retrieve("cybercrime", use_reranker=False)

        context = result.get_context_text()
        assert "[Source 1:" in context
        assert "[Source 2:" in context

    def test_law_type_filter_detection(self, mock_vector_store):
        """Auto-filter should detect cyber queries."""
        from src.retrieval.retriever import LegalRetriever

        retriever = LegalRetriever(mock_vector_store)
        f = retriever.get_law_type_filter("What is PECA 2016 cybercrime punishment?")
        assert f == {"law_type": "cyber"}

        f2 = retriever.get_law_type_filter("What is the weather like?")
        assert f2 is None

    def test_citations_list_structure(self, mock_vector_store):
        """get_citations() should return dicts with required keys."""
        from src.retrieval.retriever import LegalRetriever

        retriever = LegalRetriever(mock_vector_store)
        result = retriever.retrieve("test", use_reranker=False)
        citations = result.get_citations()

        required_keys = {"index", "source_name", "section", "page_number", "relevance_score"}
        for cite in citations:
            assert required_keys.issubset(cite.keys())


# ════════════════════════════════════════════════════════════════════════════
# Generator tests
# ════════════════════════════════════════════════════════════════════════════

class TestLegalAnswerGenerator:

    def test_no_sources_returns_out_of_scope(self):
        """Generator must not hallucinate when no sources are found."""
        from src.generation.generator import LegalAnswerGenerator
        from src.retrieval.retriever import RetrievalResult

        gen = LegalAnswerGenerator()
        result = RetrievalResult(query="test", documents=[], found=False)
        response = gen.generate("test question", result)

        assert not response.found
        assert response.answer  # should have a polite refusal message
        assert response.citations == []

    def test_citation_validator_removes_out_of_range(self):
        """Citations beyond num_sources should be stripped from answer."""
        from src.generation.generator import LegalAnswerGenerator

        gen = LegalAnswerGenerator()
        answer = "See [Source 1] and [Source 5] for details."
        cleaned = gen._validate_citations(answer, num_sources=3)

        assert "[Source 1]" in cleaned
        assert "[Source 5]" not in cleaned

    def test_disclaimer_always_present(self):
        """LegalResponse must always carry the legal disclaimer."""
        from src.generation.generator import LegalAnswerGenerator, LegalResponse

        gen = LegalAnswerGenerator()
        from src.retrieval.retriever import RetrievalResult
        result = RetrievalResult(query="q", documents=[], found=False)
        response = gen.generate("q", result)

        assert response.disclaimer


# ════════════════════════════════════════════════════════════════════════════
# Language utils tests
# ════════════════════════════════════════════════════════════════════════════

class TestLanguageUtils:

    def test_detect_english(self):
        from src.utils.language import LanguageUtils
        util = LanguageUtils()
        assert util.detect("What is the punishment for murder?") == "en"

    def test_detect_urdu(self):
        from src.utils.language import LanguageUtils
        util = LanguageUtils()
        result = util.detect("سائبر کرائم کی سزا کیا ہے؟")
        assert result == "ur"

    def test_glossary_lookup(self):
        from src.utils.language import LanguageUtils, LEGAL_GLOSSARY_EN_UR
        util = LanguageUtils()
        assert "ضمانت" == LEGAL_GLOSSARY_EN_UR.get("bail")
        assert "ایف آئی آر" == LEGAL_GLOSSARY_EN_UR.get("FIR")


# ════════════════════════════════════════════════════════════════════════════
# PDF Extractor tests
# ════════════════════════════════════════════════════════════════════════════

class TestPDFExtractor:

    def test_detect_section(self):
        """detect_section() should find Section/Article headers."""
        from src.ingestion.pdf_extractor import detect_section

        text = "Section 302. Punishment of qatl-i-amd.\nWhoever commits..."
        section, chapter = detect_section(text)
        assert "302" in section

    def test_missing_pdf_raises(self):
        """Extracting a nonexistent file should raise FileNotFoundError."""
        from src.ingestion.pdf_extractor import PDFExtractor

        extractor = PDFExtractor()
        with pytest.raises(FileNotFoundError):
            extractor.extract("/nonexistent/file.pdf", "Test", "general")

    def test_source_map_completeness(self):
        """All expected PDF filenames should be in the source map."""
        from src.ingestion.pdf_extractor import PAKISTAN_LAW_SOURCE_MAP

        expected = ["ppc_1860.pdf", "peca_2016.pdf", "constitution_1973.pdf"]
        for fname in expected:
            assert fname in PAKISTAN_LAW_SOURCE_MAP, f"{fname} missing from source map"


# ════════════════════════════════════════════════════════════════════════════
# Integration test (mocked LLM)
# ════════════════════════════════════════════════════════════════════════════

class TestPipelineIntegration:

    def test_full_pipeline_mock(self, mock_vector_store, sample_legal_docs):
        """Integration test with mocked LLM — no API key needed."""
        from src.generation.generator import LegalAnswerGenerator
        from src.retrieval.retriever import LegalRetriever

        retriever = LegalRetriever(mock_vector_store)

        with patch.object(LegalAnswerGenerator, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                "The punishment for cybercrime under [Source 1] is three years "
                "imprisonment or a fine of one million rupees."
            )
            gen = LegalAnswerGenerator()
            result = retriever.retrieve("cybercrime punishment", use_reranker=False)
            response = gen.generate("cybercrime punishment", result)

            assert response.found
            assert "[Source 1]" in response.answer
            assert response.disclaimer
            assert len(response.citations) > 0
