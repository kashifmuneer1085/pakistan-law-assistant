"""
src/generation/generator.py

Grounded answer generation for Pakistani legal questions.

Anti-hallucination design:
  1. System prompt explicitly forbids fabricating laws or sections
  2. Answers must cite specific source numbers from the context block
  3. If context doesn't contain an answer, LLM must say so
  4. Temperature = 0.0 for determinism
  5. Post-generation validator checks for fabricated citations

Usage:
    generator = LegalAnswerGenerator()
    response = generator.generate(query, retrieval_result)
    print(response.answer)
    print(response.citations)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from langchain.schema import Document
from loguru import logger

from src.retrieval.retriever import RetrievalResult
from src.utils.config import get_settings


# ── Response model ─────────────────────────────────────────────────────────

@dataclass
class LegalResponse:
    """Structured response from the generator."""
    query: str
    answer: str
    citations: list[dict] = field(default_factory=list)
    disclaimer: str = ""
    language: str = "en"
    found: bool = True
    raw_context: str = ""

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "answer": self.answer,
            "citations": self.citations,
            "disclaimer": self.disclaimer,
            "language": self.language,
            "found": self.found,
        }


# ── Prompts ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a knowledgeable assistant for Pakistani law and government services.
Your role is to help citizens understand legal procedures, rights, and government services in Pakistan.

STRICT RULES — follow these at all times:

1. GROUNDING: Base your answer ONLY on the provided [Source N] context blocks.
   Do NOT use any legal knowledge from outside the provided sources.

2. CITATIONS: Every factual claim must reference a source number like [Source 1] or [Source 2].
   Place citations inline immediately after the claim they support.

3. HONESTY: If the provided sources do not contain sufficient information to answer the question,
   say clearly: "I could not find this information in the provided legal documents."
   Do NOT fabricate laws, section numbers, or procedures.

4. SECTION NUMBERS: When citing a specific law section (e.g., Section 20 of PECA 2016),
   only mention it if it appears explicitly in the source text.

5. LANGUAGE: Respond in the same language the user asked in (English or Urdu).

6. FORMAT: Structure your answer with:
   - Direct answer first (1-2 sentences)
   - Supporting details with inline citations
   - Required documents / steps (if applicable, use numbered list)
   - Any relevant penalties or timelines

7. DISCLAIMER: Always end with a note that this is general information, not legal advice."""

LEGAL_QA_TEMPLATE = """CONTEXT FROM OFFICIAL PAKISTANI LEGAL DOCUMENTS:

{context}

---

USER QUESTION: {query}

Please answer the question using ONLY the information in the context above.
Cite sources inline as [Source 1], [Source 2] etc.
If the context does not contain enough information, state that clearly."""

SUMMARIZE_TEMPLATE = """CONTEXT FROM OFFICIAL PAKISTANI LEGAL DOCUMENTS:

{context}

---

Please provide a clear, organized summary of the above legal content about: {topic}

Structure your summary with:
1. Overview (2-3 sentences)
2. Key provisions/sections
3. Penalties or consequences (if applicable)
4. Who it applies to
5. Important definitions

Cite each point with [Source N] references."""

URDU_SYSTEM_ADDITION = """
اہم: صارف نے اردو میں سوال پوچھا ہے۔ اردو میں جواب دیں۔
آسان اور سمجھ میں آنے والی زبان استعمال کریں۔
قانونی اصطلاحات کو سادہ الفاظ میں سمجھائیں۔"""


# ── Generator ─────────────────────────────────────────────────────────────

class LegalAnswerGenerator:
    """
    Generates grounded legal answers from retrieved context.
    Supports OpenAI, Anthropic, and local Mistral/Llama models.
    """

    def __init__(self, config=None):
        cfg = config or get_settings()
        self.llm_cfg = cfg.llm
        self.safety_cfg = cfg.safety
        self._llm = None

    # ── Public API ─────────────────────────────────────────────────────

    def generate(
        self,
        query: str,
        retrieval_result: RetrievalResult,
        language: str = "en",
    ) -> LegalResponse:
        """
        Generate a grounded legal answer from retrieved context.

        Args:
            query:            User question.
            retrieval_result: Output of LegalRetriever.retrieve().
            language:         "en" or "ur".

        Returns:
            LegalResponse with answer and citations.
        """
        # Handle no-results case
        if not retrieval_result.found or not retrieval_result.documents:
            return LegalResponse(
                query=query,
                answer=self.safety_cfg.out_of_scope_response,
                citations=[],
                disclaimer=self.safety_cfg.disclaimer,
                language=language,
                found=False,
            )

        context_text = retrieval_result.get_context_text()
        citations = retrieval_result.get_citations()

        # Build prompt
        user_message = LEGAL_QA_TEMPLATE.format(
            context=context_text,
            query=query,
        )

        system_msg = SYSTEM_PROMPT
        if language == "ur":
            system_msg += URDU_SYSTEM_ADDITION

        # Call LLM
        try:
            answer = self._call_llm(system_msg, user_message)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            answer = "An error occurred while generating the answer. Please try again."

        # Validate citations (anti-hallucination check)
        answer = self._validate_citations(answer, len(citations))

        return LegalResponse(
            query=query,
            answer=answer,
            citations=citations,
            disclaimer=self.safety_cfg.disclaimer,
            language=language,
            found=True,
            raw_context=context_text,
        )

    def summarize(
        self,
        topic: str,
        retrieval_result: RetrievalResult,
        language: str = "en",
    ) -> LegalResponse:
        """Generate a structured summary of a legal topic."""
        if not retrieval_result.found or not retrieval_result.documents:
            return LegalResponse(
                query=topic,
                answer="Insufficient documents found for summarization.",
                found=False,
                disclaimer=self.safety_cfg.disclaimer,
            )

        context_text = retrieval_result.get_context_text()
        user_message = SUMMARIZE_TEMPLATE.format(context=context_text, topic=topic)

        system_msg = SYSTEM_PROMPT
        if language == "ur":
            system_msg += URDU_SYSTEM_ADDITION

        try:
            answer = self._call_llm(system_msg, user_message)
        except Exception as e:
            logger.error(f"LLM summarize failed: {e}")
            answer = "Summarization failed. Please try again."

        return LegalResponse(
            query=topic,
            answer=answer,
            citations=retrieval_result.get_citations(),
            disclaimer=self.safety_cfg.disclaimer,
            language=language,
            found=True,
        )

    # ── LLM backends ───────────────────────────────────────────────────

    def _call_llm(self, system_msg: str, user_msg: str) -> str:
        provider = self.llm_cfg.provider.lower()
        if provider == "openai":
            return self._call_openai(system_msg, user_msg)
        elif provider == "anthropic":
            return self._call_anthropic(system_msg, user_msg)
        elif provider == "groq":
            return self._call_groq(system_msg, user_msg)
        elif provider == "local":
            return self._call_local(system_msg, user_msg)
    

    def _call_openai(self, system_msg: str, user_msg: str) -> str:
        from openai import OpenAI
        from src.utils.config import get_settings
        client = OpenAI(api_key=get_settings().openai_api_key)
        response = client.chat.completions.create(
            model=self.llm_cfg.model,
            temperature=self.llm_cfg.temperature,
            max_tokens=self.llm_cfg.max_tokens,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, system_msg: str, user_msg: str) -> str:
        import anthropic
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=self.llm_cfg.model,
            max_tokens=self.llm_cfg.max_tokens,
            system=system_msg,
            messages=[{"role": "user", "content": user_msg}],
        )
        return message.content[0].text.strip()
    
    def _call_groq(self, system_msg: str, user_msg: str) -> str:
        import os
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model=self.llm_cfg.model,
            temperature=self.llm_cfg.temperature,
            max_tokens=self.llm_cfg.max_tokens,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
        )
        return response.choices[0].message.content.strip()

    def _call_local(self, system_msg: str, user_msg: str) -> str:
        """
        Call a local GGUF model via llama-cpp-python.
        Install: pip install llama-cpp-python
        Model:   Mistral-7B-Instruct-v0.2.Q4_K_M.gguf (4GB)
        """
        from llama_cpp import Llama
        if self._llm is None:
            self._llm = Llama(
                model_path=self.llm_cfg.local_model_path,
                n_ctx=4096,
                n_threads=4,
                verbose=False,
            )
        prompt = f"[INST] {system_msg}\n\n{user_msg} [/INST]"
        output = self._llm(prompt, max_tokens=self.llm_cfg.max_tokens, temperature=0.0)
        return output["choices"][0]["text"].strip()

    # ── Citation validator ─────────────────────────────────────────────

    def _validate_citations(self, answer: str, num_sources: int) -> str:
        """
        Remove citation references to sources that don't exist.
        e.g. if only 3 sources retrieved, remove [Source 4], [Source 5] etc.
        """
        def replace_invalid(match):
            n = int(match.group(1))
            if n > num_sources:
                return ""  # remove invalid citation
            return match.group(0)

        return re.sub(r"\[Source\s+(\d+)\]", replace_invalid, answer)
