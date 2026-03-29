# 🇵🇰 Pakistan Law & Government Assistant

<div align="center">

![Pakistan Law Assistant](https://img.shields.io/badge/Pakistan%20Law-Assistant-00C88C?style=for-the-badge&logo=scale&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-0.3.25-1C3C3C?style=for-the-badge&logo=chainlink&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-Llama%203.3%2070B-F55036?style=for-the-badge&logo=groq&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.41-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-gold?style=for-the-badge)

**An AI-powered legal assistant that makes Pakistani law accessible to every citizen.**

*Ask questions in English or Urdu — get grounded, cited answers from official legal documents.*

[🚀 Features](#features) • [⚡ Quick Start](#quick-start) • [🏗️ Architecture](#architecture) • [📚 Data Sources](#data-sources) • [👨‍💻 Developer](#developer)

</div>

---

## 🌟 What is this?

Pakistani citizens often struggle to understand their legal rights and government procedures. Legal documents are dense, government websites are unclear, and professional legal advice is expensive.

**Pakistan Law Assistant** solves this by providing an AI chatbot that:
- Retrieves relevant sections from **official Pakistani legal documents**
- Generates **grounded, cited answers** — no hallucinations
- Supports both **English and Urdu** queries
- Provides **step-by-step procedures** for government services

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Hybrid Search** | FAISS semantic + BM25 keyword search with RRF fusion |
| 🧠 **Groq LLM** | Llama 3.3 70B for fast, grounded answer generation |
| 📖 **Source Citations** | Every answer cites specific sections and articles |
| 🌐 **Bilingual** | Full English + Urdu support with auto-detection |
| 🛡️ **Anti-Hallucination** | 7-layer defence — never fabricates laws or sections |
| 📋 **Summarization** | Get structured summaries of any legal topic |
| 📤 **Document Upload** | Add new legal PDFs at runtime — instantly searchable |
| ⚖️ **Legal Disclaimer** | Every response carries appropriate legal warnings |

---

## 🏗️ Architecture

```
User Query (EN/UR)
       │
       ▼
┌─────────────────┐
│  Language       │  Auto-detect + translate Urdu → English
│  Detection      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Hybrid Search  │  FAISS (semantic 70%) + BM25 (keyword 30%)
│  + Reranking    │  Cross-encoder reranking → top 3 chunks
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Groq LLM       │  Llama 3.3 70B — grounded generation
│  Generation     │  Temperature=0.0 — fully deterministic
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Citation       │  Validate [Source N] references
│  Validator      │  Strip any hallucinated citations
└────────┬────────┘
         │
         ▼
   Cited Answer + Sources + Disclaimer
```

---

## 📚 Data Sources

| Document | Pages | Chunks | Type |
|---|---|---|---|
| 🏛️ Constitution of Pakistan 1973 | 222 | 526 | Constitutional |
| ⚖️ Pakistan Penal Code (PPC) 1860 | 164 | 541 | Criminal |
| 🌐 PECA 2016 | 39 | 541 | Cyber Law |
| 🔍 FIA Cybercrime Laws (Scraped) | 53 | 685 | Cyber / Criminal |
| 🪪 NADRA Ordinance 2000 | 27 | 62 | Government Service |
| **Total** | **505** | **1,814+** | |

---

## ⚡ Quick Start

### Prerequisites
- Python 3.11+
- Conda (recommended)
- Free [Groq API Key](https://console.groq.com)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/kashifmuneer1085/pakistan-law-assistant.git
cd pakistan-law-assistant

# 2. Create conda environment
conda create -n pakistan-law python=3.11 -y
conda activate pakistan-law

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
echo "GROQ_API_KEY=your_key_here" > .env

# 5. Build the knowledge index (takes ~50 mins first time)
python scripts/ingest_documents.py --skip-scrape

# 6. Start the API server (Terminal 1)
uvicorn src.api.main:app --reload --port 8000

# 7. Launch the chatbot UI (Terminal 2)
streamlit run streamlit_app/app.py
```

Open **http://localhost:8501** 🎉

---

## 🛡️ Anti-Hallucination System

This system implements 7 layers of protection against false legal information:

```
Layer 1 → Grounded system prompt (only use provided context)
Layer 2 → Temperature = 0.0 (deterministic, no creativity)
Layer 3 → Citation validator (removes hallucinated [Source N])
Layer 4 → Score threshold 0.30 (low similarity → "not found")
Layer 5 → require_sources: true (no answer without retrieval)
Layer 6 → Exact section numbers only (verbatim from context)
Layer 7 → Legal disclaimer on every response
```

---

## 📁 Project Structure

```
pakistan-law-assistant/
├── configs/
│   └── config.yaml              # All system parameters
├── data/
│   ├── raw/pdfs/                # Official legal PDFs
│   └── raw/scraped/             # Web-scraped government data
├── src/
│   ├── api/main.py              # FastAPI REST backend
│   ├── generation/generator.py  # Groq LLM + citation validator
│   ├── ingestion/               # PDF extraction + chunking
│   ├── retrieval/               # FAISS + BM25 hybrid search
│   └── utils/                   # Config, language, evaluation
├── streamlit_app/
│   └── app.py                   # Premium dark UI
├── scripts/
│   ├── ingest_documents.py      # Full pipeline ingestion
│   └── add_documents.py         # Incremental index updates
└── tests/
    └── test_pipeline.py         # 19 automated tests
```

---

## 🔌 API Endpoints

```
POST /query       → Ask a legal question
POST /summarize   → Summarize a legal topic
POST /upload      → Add new legal PDF
GET  /sources     → List indexed documents
GET  /health      → System status
```

---

## 💻 Tech Stack

```
LLM              │ Groq — Llama 3.3 70B Versatile (free tier)
Embeddings       │ intfloat/multilingual-e5-large (1024-dim, EN+UR)
Vector DB        │ FAISS with IVF indexing
Keyword Search   │ BM25 (rank-bm25)
Reranking        │ cross-encoder/ms-marco-MiniLM-L-6-v2
RAG Framework    │ LangChain 0.3.25
API              │ FastAPI + Uvicorn
Frontend         │ Streamlit 1.41
PDF Extraction   │ PyMuPDF + pdfplumber
Language         │ langdetect + deep-translator
```

---

## 🧪 Test Results

```bash
python -m pytest tests/ -v

✅ TestLegalChunker          (4 tests)
✅ TestLegalRetriever        (5 tests)
✅ TestLegalAnswerGenerator  (3 tests)
✅ TestLanguageUtils         (3 tests)
✅ TestPDFExtractor          (3 tests)
✅ TestPipelineIntegration   (1 test)

19/19 passed ── 100% pass rate
```

---

## 📊 Sample Questions

```
⚖️  What is Section 302 of Pakistan Penal Code?
🌐  What is the punishment for cybercrime in Pakistan?
🏛️  What are fundamental rights in the Constitution of Pakistan?
📋  What are the steps to register a FIR in Pakistan?
🪪  How do I get a CNIC renewal from NADRA?
🚗  How can I apply for a driving license in Punjab?

اردو میں بھی پوچھیں:
🔍  پاکستان میں سائبر کرائم کی سزا کیا ہے؟
📜  پاکستان کے آئین میں بنیادی حقوق کیا ہیں؟
```

---

## 👨‍💻 Developer

<div align="center">

**Engineer Kashif Muneer**

AI Engineer Intern @ AI4LYF

[![GitHub](https://img.shields.io/badge/GitHub-kashifmuneer1085-181717?style=for-the-badge&logo=github)](https://github.com/kashifmuneer1085)

</div>

---

## ⚠️ Disclaimer

This tool provides **general legal information only** — not legal advice. Always consult a qualified lawyer for your specific situation. Legal information may not be current or complete.

---

<div align="center">

Made with ❤️ for Pakistani citizens | Project

⭐ **Star this repo if you found it useful!**

</div>