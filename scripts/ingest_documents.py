"""
scripts/ingest_documents.py

One-command ingestion pipeline:
  1. Extract text from all PDFs in data/raw/pdfs/
  2. Scrape official government websites
  3. Chunk all documents (section-aware)
  4. Build FAISS + BM25 indexes
  5. Save to disk

Usage:
  python scripts/ingest_documents.py [--pdf-only] [--scrape-only] [--skip-scrape]

Environment:
  No API keys needed for ingestion. Only the LLM key is needed at query time.
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.ingestion.pdf_extractor import PDFExtractor, PAKISTAN_LAW_SOURCE_MAP
from src.ingestion.web_scraper import PakistanLawScraper
from src.ingestion.chunker import LegalChunker, print_chunk_stats
from src.retrieval.vector_store import VectorStore
from src.utils.config import get_settings

logger.remove()
logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")


def ingest_pdfs(pdf_dir: str) -> list:
    """Extract and convert all PDFs to LangChain documents."""
    extractor = PDFExtractor()
    pdf_path = Path(pdf_dir)

    if not pdf_path.exists() or not list(pdf_path.glob("*.pdf")):
        logger.warning(
            f"No PDFs found in {pdf_dir}.\n"
            "Download legal PDFs from official sources and place them here:\n"
            "  data/raw/pdfs/ppc_1860.pdf\n"
            "  data/raw/pdfs/peca_2016.pdf\n"
            "  etc."
        )
        return []

    raw_docs = extractor.extract_directory(pdf_path, source_map=PAKISTAN_LAW_SOURCE_MAP)
    return [d.to_langchain_doc() for d in raw_docs]


def ingest_web(scraped_dir: str, skip_scrape: bool = False) -> list:
    """Scrape or load web documents."""
    scraper = PakistanLawScraper()
    scraped_path = Path(scraped_dir)

    if not skip_scrape:
        logger.info("Scraping official government websites...")
        logger.warning(
            "Note: Web scraping may take 10-20 minutes. "
            "Use --skip-scrape to use cached data if available."
        )
        scraped_docs = scraper.scrape_all_sources()
        scraper.save_scraped(scraped_docs, scraped_dir)
    else:
        logger.info("Loading cached scraped documents...")
        scraped_docs = scraper.load_scraped(scraped_dir) if scraped_path.exists() else []

    return [d.to_langchain_doc() for d in scraped_docs]


def build_index(all_docs: list) -> None:
    """Chunk documents and build FAISS + BM25 indexes."""

    # Add supplementary service documents not covered by PDFs
    from langchain.schema import Document
    supplementary = [
        Document(
            page_content=(
                "CNIC Application and Renewal — NADRA Procedure.\n"
                "To apply for a new CNIC or renew existing CNIC from NADRA:\n\n"
                "NEW CNIC required documents:\n"
                "1. Original B-Form (birth registration certificate)\n"
                "2. Father or guardian CNIC copy\n"
                "3. Family registration certificate\n"
                "4. Two passport size photographs\n\n"
                "CNIC RENEWAL required documents:\n"
                "1. Old expired or expiring CNIC\n"
                "2. Proof of address if changed (utility bill)\n\n"
                "PROCEDURE:\n"
                "Step 1: Visit nearest NADRA Registration Centre (NRC)\n"
                "Step 2: Submit documents and give biometrics\n"
                "Step 3: Pay fee — Normal Rs.750, Urgent Rs.1500, Executive Rs.2500\n"
                "Step 4: Collect CNIC after processing\n"
                "CNIC valid for 10 years. Helpline: 051-111-786-100"
            ),
            metadata={
                "source_name": "NADRA Documentation Procedures",
                "source_file": "nadra_cnic_procedure.txt",
                "law_type": "service",
                "section": "CNIC Application and Renewal",
                "chapter": "", "article": "",
                "page_number": 1, "language": "en",
            }
        ),
        Document(
            page_content=(
                "Domicile Certificate Requirements — Punjab Government.\n"
                "Required documents for domicile certificate in Punjab:\n"
                "1. Original CNIC of applicant\n"
                "2. Proof of residence: utility bill not older than 3 months\n"
                "3. Affidavit on Rs.50 stamp paper\n"
                "4. Two passport size photographs\n"
                "5. Filled application form from Tehsil or District office\n"
                "6. B-Form for minors under 18 years\n"
                "Submit at local Tehsil Municipal Administration (TMA) office.\n"
                "Processing time: 7-15 working days. No fee charged."
            ),
            metadata={
                "source_name": "Punjab Government Service Manual",
                "source_file": "punjab_service_manual.txt",
                "law_type": "service",
                "section": "Domicile Certificate Procedure",
                "chapter": "", "article": "",
                "page_number": 1, "language": "en",
            }
        ),
        Document(
            page_content=(
                "Driving License Application — Punjab Police DLIMS.\n"
                "To apply for driving license in Punjab:\n"
                "Step 1: Visit DLA office or apply at dlims.punjab.gov.pk\n"
                "Step 2: Required documents:\n"
                "  - Original CNIC\n"
                "  - Medical certificate from registered doctor\n"
                "  - 4 passport size photographs\n"
                "  - Token fee payment receipt\n"
                "Step 3: Pass written theory test\n"
                "Step 4: Pass practical driving test\n"
                "Step 5: Collect license after 1-2 weeks\n"
                "Fee: Rs.750 motorcycle, Rs.1500 car.\n"
                "Minimum age: 18 years for car, 16 years for motorcycle."
            ),
            metadata={
                "source_name": "Punjab Police Driving License Procedure",
                "source_file": "driving_license_punjab.txt",
                "law_type": "service",
                "section": "Driving License Application",
                "chapter": "", "article": "",
                "page_number": 1, "language": "en",
            }
        ),
        Document(
            page_content=(
                "FIR Registration Procedure — Section 154 CrPC.\n"
                "Steps to register an FIR in Pakistan:\n"
                "Step 1: Visit nearest police station where crime occurred\n"
                "Step 2: Meet the Station House Officer (SHO)\n"
                "Step 3: Provide complaint with date, time, place of incident\n"
                "Step 4: SHO is legally bound to register FIR for cognizable offences\n"
                "Step 5: Receive free copy of FIR — this is your legal right\n"
                "Step 6: If police refuse, complain to DSP, SSP or Magistrate "
                "under Section 22-A CrPC\n"
                "FIR is only for cognizable (serious) offences."
            ),
            metadata={
                "source_name": "Code of Criminal Procedure 1898",
                "source_file": "crpc_fir.txt",
                "law_type": "procedure",
                "section": "Section 154 — FIR Registration",
                "chapter": "Chapter XII", "article": "",
                "page_number": 1, "language": "en",
            }
        ),
        Document(
            page_content=(
                "Bail Provisions in Pakistan — CrPC Section 497-498.\n"
                "Types of bail:\n"
                "1. Pre-arrest bail (Anticipatory) — Section 498 CrPC\n"
                "   Applied in High Court or Sessions Court before arrest.\n"
                "2. Post-arrest bail — Section 497 CrPC\n"
                "   Bailable offences: bail is a right, police must grant.\n"
                "   Non-bailable offences: court discretion.\n"
                "Grounds for granting bail:\n"
                "  - Accused not likely to flee\n"
                "  - No risk of tampering evidence\n"
                "  - Illness or medical emergency\n"
                "  - Long detention without trial\n"
                "Bail NOT granted for offences punishable by death or life imprisonment."
            ),
            metadata={
                "source_name": "Code of Criminal Procedure 1898",
                "source_file": "crpc_bail.txt",
                "law_type": "procedure",
                "section": "Bail Provisions Section 497-498",
                "chapter": "Chapter XXXIX", "article": "",
                "page_number": 1, "language": "en",
            }
        ),
    ]

    all_docs.extend(supplementary)
    logger.info(f"Added {len(supplementary)} supplementary service documents")

    if not all_docs:
        logger.error("No documents to index. Aborting.")
        sys.exit(1)

    # Chunk
    chunker = LegalChunker()
    chunks = chunker.chunk_documents(all_docs)
    print_chunk_stats(chunks)

    # Save chunks to disk (for inspection/debugging)
    cfg = get_settings()
    chunks_dir = Path(cfg.data_sources.chunks_dir)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    import json
    with open(chunks_dir / "chunks_manifest.json", "w") as f:
        manifest = [
            {
                "chunk_id": c.metadata.get("chunk_id", ""),
                "source_name": c.metadata.get("source_name", ""),
                "section": c.metadata.get("section", ""),
                "char_count": len(c.page_content),
            }
            for c in chunks
        ]
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    logger.info(f"Chunk manifest saved to {chunks_dir}/chunks_manifest.json")

    # Build vector store
    store = VectorStore()
    store.build(chunks)
    store.save()
    logger.success(f"Index built and saved. Total: {store.total_documents} chunks.")
    
def main():
    parser = argparse.ArgumentParser(description="Ingest Pakistani legal documents")
    parser.add_argument("--pdf-only",    action="store_true", help="Only process PDFs")
    parser.add_argument("--scrape-only", action="store_true", help="Only scrape web")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip web scraping, use cached")
    args = parser.parse_args()

    cfg = get_settings()
    all_docs = []

    # PDFs
    if not args.scrape_only:
        pdf_docs = ingest_pdfs(cfg.data_sources.pdf_dir)
        logger.info(f"PDF documents: {len(pdf_docs)} pages")
        all_docs.extend(pdf_docs)

    # Web
    if not args.pdf_only:
        web_docs = ingest_web(cfg.data_sources.scraped_dir, skip_scrape=args.skip_scrape)
        logger.info(f"Web documents: {len(web_docs)} pages")
        all_docs.extend(web_docs)

    logger.info(f"Total raw documents: {len(all_docs)}")

    # Build index
    build_index(all_docs)

    logger.success(
        "\n" + "="*50 +
        "\nIngestion complete!\n"
        "Run the API:       uvicorn src.api.main:app --reload\n"
        "Run the chatbot:   streamlit run streamlit_app/app.py\n" +
        "="*50
    )


if __name__ == "__main__":
    main()
