"""
src/utils/language.py

Multilingual support utilities for English ↔ Urdu.

Approach:
  - Language detection via langdetect
  - Translation via deep-translator (Google Translate API — free tier)
  - Urdu query expansion: translate Urdu query → English for retrieval,
    then translate English answer → Urdu for response
  - Bilingual glossary for common Pakistani legal terms

Usage:
    lang_util = LanguageUtils()
    lang = lang_util.detect("سائبر کرائم کی سزا کیا ہے؟")   # → "ur"
    en_query = lang_util.to_english("سائبر کرائم کی سزا کیا ہے؟")
    ur_answer = lang_util.to_urdu("The punishment is 3 years imprisonment.")
"""
from __future__ import annotations

import re
from functools import lru_cache

from loguru import logger


# ── Legal term bilingual glossary ──────────────────────────────────────────
# Common Pakistani legal terms: English → Urdu
LEGAL_GLOSSARY_EN_UR = {
    "Pakistan Penal Code": "پاکستان تعزیرات",
    "FIR": "ایف آئی آر",
    "bail": "ضمانت",
    "arrest": "گرفتاری",
    "imprisonment": "قید",
    "fine": "جرمانہ",
    "sentence": "سزا",
    "court": "عدالت",
    "judge": "جج",
    "lawyer": "وکیل",
    "plaintiff": "مدعی",
    "defendant": "ملزم",
    "evidence": "ثبوت",
    "witness": "گواہ",
    "NADRA": "نادرا",
    "domicile": "ڈومیسائل",
    "driving license": "ڈرائیونگ لائسنس",
    "CNIC": "شناختی کارڈ",
    "cybercrime": "سائبر کرائم",
    "harassment": "ہراسانی",
    "Section": "دفعہ",
    "Article": "آرٹیکل",
    "Constitution": "آئین",
    "fundamental rights": "بنیادی حقوق",
    "government": "حکومت",
    "procedure": "طریقہ کار",
    "registration": "رجسٹریشن",
    "application": "درخواست",
    "document": "دستاویز",
    "certificate": "سرٹیفکیٹ",
}

# Urdu → English (reverse)
LEGAL_GLOSSARY_UR_EN = {v: k for k, v in LEGAL_GLOSSARY_EN_UR.items()}


class LanguageUtils:
    """
    Utility class for language detection and translation.
    Falls back gracefully if translation libraries are unavailable.
    """

    def __init__(self):
        self._translator = None
        self._langdetect_ready = self._init_langdetect()

    def _init_langdetect(self) -> bool:
        try:
            from langdetect import DetectorFactory
            DetectorFactory.seed = 42   # reproducible detection
            return True
        except ImportError:
            logger.warning("langdetect not installed. Language detection disabled.")
            return False

    def detect(self, text: str) -> str:
        """
        Detect language of text.
        Returns ISO 639-1 code: "en", "ur", etc.
        Falls back to "en" if detection fails.
        """
        if not self._langdetect_ready:
            return "en"

        # Heuristic: check for Urdu Unicode range (U+0600–U+06FF)
        urdu_chars = len(re.findall(r"[\u0600-\u06FF]", text))
        if urdu_chars > len(text) * 0.3:
            return "ur"

        try:
            from langdetect import detect
            lang = detect(text)
            return lang
        except Exception:
            return "en"

    def to_english(self, text: str) -> str:
        """
        Translate text to English.
        First checks glossary, then uses deep-translator.
        Returns original text if translation fails.
        """
        # Check if already English
        if self.detect(text) == "en":
            return text

        # Glossary substitution for known legal terms
        translated = text
        for ur_term, en_term in LEGAL_GLOSSARY_UR_EN.items():
            translated = translated.replace(ur_term, en_term)

        # If mostly glossary-translated, return it
        urdu_remaining = len(re.findall(r"[\u0600-\u06FF]", translated))
        if urdu_remaining < 3:
            return translated

        # Use deep-translator for full translation
        try:
            from deep_translator import GoogleTranslator
            result = GoogleTranslator(source="ur", target="en").translate(text)
            return result or text
        except Exception as e:
            logger.warning(f"Translation to English failed: {e}")
            return text

    def to_urdu(self, text: str) -> str:
        """
        Translate text to Urdu.
        Returns original text if translation fails.
        """
        if self.detect(text) == "ur":
            return text

        try:
            from deep_translator import GoogleTranslator
            result = GoogleTranslator(source="en", target="ur").translate(text)
            return result or text
        except Exception as e:
            logger.warning(f"Translation to Urdu failed: {e}")
            return text

    def expand_query_for_retrieval(self, query: str) -> str:
        """
        For Urdu queries: translate to English for better retrieval,
        since most documents are in English.

        Returns English version of the query.
        """
        lang = self.detect(query)
        if lang == "ur":
            en_query = self.to_english(query)
            logger.info(f"Urdu query translated for retrieval: {en_query[:60]}")
            return en_query
        return query

    def format_legal_term(self, term: str, language: str = "en") -> str:
        """Return a legal term in the requested language."""
        if language == "ur":
            return LEGAL_GLOSSARY_EN_UR.get(term, term)
        return LEGAL_GLOSSARY_UR_EN.get(term, term)
