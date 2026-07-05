"""Streamlit UI for the safety-constrained RAG chatbot."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag.chunking import STRATEGY_LABELS  # noqa: E402
from rag.generation import (  # noqa: E402
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    GenerationError,
    build_prompt,
    generate_ollama,
    generate_openai_compatible,
)
from rag.indexing import load_index  # noqa: E402
from rag.retrieval import retrieve  # noqa: E402
from rag.safety import (  # noqa: E402
    CERTIFICATION_DISCLAIMER,
    REFUSAL_MESSAGE,
    assess,
)

st.set_page_config(
    page_title="RAG Chunking Strategies — Construction QA",
    page_icon="📐",
    layout="wide",
)

st.markdown(
    """
    <style>
    .answer-card {
        background-color: #22262b;
        border: 1px solid #3a4455;
        border-left: 3px solid #5b8dbe;
        border-radius: 6px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner="Loading FAISS index...")
def cached_index(strategy: str):
    return load_index(strategy)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Retrieval settings")
    strategy = st.selectbox(
        "Chunking strategy",
        options=list(STRATEGY_LABELS),
        format_func=lambda k: STRATEGY_LABELS[k],
        help="Which prebuilt FAISS index to query.",
    )
    top_k = st.slider("Top-k retrieved chunks", min_value=1, max_value=10, value=4)

    st.header("LLM provider")
    provider = st.radio(
        "Provider",
        options=["Local Ollama", "OpenAI-compatible API"],
        help="Default is a local Ollama model; no API key needed.",
    )

    if provider == "Local Ollama":
        ollama_model = st.text_input("Ollama model", value=DEFAULT_OLLAMA_MODEL)
        ollama_base_url = st.text_input("Ollama base URL", value=DEFAULT_OLLAMA_BASE_URL)
    else:
        api_base_url = st.text_input(
            "API base URL",
            value=os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
        )
        api_key = st.text_input(
            "API key", value=os.environ.get("OPENAI_API_KEY", ""), type="password"
        )
        api_model = st.text_input(
            "API model", value=os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        )

    st.caption(
        "Answers are generated only from the retrieved document context. "
        "This tool cannot certify legal, regulatory, structural, or "
        "compliance status."
    )

# ---------------------------------------------------------------- main area
st.title("Construction Documentation QA")
st.caption(
    "Evaluating RAG chunking strategies for safety-constrained question "
    "answering over construction documentation — academic prototype."
)

if "history" not in st.session_state:
    st.session_state.history = []


def render_turn(turn: dict) -> None:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        if turn.get("certification_flag"):
            st.warning(CERTIFICATION_DISCLAIMER)
        st.markdown(
            f"<div class='answer-card'>{turn['answer']}</div>",
            unsafe_allow_html=True,
        )
        grounding = turn["grounding"]
        note = turn["notes"]
        if grounding == "strong":
            st.info(f"Grounding: strong — {note}")
        elif grounding == "moderate":
            st.warning(f"Grounding: moderate — {note}")
        else:
            st.error(f"Grounding: weak — {note}")

        sources = turn.get("sources", [])
        if sources:
            with st.expander(f"Retrieved sources ({len(sources)})"):
                for r in sources:
                    section = f" · {r['section']}" if r.get("section") else ""
                    st.markdown(
                        f"**{r['doc_name']}**{section}  \n"
                        f"chunk: `{r['chunk_id']}` · similarity: `{r['score']:.4f}`"
                    )
                    snippet = r["text"][:300] + ("…" if len(r["text"]) > 300 else "")
                    st.caption(snippet)
                    st.divider()


for turn in st.session_state.history:
    render_turn(turn)

question = st.chat_input("Ask a question about the construction documents…")

if question:
    try:
        index_and_chunks = cached_index(strategy)
    except FileNotFoundError as exc:
        st.error(
            f"{exc}\n\nInside Docker: "
            "`docker compose exec app python scripts/build_indexes.py`"
        )
        st.stop()

    with st.spinner("Retrieving…"):
        retrieved = retrieve(question, strategy, top_k,
                             index_and_chunks=index_and_chunks)
    verdict = assess(question, retrieved)

    if not verdict.should_answer:
        answer = REFUSAL_MESSAGE
    else:
        prompt = build_prompt(question, retrieved)
        try:
            with st.spinner("Generating answer…"):
                if provider == "Local Ollama":
                    answer = generate_ollama(prompt, model=ollama_model,
                                             base_url=ollama_base_url)
                else:
                    answer = generate_openai_compatible(
                        prompt, model=api_model, base_url=api_base_url,
                        api_key=api_key,
                    )
        except GenerationError as exc:
            answer = f"⚠️ {exc}"

    turn = {
        "question": question,
        "answer": answer,
        "grounding": verdict.grounding,
        "notes": verdict.notes,
        "certification_flag": verdict.certification_flag,
        "sources": retrieved,
        "strategy": strategy,
    }
    st.session_state.history.append(turn)
    render_turn(turn)
