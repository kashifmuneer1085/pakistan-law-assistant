"""
src/ingestion/web_scraper.py

Scrapes official Pakistani government and law websites.
Targeted scrapers for: punjab.gov.pk, nadra.gov.pk, fia.gov.pk, molaw.gov.pk

Usage:
    scraper = PakistanLawScraper()
    docs = scraper.scrape_url("https://www.fia.gov.pk/cyber-crime-laws")
    docs = scraper.scrape_all_sources()
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from loguru import logger


# ── Scraped document model ─────────────────────────────────────────────────

@dataclass
class ScrapedDocument:
    text: str
    url: str
    title: str
    source_name: str
    law_type: str
    section: str = ""
    language: str = "en"

    def to_langchain_doc(self):
        from langchain.schema import Document
        return Document(
            page_content=self.text,
            metadata={
                "source_url": self.url,
                "source_name": self.source_name,
                "title": self.title,
                "law_type": self.law_type,
                "section": self.section,
                "language": self.language,
                "source_file": "web",
            }
        )


# ── Official Pakistani government sources ─────────────────────────────────

OFFICIAL_SOURCES = [
    {
        "url": "https://molaw.gov.pk",
        "source_name": "Ministry of Law and Justice",
        "law_type": "legislation",
        "crawl_paths": ["/acts", "/ordinances", "/rules"],
    },
    {
        "url": "https://www.fia.gov.pk",
        "source_name": "Federal Investigation Agency",
        "law_type": "cyber",
        "crawl_paths": ["/cyber-crime", "/laws"],
    },
    {
        "url": "https://nadra.gov.pk",
        "source_name": "NADRA",
        "law_type": "service",
        "crawl_paths": ["/services", "/forms", "/faqs"],
    },
    {
        "url": "https://punjabpolice.gov.pk",
        "source_name": "Punjab Police",
        "law_type": "procedure",
        "crawl_paths": ["/services", "/citizen-services"],
    },
    {
        "url": "https://punjab.gov.pk",
        "source_name": "Government of Punjab",
        "law_type": "service",
        "crawl_paths": ["/services", "/departments"],
    },
]

# HTML tags that typically contain navigation / noise (skip them)
NOISE_SELECTORS = [
    "nav", "header", "footer", "script", "style",
    ".menu", ".navigation", ".sidebar", ".advertisement",
    "#cookie-notice", ".social-links",
]


# ── Main scraper class ─────────────────────────────────────────────────────

class PakistanLawScraper:
    """
    Polite, respectful scraper for official Pakistani legal/government websites.
    - Respects robots.txt implicitly (only scrapes official .gov.pk domains)
    - 1-second delay between requests
    - User-agent identifies the bot clearly
    """

    HEADERS = {
        "User-Agent": (
            "PakistanLawAssistant/1.0 (Educational RAG Project; "
            "contact: your_email@example.com)"
        ),
        "Accept-Language": "en-US,en;q=0.9,ur;q=0.8",
    }

    def __init__(self, delay: float = 1.0, timeout: int = 15):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ── Core scraping methods ───────────────────────────────────────────

    def fetch_page(self, url: str) -> str | None:
        """Fetch raw HTML for a URL. Returns None on failure."""
        try:
            time.sleep(self.delay)
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    def parse_page(
        self,
        html: str,
        url: str,
        source_name: str,
        law_type: str,
    ) -> ScrapedDocument | None:
        """Parse HTML into a clean ScrapedDocument."""
        soup = BeautifulSoup(html, "lxml")

        # Remove noise elements
        for selector in NOISE_SELECTORS:
            for tag in soup.select(selector):
                tag.decompose()

        # Extract title
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
        elif h1 := soup.find("h1"):
            title = h1.get_text(strip=True)

        # Try to find main content area
        content = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id=re.compile(r"content|main", re.I))
            or soup.find(class_=re.compile(r"content|main|body", re.I))
            or soup.body
        )

        if not content:
            return None

        text = content.get_text(separator="\n", strip=True)
        text = self._clean_text(text)

        if len(text) < 100:     # skip near-empty pages
            return None

        # Detect section headers within content
        section = self._detect_section(text)

        return ScrapedDocument(
            text=text,
            url=url,
            title=title,
            source_name=source_name,
            law_type=law_type,
            section=section,
        )

    def scrape_url(
        self,
        url: str,
        source_name: str = "",
        law_type: str = "general",
    ) -> ScrapedDocument | None:
        """Scrape a single URL and return a ScrapedDocument."""
        html = self.fetch_page(url)
        if not html:
            return None

        source_name = source_name or urlparse(url).netloc
        return self.parse_page(html, url, source_name, law_type)

    def scrape_site(
        self,
        base_url: str,
        source_name: str,
        law_type: str,
        crawl_paths: list[str],
        max_pages: int = 50,
    ) -> list[ScrapedDocument]:
        """
        Crawl a site by following known paths + same-domain links.

        Args:
            base_url:     Root URL of the site.
            source_name:  Human-readable source name.
            law_type:     Category tag.
            crawl_paths:  Known sub-paths to start from.
            max_pages:    Safety limit on pages crawled.

        Returns:
            List of ScrapedDocuments.
        """
        visited: set[str] = set()
        queue: list[str] = [urljoin(base_url, p) for p in crawl_paths]
        docs: list[ScrapedDocument] = []
        domain = urlparse(base_url).netloc

        while queue and len(visited) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            logger.info(f"Scraping: {url}")
            html = self.fetch_page(url)
            if not html:
                continue

            doc = self.parse_page(html, url, source_name, law_type)
            if doc:
                docs.append(doc)

            # Discover same-domain links
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = urljoin(url, a["href"])
                parsed = urlparse(href)
                if (
                    parsed.netloc == domain
                    and href not in visited
                    and not href.endswith((".pdf", ".jpg", ".png", ".zip"))
                ):
                    queue.append(href)

        logger.success(f"Scraped {len(docs)} pages from {base_url}")
        return docs

    def scrape_all_sources(self) -> list[ScrapedDocument]:
        """Scrape all predefined official sources."""
        all_docs: list[ScrapedDocument] = []
        for source in OFFICIAL_SOURCES:
            docs = self.scrape_site(
                base_url=source["url"],
                source_name=source["source_name"],
                law_type=source["law_type"],
                crawl_paths=source["crawl_paths"],
            )
            all_docs.extend(docs)
        logger.success(f"Total scraped: {len(all_docs)} pages")
        return all_docs

    def save_scraped(
        self,
        docs: list[ScrapedDocument],
        output_dir: str | Path,
    ) -> None:
        """Save scraped documents as JSON files for re-use."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, doc in enumerate(docs):
            filename = output_dir / f"scraped_{i:04d}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "text": doc.text,
                        "url": doc.url,
                        "title": doc.title,
                        "source_name": doc.source_name,
                        "law_type": doc.law_type,
                        "section": doc.section,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        logger.success(f"Saved {len(docs)} scraped docs to {output_dir}")

    def load_scraped(self, scraped_dir: str | Path) -> list[ScrapedDocument]:
        """Load previously saved scraped documents from JSON files."""
        scraped_dir = Path(scraped_dir)
        docs = []
        for json_file in sorted(scraped_dir.glob("scraped_*.json")):
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            docs.append(ScrapedDocument(**data))
        logger.info(f"Loaded {len(docs)} scraped docs from {scraped_dir}")
        return docs

    # ── Helpers ─────────────────────────────────────────────────────────

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _detect_section(self, text: str) -> str:
        for line in text.split("\n")[:10]:
            line = line.strip()
            if re.match(r"(Section|Article|Clause)\s+\d+", line, re.IGNORECASE):
                return line[:80]
        return ""
