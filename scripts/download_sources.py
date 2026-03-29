"""
scripts/download_sources.py

Automated download of publicly available Pakistani legal documents
from official government and law repositories.

IMPORTANT: Only downloads from official government domains and
open legal repositories. Respects copyright and terms of service.

Usage:
  python scripts/download_sources.py
  python scripts/download_sources.py --list    # show all sources
  python scripts/download_sources.py --source ppc  # download specific source
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Official PDF sources ───────────────────────────────────────────────────
# All links point to official .gov.pk or trusted legal repositories

OFFICIAL_PDF_SOURCES = [
    {
        "id": "ppc",
        "name": "Pakistan Penal Code 1860",
        "filename": "ppc_1860.pdf",
        "law_type": "criminal",
        "urls": [
            # Try multiple mirrors — use first that works
            "https://molaw.gov.pk/filemanager/Pakistan_Penal_Code_1860.pdf",
            "https://pakistancode.gov.pk/downloads/ppc.pdf",
        ],
        "note": "If download fails, get from: https://molaw.gov.pk",
    },
    {
        "id": "peca",
        "name": "Prevention of Electronic Crimes Act 2016",
        "filename": "peca_2016.pdf",
        "law_type": "cyber",
        "urls": [
            "https://moitt.gov.pk/SiteImage/Misc/files/PECA.pdf",
            "https://fia.gov.pk/files/peca2016.pdf",
        ],
        "note": "Also at: https://na.gov.pk (National Assembly website)",
    },
    {
        "id": "constitution",
        "name": "Constitution of Pakistan 1973",
        "filename": "constitution_1973.pdf",
        "law_type": "constitutional",
        "urls": [
            "https://molaw.gov.pk/filemanager/Constitution_of_Pakistan.pdf",
            "https://pakistancode.gov.pk/downloads/constitution.pdf",
        ],
        "note": "Official text at: https://na.gov.pk/constitution",
    },
    {
        "id": "crpc",
        "name": "Code of Criminal Procedure 1898",
        "filename": "crpc.pdf",
        "law_type": "procedure",
        "urls": [
            "https://molaw.gov.pk/filemanager/Code_of_Criminal_Procedure_1898.pdf",
        ],
        "note": "Also searchable at: https://pakistancode.gov.pk",
    },
]

# ── Manual download instructions ──────────────────────────────────────────
# For sources that require browser/login, print clear instructions

MANUAL_DOWNLOAD_INSTRUCTIONS = """
╔══════════════════════════════════════════════════════════════════╗
║           MANUAL DOWNLOAD INSTRUCTIONS                          ║
║      (for sources requiring browser navigation)                 ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  1. NADRA Documentation                                          ║
║     URL: https://nadra.gov.pk/services/                          ║
║     Save as: data/raw/pdfs/nadra_procedures.pdf                  ║
║                                                                  ║
║  2. Punjab Driving License Procedure                             ║
║     URL: https://punjabpolice.gov.pk/driving-license             ║
║     Save as: data/raw/pdfs/driving_license_punjab.pdf            ║
║                                                                  ║
║  3. Punjab Service Manual                                        ║
║     URL: https://punjab.gov.pk/services                          ║
║     Save as: data/raw/pdfs/punjab_service_manual.pdf             ║
║                                                                  ║
║  4. FIA Cybercrime Laws                                           ║
║     URL: https://fia.gov.pk/en/cyber-crime-circle                ║
║     Save as: data/raw/pdfs/fia_cybercrime.pdf                    ║
║                                                                  ║
║  5. Pakistan Code (all laws)                                      ║
║     URL: https://pakistancode.gov.pk                             ║
║     Browse and download relevant acts as needed.                 ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""


class LegalDocumentDownloader:
    """Downloads official Pakistani legal PDFs with retry logic."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; PakistanLawAssistant/1.0; "
            "+https://github.com/yourusername/pakistan-law-assistant)"
        )
    }

    def __init__(self, output_dir: str = "data/raw/pdfs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download_all(self) -> dict[str, bool]:
        """Download all configured PDF sources. Returns {filename: success}."""
        results = {}
        for source in OFFICIAL_PDF_SOURCES:
            success = self.download_source(source)
            results[source["filename"]] = success
            time.sleep(1)  # polite delay

        self._print_summary(results)
        print(MANUAL_DOWNLOAD_INSTRUCTIONS)
        return results

    def download_source(self, source: dict) -> bool:
        """Try each URL for a source until one succeeds."""
        output_path = self.output_dir / source["filename"]

        if output_path.exists():
            logger.info(f"Already downloaded: {source['filename']} (skipping)")
            return True

        logger.info(f"Downloading: {source['name']}...")

        for url in source["urls"]:
            try:
                response = requests.get(
                    url,
                    headers=self.HEADERS,
                    timeout=30,
                    stream=True,
                )
                response.raise_for_status()

                # Verify it's actually a PDF
                content_type = response.headers.get("Content-Type", "")
                if "pdf" not in content_type and "octet-stream" not in content_type:
                    logger.warning(f"Unexpected content type from {url}: {content_type}")
                    continue

                # Save
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                size_mb = output_path.stat().st_size / 1024 / 1024
                logger.success(f"✓ {source['filename']} ({size_mb:.1f} MB)")
                return True

            except Exception as e:
                logger.warning(f"  Failed {url}: {e}")

        logger.error(
            f"✗ Could not download {source['name']}.\n"
            f"  Note: {source.get('note', '')}\n"
            f"  Save manually to: {output_path}"
        )
        return False

    def _print_summary(self, results: dict[str, bool]):
        success = sum(results.values())
        total = len(results)
        print(f"\n{'='*50}")
        print(f"Download summary: {success}/{total} files")
        for fname, ok in results.items():
            status = "✓" if ok else "✗ (manual download needed)"
            print(f"  {status} {fname}")
        print("="*50)


def create_demo_data():
    """
    Create minimal demo text files for testing WITHOUT real PDFs.
    Useful for CI/CD and development without actual legal documents.
    """
    from langchain.schema import Document
    from src.ingestion.chunker import LegalChunker
    from src.retrieval.vector_store import VectorStore

    demo_docs = [
        Document(
            page_content=(
                "Section 302. Punishment of Qatl-i-amd.\n"
                "Whoever commits qatl-i-amd shall be punished with death as tazir "
                "or imprisonment for life as tazir, depending on circumstances."
            ),
            metadata={
                "source_name": "Pakistan Penal Code 1860 (DEMO)",
                "source_file": "demo_ppc.txt",
                "law_type": "criminal",
                "section": "Section 302",
                "chapter": "Chapter XVI",
                "article": "",
                "page_number": 1,
                "language": "en",
            }
        ),
        Document(
            page_content=(
                "Section 20 PECA 2016. Offences against dignity.\n"
                "Whoever intentionally and publicly exhibits or displays or transmits "
                "any false information through any information system shall be "
                "punished with imprisonment up to three years or fine up to "
                "one million rupees or with both."
            ),
            metadata={
                "source_name": "Prevention of Electronic Crimes Act 2016 (DEMO)",
                "source_file": "demo_peca.txt",
                "law_type": "cyber",
                "section": "Section 20",
                "chapter": "",
                "article": "",
                "page_number": 1,
                "language": "en",
            }
        ),
        Document(
            page_content=(
                "Domicile Certificate — Punjab Government.\n"
                "Required documents: (1) CNIC copy, (2) Proof of residence "
                "(utility bill), (3) Affidavit on Rs.50 stamp paper, "
                "(4) Two passport photographs, (5) Filled application form.\n"
                "Apply at: District Headquarters or Tehsil Office."
            ),
            metadata={
                "source_name": "Punjab Government Service Manual (DEMO)",
                "source_file": "demo_punjab.txt",
                "law_type": "service",
                "section": "Domicile Certificate Procedure",
                "chapter": "",
                "article": "",
                "page_number": 1,
                "language": "en",
            }
        ),
        Document(
            page_content=(
                "FIR Registration Procedure — Code of Criminal Procedure Section 154.\n"
                "Step 1: Visit the nearest police station.\n"
                "Step 2: Report the offence to the Station House Officer (SHO).\n"
                "Step 3: Provide written complaint details.\n"
                "Step 4: The SHO must register the FIR within 24 hours.\n"
                "Step 5: Obtain a copy of the registered FIR free of charge."
            ),
            metadata={
                "source_name": "Code of Criminal Procedure (DEMO)",
                "source_file": "demo_crpc.txt",
                "law_type": "procedure",
                "section": "Section 154 — FIR Registration",
                "chapter": "",
                "article": "",
                "page_number": 1,
                "language": "en",
            }
        ),

        Document(
            page_content=(
                "Domicile Certificate Requirements — Punjab Government.\n"
                "To obtain a domicile certificate in Punjab, the following "
                "documents are required:\n"
                "1. Original CNIC (Computerized National Identity Card)\n"
                "2. Copy of CNIC of applicant\n"
                "3. Proof of residence: utility bill (electricity, gas, or water) "
                "not older than 3 months, OR property ownership documents\n"
                "4. Affidavit on Rs. 50 stamp paper stating you are a permanent "
                "resident of Punjab\n"
                "5. Two recent passport-size photographs\n"
                "6. Filled application form available at Tehsil or District office\n"
                "7. B-Form (for minors under 18 years)\n"
                "The application is submitted at the local Tehsil Municipal "
                "Administration (TMA) office or District Headquarters. "
                "Processing time is typically 7-15 working days. "
                "No fee is charged for domicile certificate in Punjab."
            ),
            metadata={
                "source_name": "Punjab Government Service Manual",
                "source_file": "punjab_service_manual.txt",
                "law_type": "service",
                "section": "Domicile Certificate Procedure",
                "chapter": "",
                "article": "",
                "page_number": 1,
                "language": "en",
            }
        ),
        Document(
            page_content=(
                "Driving License Application Procedure — Punjab Police.\n"
                "To apply for a new driving license in Punjab:\n"
                "Step 1: Visit the nearest Driving License Authority (DLA) office "
                "or apply online at dlims.punjab.gov.pk\n"
                "Step 2: Required documents:\n"
                "  - Original CNIC\n"
                "  - Medical certificate from a registered doctor\n"
                "  - Passport size photographs (4 copies)\n"
                "  - Token fee payment receipt\n"
                "Step 3: Pass the written test (theory test about traffic rules)\n"
                "Step 4: Pass the practical driving test\n"
                "Step 5: Collect your license after 1-2 weeks\n"
                "Fee: Rs. 750 for motorcycle, Rs. 1500 for car license.\n"
                "Learner license is issued first, valid for 6 months. "
                "Minimum age: 18 years for car, 16 years for motorcycle. "
                "Online portal: https://dlims.punjab.gov.pk"
            ),
            metadata={
                "source_name": "Punjab Police Driving License Procedure",
                "source_file": "driving_license_punjab.txt",
                "law_type": "service",
                "section": "Driving License Application",
                "chapter": "",
                "article": "",
                "page_number": 1,
                "language": "en",
            }
        ),
        Document(
            page_content=(
                "FIR Registration Procedure — Code of Criminal Procedure Section 154.\n"
                "An FIR (First Information Report) is registered under Section 154 "
                "of the Code of Criminal Procedure (CrPC) 1898.\n"
                "Steps to register an FIR in Pakistan:\n"
                "Step 1: Visit the nearest police station in whose jurisdiction "
                "the crime occurred.\n"
                "Step 2: Meet the Station House Officer (SHO) or duty officer.\n"
                "Step 3: Provide a written or oral complaint describing:\n"
                "  - Date, time and place of incident\n"
                "  - Description of the offence\n"
                "  - Names of accused if known\n"
                "  - Names of witnesses if any\n"
                "Step 4: The SHO is legally bound to register FIR for cognizable "
                "offences. Refusal to register FIR is punishable under law.\n"
                "Step 5: Receive a free copy of the FIR — this is your legal right.\n"
                "Step 6: If police refuse to register FIR, file complaint with:\n"
                "  - DSP (Deputy Superintendent of Police)\n"
                "  - SSP (Senior Superintendent of Police)\n"
                "  - Judicial Magistrate under Section 22-A CrPC\n"
                "Important: FIR is only for cognizable offences (serious crimes). "
                "For non-cognizable offences, a complaint application is filed."
            ),
            metadata={
                "source_name": "Code of Criminal Procedure 1898",
                "source_file": "crpc.txt",
                "law_type": "procedure",
                "section": "Section 154 — FIR Registration",
                "chapter": "Chapter XII",
                "article": "",
                "page_number": 1,
                "language": "en",
            }
        ),
        Document(
            page_content=(
                "CNIC Renewal Procedure — NADRA.\n"
                "To renew your CNIC (Computerized National Identity Card) from NADRA:\n"
                "Step 1: Visit nearest NADRA Registration Centre (NRC) or "
                "apply online at id.nadra.gov.pk\n"
                "Step 2: Required documents for renewal:\n"
                "  - Old/expired CNIC\n"
                "  - If address changed: proof of new address (utility bill)\n"
                "  - If name changed: court order or marriage certificate\n"
                "Step 3: Biometric verification (fingerprints and photo)\n"
                "Step 4: Pay the fee:\n"
                "  - Normal delivery (30 days): Rs. 750\n"
                "  - Urgent delivery (7 days): Rs. 1500\n"
                "  - Executive delivery (2 days): Rs. 2500\n"
                "Step 5: Receive SMS confirmation with tracking number\n"
                "Step 6: Collect CNIC from NADRA office or receive by courier\n"
                "CNIC is valid for 10 years. Renewal must be done before expiry. "
                "NADRA helpline: 051-111-786-100"
            ),
            metadata={
                "source_name": "NADRA Documentation Procedures",
                "source_file": "nadra_procedures.txt",
                "law_type": "service",
                "section": "CNIC Renewal Procedure",
                "chapter": "",
                "article": "",
                "page_number": 2,
                "language": "en",
            }
        ),
        Document(
            page_content=(
                "Bail Provisions in Pakistan — Code of Criminal Procedure.\n"
                "Bail is the temporary release of an accused person awaiting trial.\n"
                "Types of bail in Pakistan:\n"
                "1. Pre-arrest bail (Anticipatory bail) — Section 498 CrPC\n"
                "   Granted before arrest to protect from unjust arrest.\n"
                "   Applied for in High Court or Sessions Court.\n"
                "2. Post-arrest bail — Section 497 CrPC\n"
                "   Granted after arrest. Two categories:\n"
                "   a) Bailable offences: Bail is a right, police must grant it.\n"
                "   b) Non-bailable offences: Bail is discretionary by court.\n"
                "Grounds for granting bail:\n"
                "  - Accused is not likely to flee\n"
                "  - No risk of tampering with evidence\n"
                "  - Accused is not a repeat offender\n"
                "  - Illness or medical emergency\n"
                "  - Long period of incarceration without trial\n"
                "Bail cannot be granted for:\n"
                "  - Offences punishable by death\n"
                "  - Offences punishable by life imprisonment\n"
                "  - Previous convictions for similar offence\n"
                "Surety: A person who guarantees the accused will appear in court."
            ),
            metadata={
                "source_name": "Code of Criminal Procedure 1898",
                "source_file": "crpc.txt",
                "law_type": "procedure",
                "section": "Bail Provisions — Section 497-498",
                "chapter": "Chapter XXXIX",
                "article": "",
                "page_number": 1,
                "language": "en",
            }
        ),



        Document(
            page_content=(
                "Article 9. Security of person.\n"
                "No person shall be deprived of life or liberty save in accordance "
                "with law.\n\n"
                "Article 25. Equality of citizens.\n"
                "All citizens are equal before law and are entitled to equal protection "
                "of law. There shall be no discrimination on the basis of sex."
            ),
            metadata={
                "source_name": "Constitution of Pakistan 1973 (DEMO)",
                "source_file": "demo_constitution.txt",
                "law_type": "constitutional",
                "section": "Fundamental Rights",
                "chapter": "Chapter 1 — Fundamental Rights",
                "article": "Article 9, Article 25",
                "page_number": 1,
                "language": "en",
            }
        ),
    ]

    logger.info("Creating demo index from sample documents...")
    chunker = LegalChunker()
    chunks = chunker.chunk_documents(demo_docs)
    logger.info(f"Created {len(chunks)} demo chunks")

    store = VectorStore()
    store.build(chunks)
    store.save()
    logger.success(
        f"Demo index built: {store.total_documents} chunks.\n"
        "You can now run the chatbot with demo data!\n"
        "  uvicorn src.api.main:app --reload\n"
        "  streamlit run streamlit_app/app.py"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Pakistani legal documents")
    parser.add_argument("--list", action="store_true", help="List all sources")
    parser.add_argument("--source", type=str, help="Download specific source by ID")
    parser.add_argument("--demo", action="store_true",
                        help="Build demo index without real PDFs (for testing)")
    args = parser.parse_args()

    if args.demo:
        create_demo_data()
        sys.exit(0)

    if args.list:
        print("\nConfigured sources:")
        for s in OFFICIAL_PDF_SOURCES:
            print(f"  [{s['id']}] {s['name']} → {s['filename']}")
        print(MANUAL_DOWNLOAD_INSTRUCTIONS)
        sys.exit(0)

    downloader = LegalDocumentDownloader()

    if args.source:
        matching = [s for s in OFFICIAL_PDF_SOURCES if s["id"] == args.source]
        if not matching:
            print(f"Unknown source: {args.source}")
            sys.exit(1)
        downloader.download_source(matching[0])
    else:
        downloader.download_all()
