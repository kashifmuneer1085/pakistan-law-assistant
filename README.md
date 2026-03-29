# 🇵🇰 Pakistan Law & Government Assistant

A production-grade **Retrieval-Augmented Generation (RAG)** chatbot that answers questions about Pakistani laws, government services, and legal regulations. Built with LangChain, FAISS, Sentence Transformers, and Streamlit.

## Features
- Hybrid search (vector + BM25 keyword)
- Multilingual support (English + Urdu)
- Source citations with section/article numbers
- Legal document summarization
- Government procedure walkthroughs
- Upload new documents at runtime
- Anti-hallucination safeguards

## Quick Start
```bash
pip install -r requirements.txt
cp configs/config.example.yaml configs/config.yaml  # fill in your LLM API key
python scripts/ingest_documents.py
streamlit run streamlit_app/app.py
```

## Data Sources
- Pakistan Penal Code (PPC) 1860
- Prevention of Electronic Crimes Act (PECA) 2016
- FIA Cyber Crime laws
- Punjab Government Service Manuals
- NADRA documentation
- Punjab Police driving license procedures

## Architecture
See `docs/architecture.md` for the full system diagram.
