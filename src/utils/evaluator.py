"""
src/utils/evaluator.py

Evaluation of the RAG pipeline using:
  1. RAGAS metrics: faithfulness, answer_relevancy, context_precision, context_recall
  2. Custom legal accuracy tests
  3. Retrieval metrics: hit rate, MRR (Mean Reciprocal Rank)

Usage:
  python -m src.utils.evaluator

The evaluator uses a golden test set of Pakistani law Q&A pairs with known correct answers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

# ── Golden test set ────────────────────────────────────────────────────────

GOLDEN_QA_PAIRS = [
    {
        "question": "What is the punishment for murder under PPC?",
        "expected_keywords": ["Section 302", "death", "life imprisonment", "PPC"],
        "expected_sources": ["Pakistan Penal Code"],
        "law_type": "criminal",
    },
    {
        "question": "What is the punishment for cybercrime harassment in Pakistan?",
        "expected_keywords": ["PECA", "Section 20", "harassment", "imprisonment", "fine"],
        "expected_sources": ["Prevention of Electronic Crimes Act"],
        "law_type": "cyber",
    },
    {
        "question": "What documents are required for CNIC?",
        "expected_keywords": ["NADRA", "birth certificate", "B Form", "identity"],
        "expected_sources": ["NADRA"],
        "law_type": "service",
    },
    {
        "question": "How to register an FIR in Pakistan?",
        "expected_keywords": ["police station", "Section 154 CrPC", "SHO", "complaint"],
        "expected_sources": ["Code of Criminal Procedure"],
        "law_type": "procedure",
    },
    {
        "question": "What are the fundamental rights in Pakistan's Constitution?",
        "expected_keywords": ["Article 9", "Article 25", "equality", "freedom"],
        "expected_sources": ["Constitution of Pakistan"],
        "law_type": "constitutional",
    },
]


# ── Evaluation result ──────────────────────────────────────────────────────

@dataclass
class EvalResult:
    question: str
    answer: str
    retrieved_sources: list[str]
    keyword_hits: int
    keyword_total: int
    source_hit: bool
    has_citation: bool
    is_grounded: bool    # answer contains [Source N] references
    notes: str = ""

    @property
    def keyword_score(self) -> float:
        return self.keyword_hits / max(self.keyword_total, 1)


# ── Evaluator ─────────────────────────────────────────────────────────────

class LegalRAGEvaluator:
    """
    Evaluates the full RAG pipeline against golden Q&A pairs.
    Does NOT require RAGAS by default (avoids OpenAI dependency at eval time).
    """

    def __init__(self, retriever=None, generator=None):
        self.retriever = retriever
        self.generator = generator

    def run_basic_eval(self) -> dict[str, Any]:
        """
        Run evaluation against the golden test set.
        Returns a dict of metrics.
        """
        if not self.retriever or not self.generator:
            raise RuntimeError("Retriever and generator must be provided.")

        results: list[EvalResult] = []

        for pair in GOLDEN_QA_PAIRS:
            question = pair["question"]
            logger.info(f"Evaluating: {question[:60]}...")

            retrieval = self.retriever.retrieve(question, top_k=3)
            response = self.generator.generate(question, retrieval)

            retrieved_sources = [
                doc.metadata.get("source_name", "")
                for doc, _ in retrieval.documents
            ]

            # Check keyword hits
            answer_lower = response.answer.lower()
            keyword_hits = sum(
                1 for kw in pair["expected_keywords"]
                if kw.lower() in answer_lower
            )

            # Check source hit
            source_hit = any(
                exp_src.lower() in src.lower()
                for exp_src in pair["expected_sources"]
                for src in retrieved_sources
            )

            # Check groundedness (has [Source N] citations)
            import re
            has_citation = bool(re.search(r"\[Source\s+\d+\]", response.answer))

            # Check if answer seems grounded (doesn't say "I don't know" when sources exist)
            is_grounded = retrieval.found and response.found

            result = EvalResult(
                question=question,
                answer=response.answer,
                retrieved_sources=retrieved_sources,
                keyword_hits=keyword_hits,
                keyword_total=len(pair["expected_keywords"]),
                source_hit=source_hit,
                has_citation=has_citation,
                is_grounded=is_grounded,
            )
            results.append(result)
            self._print_result(result)

        return self._aggregate_metrics(results)

    def run_ragas_eval(self, openai_api_key: str) -> dict:
        """
        Run RAGAS evaluation (requires OpenAI API key for LLM-based metrics).
        Metrics: faithfulness, answer_relevancy, context_precision, context_recall.
        """
        try:
            from ragas import evaluate
            from ragas.metrics import (
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            )
            from datasets import Dataset
        except ImportError:
            raise ImportError("Install ragas and datasets: pip install ragas datasets")

        import os
        os.environ["OPENAI_API_KEY"] = openai_api_key

        data = {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],
        }

        for pair in GOLDEN_QA_PAIRS:
            retrieval = self.retriever.retrieve(pair["question"])
            response = self.generator.generate(pair["question"], retrieval)
            contexts = [doc.page_content for doc, _ in retrieval.documents]

            data["question"].append(pair["question"])
            data["answer"].append(response.answer)
            data["contexts"].append(contexts)
            # Simple ground truth: the expected keywords joined
            data["ground_truth"].append(", ".join(pair["expected_keywords"]))

        dataset = Dataset.from_dict(data)
        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        )

        logger.info(f"RAGAS Results: {result}")
        return result

    # ── Helpers ────────────────────────────────────────────────────────

    def _print_result(self, r: EvalResult):
        print(f"\nQ: {r.question[:70]}")
        print(f"  Keyword score : {r.keyword_score:.0%} ({r.keyword_hits}/{r.keyword_total})")
        print(f"  Source hit    : {'✓' if r.source_hit else '✗'}")
        print(f"  Has citation  : {'✓' if r.has_citation else '✗'}")
        print(f"  Is grounded   : {'✓' if r.is_grounded else '✗'}")

    def _aggregate_metrics(self, results: list[EvalResult]) -> dict:
        n = len(results)
        metrics = {
            "total_questions": n,
            "avg_keyword_score": sum(r.keyword_score for r in results) / n,
            "source_hit_rate": sum(r.source_hit for r in results) / n,
            "citation_rate": sum(r.has_citation for r in results) / n,
            "groundedness_rate": sum(r.is_grounded for r in results) / n,
            "perfect_answers": sum(
                r.keyword_score == 1.0 and r.source_hit and r.has_citation
                for r in results
            ),
        }

        print("\n" + "="*50)
        print("EVALUATION SUMMARY")
        print("="*50)
        for k, v in metrics.items():
            if isinstance(v, float):
                print(f"  {k:<25}: {v:.1%}")
            else:
                print(f"  {k:<25}: {v}")
        print("="*50)
        return metrics

    def evaluate_retrieval_only(self) -> dict:
        """
        Measure retrieval quality (hit rate, MRR) without running generation.
        Useful for tuning retrieval parameters without LLM cost.
        """
        hit_rates = []
        mrr_scores = []

        for pair in GOLDEN_QA_PAIRS:
            retrieval = self.retriever.retrieve(pair["question"], top_k=5)
            sources = [
                doc.metadata.get("source_name", "").lower()
                for doc, _ in retrieval.documents
            ]
            expected = [s.lower() for s in pair["expected_sources"]]

            # Hit rate: at least one expected source in top-k
            hit = any(
                any(exp in src for exp in expected)
                for src in sources
            )
            hit_rates.append(1.0 if hit else 0.0)

            # MRR: reciprocal rank of first relevant hit
            rr = 0.0
            for rank, src in enumerate(sources, 1):
                if any(exp in src for exp in expected):
                    rr = 1.0 / rank
                    break
            mrr_scores.append(rr)

        return {
            "hit_rate@5": sum(hit_rates) / len(hit_rates),
            "mrr@5": sum(mrr_scores) / len(mrr_scores),
        }
