# Evaluating RAG Chunking Strategies for Safety-Constrained Question Answering over Construction Documentation

An academic prototype (MSc NLP / Generative AI assignment) comparing three chunking strategies — **fixed-size**, **recursive**, and **section-aware** — in a retrieval-augmented generation (RAG) chatbot over synthetic construction-site documentation, with safety-constrained answering behaviour.

## Architecture

```
                 ┌──────────────────────────────────────────────┐
                 │                Streamlit UI                  │
                 │  strategy / top_k / provider selection       │
                 └────────┬─────────────────────────┬───────────┘
                          │ query                   │ prompt (context-grounded)
                          ▼                         ▼
                 ┌────────────────┐        ┌──────────────────────┐
                 │  FAISS index   │        │  LLM provider        │
                 │  per strategy  │        │  Ollama (default) or │
                 │  (IndexFlatIP) │        │  OpenAI-compatible   │
                 └────────┬───────┘        └──────────────────────┘
                          │ top-k chunks + cosine scores
                          ▼
                 ┌────────────────┐
                 │ Safety layer   │  evidence floor · certification
                 │ (rag/safety.py)│  guardrails · grounding notes
                 └────────────────┘

  Offline:  data/sample_documents/*.md ──► rag/chunking.py (3 strategies)
            ──► sentence-transformers all-MiniLM-L6-v2 ──► data/indexes/<strategy>/
```

## Quickstart (Docker)

```bash
docker compose up --build
```

Then pull the default model (one-off, ~400 MB):

```bash
docker compose exec ollama ollama pull qwen2.5:0.5b
```

Open <http://localhost:8501>. The app builds the FAISS indexes automatically on first start if they are missing.

No API key is needed for the default local mode.

## Running locally without Docker

Requires Python 3.10–3.12 (torch has no wheels for newer versions yet).

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_indexes.py
streamlit run app/streamlit_app.py
```

For generation you also need [Ollama](https://ollama.com) running locally:

```bash
ollama pull qwen2.5:0.5b
```

## Rebuilding the indexes

Indexes are fully reproducible (sorted file order, fixed chunking parameters, deterministic chunk ids).

```bash
# inside Docker
docker compose exec app python scripts/build_indexes.py

# or locally
python scripts/build_indexes.py            # all three strategies
python scripts/build_indexes.py --strategy section   # just one
```

Outputs:

- `data/processed/chunks_<strategy>.jsonl` — chunk records (JSONL)
- `data/indexes/<strategy>/index.faiss` + `chunks.jsonl` — FAISS index + aligned metadata

## Switching chunking strategies

Use the **Chunking strategy** selector in the sidebar. Each strategy queries its own prebuilt index:

| Strategy | Method | Typical chunk |
|---|---|---|
| Fixed-size | 500-char windows, 50-char overlap, whitespace-aligned | mid-sentence fragments possible |
| Recursive | split on `\n\n`, `\n`, `. `, ` ` down to ≤500 chars | paragraph/sentence aligned |
| Section-aware | split on Markdown H1–H3 headings, heading kept as metadata and prepended to text | whole topical section |

The **Top-k retrieved chunks** slider controls how many chunks are passed to the LLM (and shown in the sources panel).

## Optional OpenAI-compatible API mode

In the sidebar choose **OpenAI-compatible API** and fill in:

- **API base URL** (e.g. `https://api.openai.com/v1`, or any compatible endpoint such as a local vLLM/LM Studio server)
- **API key** (password field; leave blank for keyless local endpoints)
- **API model** (e.g. `gpt-4o-mini`)

Defaults can be pre-set via `.env` (see `.env.example`).

## Safety-constrained behaviour

Implemented in `rag/safety.py` and enforced in the app:

- **Grounded answers only.** The prompt instructs the model to answer solely from retrieved passages.
- **Evidence floor.** If the best retrieval cosine similarity is below `0.35`, the app refuses with "the documents do not provide enough evidence" — without calling the LLM at all.
- **No certification claims.** The system prompt forbids claiming legal, regulatory, structural, or compliance certification.
- **Certification-question detection.** Questions matching certification/compliance patterns get a standing disclaimer: the system can summarise the documents but cannot certify compliance.
- Every answer shows a **grounding note** (strong / moderate / weak with the similarity score) and a collapsible **Retrieved sources** panel with document name, chunk id, similarity score, and snippet.

## Evaluation

`evaluation/questions.csv` contains 40 questions: 30 in-scope, 5 certification-type, 5 out-of-scope.

```bash
python scripts/evaluate.py              # retrieval-only (fast, no LLM needed)
python scripts/evaluate.py --generate   # also generate answers via Ollama
```

Writes `evaluation/results.csv` with per-question, per-strategy: top-1 document, top-1 similarity, hit@k, grounding verdict, and certification flag, plus a hit@k summary per strategy.

### Efficiency metrics

```bash
python scripts/measure_efficiency.py
```

Times chunking/index-build (in memory, does not touch `data/indexes/`) and per-question retrieval latency for each strategy against the already-committed indexes. Writes `evaluation/efficiency_metrics.csv`, `evaluation/efficiency_metrics.md`, and `evaluation/efficiency_chart_data.csv`.

### Manual answer-quality sample

`evaluation/manual_answer_quality_sample.csv` and `evaluation/manual_answer_quality_summary.md` are a hand-scored 10-question sample (factual correctness, source support, unsafe-compliance-wording, refusal appropriateness) drawn from a `--generate` run of `evaluation/results.csv` — not regenerated by a script; re-derive by re-running `python scripts/evaluate.py --generate` and re-scoring a fresh sample by hand.

## Evaluation notebook

`notebooks/evaluation_walkthrough.ipynb` is a reproducible walkthrough of the
evaluation results (loads `evaluation/questions.csv` and `evaluation/results.csv`,
computes hit@k / certification-detection / refusal metrics per chunking strategy,
and generates report figures). It does not call the Streamlit app — this repo has
no HTTP API, so the notebook evaluates via the repository's own `scripts/evaluate.py`
output rather than the UI.

```bash
source .venv/bin/activate
pip install matplotlib  # already in requirements.txt; jupyter/ipykernel needed to run the notebook itself
jupyter notebook notebooks/evaluation_walkthrough.ipynb
```

Run all cells top to bottom from the repository root. It regenerates three figures
under `results/figures/` (`graph_1_inscope_hitk.png`, `graph_2_safeguard_outcomes.png`,
`graph_3_generation_run_summary.png`). To refresh the underlying data first, see
"Rebuilding the indexes" and "Evaluation" above, then re-run the notebook.

## Repository layout

```
app/streamlit_app.py      Streamlit UI
rag/chunking.py           three chunking strategies (plain Python, no LangChain)
rag/embeddings.py         all-MiniLM-L6-v2 wrapper (normalised vectors)
rag/indexing.py           FAISS build/load per strategy
rag/retrieval.py          top-k cosine retrieval
rag/generation.py         Ollama + OpenAI-compatible clients, prompt builder
rag/safety.py             evidence floor, certification guardrails
data/sample_documents/    6 synthetic construction guidance docs (Markdown)
data/raw_sources/hse/     40 real HSE construction guidance pages (Markdown, OGL v3.0)
data/processed/           chunk JSONL per strategy (generated)
data/indexes/             FAISS index per strategy (generated)
data/sources.csv          document manifest
data/rejected_sources.csv HSE sources that failed to fetch/clean (if any)
scripts/build_indexes.py     reproducible index build (data/sample_documents/ only)
scripts/fetch_hse_sources.py fetches + cleans the 40 HSE pages into data/raw_sources/hse/
scripts/seed_hse_corpus.py   opt-in: builds indexes over sample_documents + raw_sources/hse
scripts/evaluate.py       retrieval evaluation
evaluation/questions.csv  evaluation question set
evaluation/results.csv    evaluation output (generated)
notebooks/evaluation_walkthrough.ipynb  reproducible evaluation walkthrough notebook
results/figures/          report figures generated by the notebook
```

## Real-world source corpus (optional)

In addition to the synthetic sample documents, `data/raw_sources/hse/` holds 40
UK Health and Safety Executive (HSE) construction guidance pages, fetched and
cleaned to Markdown (headings preserved, navigation/cookie/footer/"Is this page
useful?" chrome stripped, no paraphrasing). This is an **opt-in** addition:

```bash
python scripts/fetch_hse_sources.py   # re-fetch/refresh the HSE markdown docs
python scripts/seed_hse_corpus.py     # build indexes over sample_documents + raw_sources/hse
```

`scripts/build_indexes.py` is unaffected and continues to index only
`data/sample_documents/` by default.

Contains public sector information licensed under the Open Government Licence
v3.0: <https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/>

## Notes and limitations

- The sample documents are **synthetic educational material** written for this assignment (license: CC0). They are not real regulatory guidance and the system must not be used for real construction decisions.
- The HSE pages under `data/raw_sources/hse/` are real regulatory guidance, licensed under the Open Government Licence v3.0; see `data/sources.csv` for per-document provenance (source URL, retrieval date, category).
- `qwen2.5:0.5b` is deliberately small so the stack runs on modest hardware; answer quality is limited and the assignment focus is on **retrieval** differences between chunking strategies.
- FAISS `IndexFlatIP` over normalised embeddings gives exact cosine search; fine at this corpus size.
