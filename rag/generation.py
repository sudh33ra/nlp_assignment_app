"""LLM clients: local Ollama (default) and OpenAI-compatible APIs."""

from __future__ import annotations

import os

import requests

from rag.safety import SAFETY_PREAMBLE

DEFAULT_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")

REQUEST_TIMEOUT = 120  # seconds; small local models can be slow on CPU


class GenerationError(Exception):
    """User-presentable error from an LLM backend."""


def build_prompt(question: str, chunks: list[dict]) -> str:
    context_blocks = []
    for i, chunk in enumerate(chunks, 1):
        section = f" — section: {chunk['section']}" if chunk.get("section") else ""
        context_blocks.append(
            f"[Passage {i}] (document: {chunk['doc_name']}{section})\n{chunk['text']}"
        )
    context = "\n\n".join(context_blocks)
    return (
        f"{SAFETY_PREAMBLE}\n\n"
        f"Context passages:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer:"
    )


def generate_ollama(prompt: str, model: str = DEFAULT_OLLAMA_MODEL,
                    base_url: str = DEFAULT_OLLAMA_BASE_URL) -> str:
    url = f"{base_url.rstrip('/')}/api/generate"
    try:
        resp = requests.post(url, json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ConnectionError as exc:
        raise GenerationError(
            f"Cannot reach Ollama at {base_url}. Is the Ollama container "
            "running? Start everything with: docker compose up"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise GenerationError(
            f"Ollama timed out after {REQUEST_TIMEOUT}s. The model may still "
            "be loading; try again in a moment."
        ) from exc

    if resp.status_code == 404 or (resp.status_code >= 400 and "not found" in resp.text.lower()):
        raise GenerationError(
            f"Model '{model}' is not available in Ollama. Pull it with:\n"
            f"docker compose exec ollama ollama pull {model}"
        )
    if resp.status_code >= 400:
        raise GenerationError(f"Ollama error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    answer = data.get("response", "").strip()
    if not answer:
        raise GenerationError("Ollama returned an empty response.")
    return answer


def generate_openai_compatible(prompt: str, model: str, base_url: str,
                               api_key: str = "") -> str:
    if not base_url:
        raise GenerationError("API base URL is required for API mode.")
    if not model:
        raise GenerationError("API model name is required for API mode.")

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.post(url, headers=headers, json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ConnectionError as exc:
        raise GenerationError(f"Cannot reach API at {base_url}.") from exc
    except requests.exceptions.Timeout as exc:
        raise GenerationError(f"API timed out after {REQUEST_TIMEOUT}s.") from exc

    if resp.status_code == 401:
        raise GenerationError("API rejected the key (401 Unauthorized).")
    if resp.status_code >= 400:
        raise GenerationError(f"API error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise GenerationError(f"Unexpected API response shape: {str(data)[:300]}") from exc
