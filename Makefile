# Pakistan Law Assistant — Makefile
# Usage: make <target>

.PHONY: help install demo ingest api ui test eval clean

help:
	@echo ""
	@echo "Pakistan Law & Government Assistant"
	@echo "===================================="
	@echo "  make install    Install all dependencies"
	@echo "  make demo       Build demo index (no real PDFs needed)"
	@echo "  make download   Download official legal PDFs"
	@echo "  make ingest     Build index from PDFs + web scraping"
	@echo "  make api        Start FastAPI backend (port 8000)"
	@echo "  make ui         Start Streamlit chatbot (port 8501)"
	@echo "  make run        Start both API + UI"
	@echo "  make test       Run test suite"
	@echo "  make eval       Evaluate RAG pipeline accuracy"
	@echo "  make clean      Remove generated index files"
	@echo ""

install:
	pip install -r requirements.txt

demo:
	python scripts/download_sources.py --demo

download:
	python scripts/download_sources.py

ingest:
	python scripts/ingest_documents.py

ingest-pdf-only:
	python scripts/ingest_documents.py --pdf-only

api:
	uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	streamlit run streamlit_app/app.py --server.port 8501

run:
	@echo "Starting API and Streamlit..."
	uvicorn src.api.main:app --host 0.0.0.0 --port 8000 & \
	streamlit run streamlit_app/app.py --server.port 8501

test:
	pytest tests/ -v --tb=short

eval:
	python -c "
from src.pipeline import PakistanLawPipeline
from src.utils.evaluator import LegalRAGEvaluator
pipeline = PakistanLawPipeline().load()
evaluator = LegalRAGEvaluator(pipeline._retriever, pipeline._generator)
evaluator.run_basic_eval()
print('\nRetrieval metrics:')
print(evaluator.evaluate_retrieval_only())
"

clean:
	rm -rf data/processed/embeddings/
	rm -rf data/processed/chunks/
	@echo "Index files removed. Run 'make ingest' to rebuild."
