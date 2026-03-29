"""
streamlit_app/app.py

Pakistan Law & Government Assistant — Premium Chatbot Interface
Redesigned with a deep navy + emerald legal theme, smooth animations,
modern message bubbles, and a professional layout.

Run:
  streamlit run streamlit_app/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import html as html_lib
import re
import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import LegalPipeline

@st.cache_resource
def get_pipeline():
    """Load pipeline once and cache it."""
    return LegalPipeline()


# ── Page config ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pakistan Law Assistant | قانونی مددگار",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ──────────────────────────────────────────────────────────────
import os
API_BASE = os.getenv("API_BASE", "http://localhost:8000")

LAW_TYPES = {
    "⚡ All (Auto-detect)": None,
    "⚖️ Criminal Law (PPC)": "criminal",
    "🌐 Cyber Crime (PECA/FIA)": "cyber",
    "🏛️ Government Services": "service",
    "📜 Constitutional Law": "constitutional",
    "📋 Legal Procedure": "procedure",
}

EXAMPLE_QUESTIONS_EN = [
    "What documents are required for a domicile certificate in Punjab?",
    "What is the punishment for cybercrime in Pakistan?",
    "How can I apply for a driving license in Punjab?",
    "What are the steps to register a FIR in Pakistan?",
    "What laws govern online harassment in Pakistan?",
    "What is bail and when can it be granted?",
    "What are fundamental rights in the Constitution of Pakistan?",
    "How do I get a CNIC renewal from NADRA?",
]

EXAMPLE_QUESTIONS_UR = [
    "پنجاب میں ڈومیسائل سرٹیفکیٹ کے لیے کون سے دستاویزات درکار ہیں؟",
    "پاکستان میں سائبر کرائم کی سزا کیا ہے؟",
    "پنجاب میں ڈرائیونگ لائسنس کیسے بنوائیں؟",
    "ایف آئی آر درج کرنے کا طریقہ کیا ہے؟",
    "آن لائن ہراسانی پر کون سے قوانین لاگو ہوتے ہیں؟",
]

# ── Premium CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=DM+Sans:wght@300;400;500;600&family=Noto+Nastaliq+Urdu&display=swap');

:root {
    --navy:      #0A1628;
    --navy2:     #0F1F3D;
    --navy3:     #152845;
    --emerald:   #00C88C;
    --emerald2:  #00A573;
    --emerald3:  #007A54;
    --gold:      #F0B429;
    --silver:    #8892A4;
    --white:     #F0F4FF;
    --glass:     rgba(255,255,255,0.05);
    --glass2:    rgba(255,255,255,0.08);
    --border:    rgba(0,200,140,0.15);
    --shadow:    0 8px 32px rgba(0,0,0,0.4);
    --shadow-sm: 0 2px 12px rgba(0,0,0,0.3);
    --r:         16px;
    --r-sm:      10px;
}

*, *::before, *::after { box-sizing: border-box; }

.stApp {
    background: linear-gradient(135deg, #0A1628 0%, #0F1F3D 50%, #0A1628 100%) !important;
    font-family: 'DM Sans', sans-serif !important;
    color: var(--white) !important;
    min-height: 100vh;
}

#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }
.block-container { padding-top: 1rem !important; max-width: 100% !important; }

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #06101F 0%, #0A1628 100%) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * { color: var(--white) !important; }
[data-testid="stSidebar"] .stMarkdown p { color: #8892A4 !important; font-size: 0.85rem; }
[data-testid="stSidebar"] .stSelectbox label { color: #8892A4 !important; font-size: 0.8rem; }

.sidebar-logo {
    text-align: center;
    padding: 1.5rem 1rem 1rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1rem;
}
.sidebar-logo .logo-icon {
    font-size: 3rem;
    display: block;
    margin-bottom: 0.5rem;
    filter: drop-shadow(0 0 20px rgba(0,200,140,0.5));
    animation: pulse-glow 3s ease-in-out infinite;
}
@keyframes pulse-glow {
    0%, 100% { filter: drop-shadow(0 0 10px rgba(0,200,140,0.3)); }
    50%       { filter: drop-shadow(0 0 25px rgba(0,200,140,0.7)); }
}
.sidebar-logo h2 {
    font-family: 'Playfair Display', serif !important;
    font-size: 1.3rem !important;
    color: var(--emerald) !important;
    margin: 0 !important;
    letter-spacing: 0.5px;
}
.sidebar-logo p {
    font-size: 0.85rem !important;
    color: var(--silver) !important;
    margin: 0.25rem 0 0 !important;
    font-family: 'Noto Nastaliq Urdu', serif !important;
    direction: rtl;
}

.sidebar-label {
    font-size: 0.7rem !important;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--emerald) !important;
    font-weight: 600;
    margin: 1.2rem 0 0.5rem !important;
    padding: 0 0.2rem;
}

.status-online {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(0,200,140,0.1);
    border: 1px solid rgba(0,200,140,0.3);
    color: var(--emerald) !important;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
    width: 100%;
    justify-content: center;
}
.status-online::before {
    content: '';
    width: 8px; height: 8px;
    background: var(--emerald);
    border-radius: 50%;
    animation: blink 1.5s ease-in-out infinite;
}
@keyframes blink {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
}
.status-offline {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(255,80,80,0.1);
    border: 1px solid rgba(255,80,80,0.3);
    color: #FF6B6B !important;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    width: 100%;
    justify-content: center;
}

.stButton > button {
    background: var(--glass) !important;
    border: 1px solid var(--border) !important;
    color: var(--white) !important;
    border-radius: var(--r-sm) !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 400 !important;
    padding: 0.5rem 0.8rem !important;
    transition: all 0.2s ease !important;
    text-align: left !important;
}
.stButton > button:hover {
    background: rgba(0,200,140,0.12) !important;
    border-color: var(--emerald) !important;
    color: var(--emerald) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 16px rgba(0,200,140,0.2) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--emerald3), var(--emerald2)) !important;
    border-color: var(--emerald) !important;
    color: #fff !important;
    font-weight: 600 !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, var(--emerald2), var(--emerald)) !important;
    box-shadow: 0 4px 20px rgba(0,200,140,0.4) !important;
    transform: translateY(-2px) !important;
}

.stSelectbox > div > div {
    background: var(--glass) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--r-sm) !important;
    color: var(--white) !important;
}
.stSelectbox > div > div:hover { border-color: var(--emerald) !important; }

.stTextInput > div > div > input {
    background: var(--glass) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--r-sm) !important;
    color: var(--white) !important;
    font-family: 'DM Sans', sans-serif !important;
}
.stTextInput > div > div > input:focus {
    border-color: var(--emerald) !important;
    box-shadow: 0 0 0 2px rgba(0,200,140,0.2) !important;
}

.stChatInput > div {
    background: rgba(15, 31, 61, 0.8) !important;
    border: 1px solid var(--border) !important;
    border-radius: 50px !important;
    backdrop-filter: blur(10px);
    box-shadow: 0 4px 24px rgba(0,0,0,0.3) !important;
    transition: border-color 0.2s ease;
}
.stChatInput > div:focus-within {
    border-color: var(--emerald) !important;
    box-shadow: 0 4px 24px rgba(0,200,140,0.2) !important;
}
.stChatInput textarea {
    background: transparent !important;
    color: var(--white) !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.95rem !important;
    caret-color: #ffffff !important;
}
.stChatInput textarea::placeholder {
    color: var(--emerald) !important;
    opacity: 0.7 !important;
    font-style: italic;
    font-size: 0.9rem;
}
.stChatInput button {
    background: linear-gradient(135deg, var(--emerald3), var(--emerald)) !important;
    border-radius: 50% !important;
    border: none !important;
}

.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--border) !important;
    gap: 0.5rem;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--silver) !important;
    border-radius: var(--r-sm) var(--r-sm) 0 0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    padding: 0.6rem 1.2rem !important;
    border: none !important;
    transition: all 0.2s ease !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--emerald) !important;
    background: rgba(0,200,140,0.05) !important;
}
.stTabs [aria-selected="true"] {
    color: var(--emerald) !important;
    border-bottom: 2px solid var(--emerald) !important;
    background: rgba(0,200,140,0.08) !important;
}
.stTabs [data-baseweb="tab-panel"] {
    padding: 1.5rem 0 !important;
    background: transparent !important;
}

hr { border-color: var(--border) !important; margin: 0.8rem 0 !important; }

.stExpander {
    background: var(--glass) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--r-sm) !important;
}
.stExpander summary { color: var(--silver) !important; font-size: 0.85rem !important; }
.stExpander summary:hover { color: var(--emerald) !important; }

.stDataFrame { background: transparent !important; }
.stDataFrame table { background: transparent !important; color: var(--white) !important; }

.stFileUploader > div {
    background: var(--glass) !important;
    border: 2px dashed var(--border) !important;
    border-radius: var(--r) !important;
}
.stFileUploader > div:hover { border-color: var(--emerald) !important; }

.app-header {
    background: linear-gradient(135deg, rgba(0,200,140,0.08) 0%, rgba(0,165,115,0.04) 100%);
    border: 1px solid var(--border);
    border-radius: var(--r);
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}
.app-header::before {
    content: '⚖️';
    position: absolute;
    right: 2rem;
    top: 50%;
    transform: translateY(-50%);
    font-size: 5rem;
    opacity: 0.5;
    pointer-events: none;
}
.app-header h1 {
    font-family: 'Playfair Display', serif !important;
    font-size: 2rem !important;
    color: var(--white) !important;
    margin: 0 0 0.4rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.5px;
}
.app-header h1 span { color: var(--emerald); }
.app-header p {
    color: var(--silver) !important;
    font-size: 0.9rem !important;
    margin: 0 !important;
    font-weight: 300;
}

/* ── Chat messages ── */
.msg-user-wrap {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 1rem;
    animation: slideInRight 0.3s ease;
}
@keyframes slideInRight {
    from { opacity: 0; transform: translateX(20px); }
    to   { opacity: 1; transform: translateX(0); }
}
.msg-user {
    background: linear-gradient(135deg, var(--emerald3) 0%, var(--emerald2) 100%);
    color: white;
    padding: 0.75rem 1.1rem;
    border-radius: 18px 18px 4px 18px;
    max-width: 70%;
    font-size: 0.9rem;
    line-height: 1.5;
    box-shadow: 0 4px 16px rgba(0,200,140,0.25);
    font-weight: 400;
    word-break: break-word;
}
.msg-user.urdu {
    direction: rtl;
    text-align: right;
    font-family: 'Noto Nastaliq Urdu', serif;
    font-size: 1rem;
    border-radius: 18px 18px 18px 4px;
}

/* Bot row — avatar + content side by side */
.msg-bot-wrap {
    display: flex;
    justify-content: flex-start;
    gap: 0.7rem;
    margin-bottom: 0.3rem;   /* reduced — pills/disclaimer follow separately */
    animation: slideInLeft 0.3s ease;
}
@keyframes slideInLeft {
    from { opacity: 0; transform: translateX(-20px); }
    to   { opacity: 1; transform: translateX(0); }
}
.bot-avatar {
    width: 36px; height: 36px;
    background: linear-gradient(135deg, var(--navy3), var(--navy2));
    border: 1px solid var(--border);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.1rem;
    flex-shrink: 0;
    margin-top: 2px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
.msg-bot-content { max-width: 80%; }
.msg-bot {
    background: rgba(15, 31, 61, 0.7);
    border: 1px solid var(--border);
    color: var(--white);
    padding: 0.9rem 1.2rem;
    border-radius: 4px 18px 18px 18px;
    font-size: 0.9rem;
    line-height: 1.7;
    box-shadow: var(--shadow-sm);
    backdrop-filter: blur(8px);
    word-break: break-word;
}
.msg-bot.urdu {
    direction: rtl;
    text-align: right;
    font-family: 'Noto Nastaliq Urdu', serif;
    font-size: 1rem;
    border-radius: 18px 4px 18px 18px;
}
.msg-bot strong { color: var(--emerald); }
.msg-bot ol, .msg-bot ul { padding-left: 1.2rem; margin: 0.5rem 0; }
.msg-bot li { margin: 0.3rem 0; color: rgba(240,244,255,0.9); }

.bot-name-tag {
    font-size: 0.72rem;
    color: var(--emerald);
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-bottom: 0.3rem;
    display: flex;
    align-items: center;
    gap: 4px;
}
.bot-name-tag::before {
    content: '';
    width: 6px; height: 6px;
    background: var(--emerald);
    border-radius: 50%;
}

/* Citation pills — rendered in own st.markdown call */
.citations-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.4rem;
    margin-left: 2.9rem;   /* aligns with bubble, clears avatar */
    margin-bottom: 0.2rem;
}
.cite-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(0,200,140,0.08);
    border: 1px solid rgba(0,200,140,0.2);
    color: var(--emerald);
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 500;
    transition: all 0.15s ease;
    cursor: default;
}
.cite-pill:hover {
    background: rgba(0,200,140,0.15);
    border-color: var(--emerald);
}
.cite-pill .cite-num {
    background: var(--emerald);
    color: var(--navy);
    width: 16px; height: 16px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.65rem;
    font-weight: 700;
}

/* Disclaimer bar — rendered in own st.markdown call */
.disclaimer-bar {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    background: rgba(240, 180, 41, 0.06);
    border: 1px solid rgba(240,180,41,0.2);
    border-radius: var(--r-sm);
    padding: 0.5rem 0.8rem;
    margin-top: 0.4rem;
    margin-left: 2.9rem;   /* aligns with bubble, clears avatar */
    margin-bottom: 0.8rem;
    font-size: 0.75rem;
    color: rgba(240,180,41,0.8);
    line-height: 1.4;
}

/* Message bottom spacer */
.msg-end-spacer { margin-bottom: 0.8rem; }

.not-found {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: rgba(240,244,255,0.5) !important;
    font-style: italic;
    font-size: 0.88rem;
}

.source-item {
    background: var(--glass);
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    padding: 0.6rem 0.9rem;
    margin: 0.3rem 0;
    font-size: 0.82rem;
}
.source-item .s-name { color: var(--white); font-weight: 500; margin-bottom: 2px; }
.source-item .s-meta {
    color: var(--silver);
    font-size: 0.75rem;
    display: flex;
    gap: 0.7rem;
    flex-wrap: wrap;
}
.source-item .s-section { color: var(--emerald); }

.stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.3rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    font-size: 0.8rem;
}
.stat-row .s-label { color: var(--silver); }
.stat-row .s-val   { color: var(--emerald); font-weight: 600; }

.indexed-src {
    background: var(--glass);
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    padding: 0.5rem 0.7rem;
    margin: 0.3rem 0;
    font-size: 0.78rem;
}
.indexed-src .is-name { color: var(--white); font-weight: 500; font-size: 0.8rem; }
.indexed-src .is-meta { color: var(--silver); }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(0,200,140,0.3); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: var(--emerald); }

.stSuccess { background: rgba(0,200,140,0.1) !important; border-color: var(--emerald) !important; color: var(--emerald) !important; border-radius: var(--r-sm) !important; }
.stError   { background: rgba(255,80,80,0.08) !important; color: #FF6B6B !important; border-radius: var(--r-sm) !important; }
.stWarning { background: rgba(240,180,41,0.08) !important; color: var(--gold) !important; border-radius: var(--r-sm) !important; }
.stInfo    { background: rgba(0,200,140,0.05) !important; color: var(--emerald) !important; border-radius: var(--r-sm) !important; }
.stSpinner > div { border-top-color: var(--emerald) !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────

def hard_strip(text: str) -> str:
    """Remove all HTML tags from text. Double-pass for safety."""
    text = re.sub(r'<[^>]*>', '', text)   # complete / self-closing tags
    text = re.sub(r'<[^>]*$',  '', text)  # unclosed tag at end of string
    text = re.sub(r'^[^<]*>',  '', text)  # orphaned > at start of string
    # second pass — catches e.g. <<script>> after first removal
    text = re.sub(r'<[^>]*>', '', text)
    return text.strip()


def format_answer_html(answer: str) -> str:
    """
    Convert plain-text LLM answer to safe HTML.
    Pipeline: double-strip → escape → bold → lists → paragraphs.
    All list-item text is sliced AFTER escaping so no tag survives.
    """
    clean = hard_strip(answer)
    if not clean:
        return "<p><em>No response.</em></p>"

    safe = html_lib.escape(clean)

    # **bold**
    parts = safe.split("**")
    safe = "".join(
        f"<strong>{p}</strong>" if idx % 2 == 1 else p
        for idx, p in enumerate(parts)
    )

    lines = safe.split("\n")
    out: list[str] = []
    in_list: str | bool = False

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s[0].isdigit() and len(s) > 1 and s[1] in ".):-":
            # numbered list item
            if in_list != "ol":
                if in_list == "ul": out.append("</ul>")
                out.append("<ol>"); in_list = "ol"
            out.append(f"<li>{s[2:].strip()}</li>")
        elif s[0] in ("-", "•", "*") and len(s) > 1:
            # bullet list item
            if in_list != "ul":
                if in_list == "ol": out.append("</ol>")
                out.append("<ul>"); in_list = "ul"
            out.append(f"<li>{s[1:].strip()}</li>")
        else:
            # plain paragraph
            if in_list == "ol":   out.append("</ol>"); in_list = False
            elif in_list == "ul": out.append("</ul>"); in_list = False
            out.append(f"<p style='margin:0.3rem 0'>{s}</p>")

    # Always close any open list tag
    if in_list == "ol":   out.append("</ol>")
    elif in_list == "ul": out.append("</ul>")

    return "".join(out)


# ── Session state ─────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "language" not in st.session_state:
    st.session_state.language = "en"

# Migration guard — drop any cached messages that still contain raw HTML
st.session_state.messages = [
    m for m in st.session_state.messages
    if not (
        m["role"] == "assistant"
        and isinstance(m["content"], dict)
        and (
            re.search(r'<[^>]+>', m["content"].get("answer", ""))
            or re.search(r'<[^>]+>', m["content"].get("disclaimer", ""))
            or m["content"].get("answer", "").strip().startswith("<div")
            or m["content"].get("answer", "").strip().startswith("<span")
        )
    )
]


# ── API helpers ───────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def check_api_health() -> dict:
    try:
        r = requests.get(f"{API_BASE}/health", timeout=3)
        return r.json()
    except Exception:
        return {"status": "offline", "ready": False, "indexed_chunks": 0}

@st.cache_data(ttl=30)
def get_sources() -> list[dict]:
    try:
        r = requests.get(f"{API_BASE}/sources", timeout=5)
        return r.json().get("sources", [])
    except Exception:
        return []

def query_api(question: str, language: str, law_type: str | None, top_k: int = 3) -> dict:
    payload = {"question": question, "language": language, "top_k": top_k}
    if law_type:
        payload["law_type"] = law_type
    r = requests.post(f"{API_BASE}/query", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

def summarize_api(topic: str, language: str) -> dict:
    r = requests.post(f"{API_BASE}/summarize", json={"topic": topic, "language": language}, timeout=60)
    r.raise_for_status()
    return r.json()

def upload_api(file_bytes, filename: str, source_name: str, law_type: str) -> dict:
    files = {"file": (filename, file_bytes, "application/pdf")}
    data  = {"source_name": source_name, "law_type": law_type, "language": "en"}
    r = requests.post(f"{API_BASE}/upload", files=files, data=data, timeout=120)
    r.raise_for_status()
    return r.json()

def process_query(question: str, lang: str, law_type) -> dict:
    """Call pipeline directly — no FastAPI needed."""
    try:
        pipeline = get_pipeline()
        result = pipeline.query(
            question=question,
            language=lang,
            law_type=law_type,
        )
        resp = result.to_dict()
        resp["answer"]     = hard_strip(resp.get("answer", ""))
        resp["disclaimer"] = hard_strip(resp.get("disclaimer", ""))
        return resp
    except Exception as e:
        return {
            "answer": f"Error: {e}",
            "citations": [], "disclaimer": "",
            "language": lang, "found": False,
        }

# ── Sidebar ───────────────────────────────────────────────────────────────
health = check_api_health()

with st.sidebar:
    st.markdown("""
    <div class="sidebar-logo">
        <span class="logo-icon">⚖️</span>
        <h2>Pakistan Law</h2>
        <p>قانونی مددگار</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<p class="sidebar-label">Language / زبان</p>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        en_type = "primary" if st.session_state.language == "en" else "secondary"
        if st.button("🇬🇧 EN", use_container_width=True, type=en_type, key="btn_en"):
            st.session_state.language = "en"
            st.rerun()
    with col2:
        ur_type = "primary" if st.session_state.language == "ur" else "secondary"
        if st.button("🇵🇰 اردو", use_container_width=True, type=ur_type, key="btn_ur"):
            st.session_state.language = "ur"
            st.rerun()

    st.markdown('<p class="sidebar-label">Filter by Category</p>', unsafe_allow_html=True)
    selected_label    = st.selectbox("Category", list(LAW_TYPES.keys()), label_visibility="collapsed")
    selected_law_type = LAW_TYPES[selected_label]

    st.markdown('<p class="sidebar-label">System Status</p>', unsafe_allow_html=True)

    if health["status"] == "ok" and health["ready"]:
        st.markdown(
            f'<div class="status-online">Ready · {health["indexed_chunks"]:,} chunks</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"""
        <div style="margin-top:0.7rem">
            <div class="stat-row"><span class="s-label">Legal chunks</span><span class="s-val">{health["indexed_chunks"]:,}</span></div>
            <div class="stat-row"><span class="s-label">API</span><span class="s-val">Online</span></div>
            <div class="stat-row"><span class="s-label">LLM</span><span class="s-val">Groq 70B</span></div>
        </div>
        """, unsafe_allow_html=True)
    elif health["status"] == "ok":
        st.markdown('<div class="status-offline">⚠ Not Indexed Yet</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-offline">✕ API Offline</div>', unsafe_allow_html=True)
        st.caption("Run: `uvicorn src.api.main:app`")

    st.markdown('<p class="sidebar-label">Indexed Sources</p>', unsafe_allow_html=True)
    with st.expander("📚 View Sources", expanded=False):
        sources = get_sources()
        if sources:
            for src in sources:
                st.markdown(f"""
                <div class="indexed-src">
                    <div class="is-name">{html_lib.escape(src['source_name'])}</div>
                    <div class="is-meta">{html_lib.escape(src['law_type'])} · {src['chunk_count']} chunks</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No sources indexed yet.")

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("🗑️  Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.markdown("""
    <div style="position:fixed;bottom:1rem;left:0;width:260px;text-align:center;padding:0 1rem">
        <div style="font-size:0.7rem;color:rgba(136,146,164,0.5);line-height:1.6">
            Pakistan Law Assistant v1.0<br>
            Engineer Kashif Muneer
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Main Content ──────────────────────────────────────────────────────────
lang     = st.session_state.language
examples = EXAMPLE_QUESTIONS_UR if lang == "ur" else EXAMPLE_QUESTIONS_EN

st.markdown(f"""
<div class="app-header">
    <h1>Pakistan Law <span>&amp;</span> Government Assistant</h1>
    <p>{"Ask questions about Pakistani laws, rights, and government services in English or Urdu"
       if lang == "en" else
       "اردو یا انگریزی میں سوال کریں"}</p>
</div>
""", unsafe_allow_html=True)

tab_chat, tab_summarize, tab_upload = st.tabs([
    "💬  Chat",
    "📋  Summarize Law",
    "📤  Upload Document",
])


# ═══════════════════════════════════════════════════
# TAB 1 — CHAT
# ═══════════════════════════════════════════════════
with tab_chat:

    # Quick examples
    st.markdown(
        '<p style="font-size:0.75rem;letter-spacing:2px;text-transform:uppercase;'
        'color:var(--emerald);font-weight:600;margin-bottom:0.6rem">Quick Examples</p>',
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for i, example in enumerate(examples[:4]):
        label = example[:65] + ("…" if len(example) > 65 else "")
        if cols[i % 2].button(label, key=f"ex_{i}", use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": example})
            if health["ready"]:
                with st.spinner("Searching legal documents…"):
                    resp = process_query(example, lang, selected_law_type)
                    st.session_state.messages.append({"role": "assistant", "content": resp})
            st.rerun()

    st.markdown('<hr style="margin:1rem 0">', unsafe_allow_html=True)

    # ── Chat history ──────────────────────────────────────────────────────
    if not st.session_state.messages:
        st.markdown("""
        <div style="text-align:center;padding:3rem 2rem;color:rgba(136,146,164,0.4)">
            <div style="font-size:3.5rem;margin-bottom:1rem;opacity:0.3">⚖️</div>
            <div style="font-size:0.9rem;font-weight:300">
                Ask a question about Pakistani law, government services,<br>
                or your legal rights to get started.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        with st.container():
            for msg in st.session_state.messages:

                # ── User bubble ───────────────────────────────────────
                if msg["role"] == "user":
                    urdu_cls     = " urdu" if lang == "ur" else ""
                    safe_content = html_lib.escape(str(msg["content"]))
                    st.markdown(f"""
                    <div class="msg-user-wrap">
                        <div class="msg-user{urdu_cls}">{safe_content}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # ── Bot bubble ────────────────────────────────────────
                else:
                    resp       = msg["content"]
                    is_urdu    = resp.get("language") == "ur"
                    urdu_cls   = " urdu" if is_urdu else ""
                    answer     = resp.get("answer", "")
                    citations  = resp.get("citations", [])
                    disclaimer = resp.get("disclaimer", "")
                    found      = resp.get("found", True)

                    # Build answer HTML
                    if not found and answer:
                        safe_answer = html_lib.escape(hard_strip(answer))
                        answer_html = f'<span class="not-found">🔍 {safe_answer}</span>'
                    else:
                        answer_html = format_answer_html(answer)

                    # ── CALL 1: avatar + nametag + bubble only ────────
                    # Nothing dynamic (citations, disclaimer) goes here.
                    # This ensures malformed answer HTML never corrupts
                    # the disclaimer or pill blocks.
                    st.markdown(f"""
                    <div class="msg-bot-wrap">
                        <div class="bot-avatar">⚖️</div>
                        <div class="msg-bot-content">
                            <div class="bot-name-tag">Pakistan Law Assistant</div>
                            <div class="msg-bot{urdu_cls}">{answer_html}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # ── CALL 2: citation pills (isolated) ─────────────
                    if citations:
                        pills = []
                        for cite in citations:
                            name    = html_lib.escape(cite.get("source_name", "Source")[:30])
                            section = html_lib.escape(cite.get("section", "")[:25])
                            label   = name + (f" · {section}" if section else "")
                            pills.append(
                                f'<span class="cite-pill">'
                                f'<span class="cite-num">{cite["index"]}</span>'
                                f'{label}</span>'
                            )
                        st.markdown(
                            f'<div class="citations-strip">{"".join(pills)}</div>',
                            unsafe_allow_html=True,
                        )

                    # ── CALL 3: disclaimer (isolated) ─────────────────
                    if disclaimer:
                        safe_disc = html_lib.escape(hard_strip(disclaimer))
                        st.markdown(
                            f'<div class="disclaimer-bar">'
                            f'<span style="font-size:0.85rem">&#9888;</span>&nbsp;'
                            f'<span style="font-size:0.75rem">{safe_disc}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                    # ── Bottom spacer ─────────────────────────────────
                    st.markdown('<div class="msg-end-spacer"></div>', unsafe_allow_html=True)

                    # ── Source expander ───────────────────────────────
                    if citations:
                        with st.expander(
                            f"📖  View {len(citations)} source document(s)",
                            expanded=False,
                        ):
                            for cite in citations:
                                sec   = html_lib.escape(cite.get("section", ""))
                                page  = cite.get("page_number", "")
                                score = cite.get("relevance_score", 0)
                                name  = html_lib.escape(cite.get("source_name", "Unknown"))
                                sec_html  = f'<span class="s-section">{sec}</span>' if sec else ""
                                page_html = f'<span>p.{page}</span>' if page else ""
                                st.markdown(f"""
                                <div class="source-item">
                                    <div class="s-name">[{cite["index"]}] {name}</div>
                                    <div class="s-meta">
                                        {sec_html}{page_html}
                                        <span>relevance: {score:.2f}</span>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)

    # ── Chat input ────────────────────────────────────────────────────────
    placeholder = "اپنا سوال یہاں لکھیں…" if lang == "ur" else "Ask your legal question here…"
    user_input  = st.chat_input(placeholder)

    if user_input and user_input.strip():
        st.session_state.messages.append({"role": "user", "content": user_input})
        if health["ready"]:
            spinner_msg = "Searching legal documents…" if lang == "en" else "تلاش جاری ہے…"
            with st.spinner(spinner_msg):
                resp = process_query(user_input, lang, selected_law_type)
                st.session_state.messages.append({"role": "assistant", "content": resp})
        else:
            st.session_state.messages.append({
                "role": "assistant",
                "content": {
                    "answer": "Knowledge base not ready. Run `python scripts/ingest_documents.py` first.",
                    "citations": [], "disclaimer": "", "language": "en", "found": False,
                },
            })
        st.rerun()


# ═══════════════════════════════════════════════════
# TAB 2 — SUMMARIZE
# ═══════════════════════════════════════════════════
with tab_summarize:
    st.markdown("""
    <div style="margin-bottom:1.2rem">
        <h3 style="font-family:'Playfair Display',serif;color:var(--white);font-size:1.4rem;margin:0 0 0.3rem">
            Summarize a Legal Topic
        </h3>
        <p style="color:var(--silver);font-size:0.85rem;margin:0">
            Get a structured summary of any Pakistani law or government procedure
        </p>
    </div>
    """, unsafe_allow_html=True)

    topic_examples = [
        "PECA 2016 — Prevention of Electronic Crimes Act",
        "Pakistan Penal Code — Offences against person",
        "FIR registration procedure in Pakistan",
        "NADRA CNIC application process",
        "Bail provisions in Pakistan",
        "Fundamental rights under Constitution of Pakistan",
    ]

    selected_topic = st.selectbox(
        "Select or type a topic:",
        ["✏️ Custom topic…"] + topic_examples,
    )
    if selected_topic == "✏️ Custom topic…":
        topic_input = st.text_input(
            "Enter your topic:",
            placeholder="e.g. Online harassment laws in Pakistan",
        )
    else:
        topic_input = selected_topic

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("📋  Generate Summary", type="primary",
                 disabled=not health["ready"], use_container_width=False):
        if topic_input:
            with st.spinner("Generating summary from legal documents…"):
                try:
                    resp        = summarize_api(topic_input, lang)
                    safe_answer = html_lib.escape(hard_strip(resp.get("answer", "")))
                    # Summary card
                    st.markdown(f"""
                    <div style="background:rgba(15,31,61,0.6);border:1px solid var(--border);
                                border-radius:var(--r);padding:1.5rem;margin-top:1rem">
                        <div style="font-family:'Playfair Display',serif;font-size:1.1rem;
                                    color:var(--emerald);margin-bottom:1rem">
                            📜 {html_lib.escape(topic_input)}
                        </div>
                        <div style="color:var(--white);font-size:0.9rem;line-height:1.7">
                            {safe_answer}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    if resp.get("citations"):
                        st.markdown(
                            '<p class="sidebar-label" style="margin-top:1rem">Sources Referenced</p>',
                            unsafe_allow_html=True,
                        )
                        for cite in resp["citations"]:
                            name = html_lib.escape(cite.get("source_name", "Unknown"))
                            sec  = html_lib.escape(cite.get("section", ""))
                            st.markdown(f"""
                            <div class="source-item">
                                <div class="s-name">[{cite["index"]}] {name}</div>
                                <div class="s-meta"><span class="s-section">{sec}</span></div>
                            </div>
                            """, unsafe_allow_html=True)

                    # Disclaimer — separate call, safe from summary HTML
                    if resp.get("disclaimer"):
                        safe_disc = html_lib.escape(hard_strip(resp["disclaimer"]))
                        st.markdown(
                            f'<div class="disclaimer-bar" style="margin-left:0">'
                            f'<span style="font-size:0.85rem">&#9888;</span>&nbsp;'
                            f'<span style="font-size:0.75rem">{safe_disc}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                except Exception as e:
                    st.error(f"Failed: {e}")


# ═══════════════════════════════════════════════════
# TAB 3 — UPLOAD
# ═══════════════════════════════════════════════════
with tab_upload:
    st.markdown("""
    <div style="margin-bottom:1.2rem">
        <h3 style="font-family:'Playfair Display',serif;color:var(--white);font-size:1.4rem;margin:0 0 0.3rem">
            Upload Legal Document
        </h3>
        <p style="color:var(--silver);font-size:0.85rem;margin:0">
            Add any official Pakistani law PDF to extend the knowledge base instantly
        </p>
    </div>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Select PDF file", type=["pdf"],
        help="Official legal/government PDFs only. Max 50MB.",
    )

    col1, col2 = st.columns(2)
    with col1:
        src_name = st.text_input(
            "Document name *",
            placeholder="e.g. Punjab Local Government Act 2022",
        )
    with col2:
        law_type_upload = st.selectbox(
            "Law category *",
            ["general", "criminal", "cyber", "service", "constitutional", "procedure", "civil"],
        )

    st.markdown("<br>", unsafe_allow_html=True)
    btn_disabled = not (uploaded_file and src_name)
    if st.button("⬆️  Upload & Index Document", type="primary", disabled=btn_disabled):
        with st.spinner(f"Processing {uploaded_file.name}…"):
            try:
                result = upload_api(
                    uploaded_file.read(), uploaded_file.name,
                    src_name, law_type_upload,
                )
                st.success(
                    f"✅ Successfully indexed **{result['chunks_added']}** chunks "
                    f"from _{result['source_name']}_"
                )
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Upload failed: {e}")

    st.markdown('<hr style="margin:1.5rem 0">', unsafe_allow_html=True)
    st.markdown('<p class="sidebar-label">Currently Indexed Documents</p>', unsafe_allow_html=True)

    sources = get_sources()
    if sources:
        import pandas as pd
        df = pd.DataFrame(sources).rename(columns={
            "source_name": "Document",
            "law_type":    "Category",
            "chunk_count": "Chunks",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No documents indexed yet. Run ingestion pipeline first.")