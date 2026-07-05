"""Safety-constrained behaviour: grounding checks and certification guardrails."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Below this best-chunk cosine similarity, context is considered too weak to
# answer from and the app refuses without calling the LLM.
SIMILARITY_FLOOR = 0.35

# Above this, grounding is considered strong; between floor and this it is
# treated as usable but flagged to the user as moderate.
STRONG_THRESHOLD = 0.5

REFUSAL_MESSAGE = (
    "The provided documents do not contain enough evidence to answer this "
    "question reliably, so I will not attempt an answer. Try rephrasing the "
    "question, or check whether the topic is covered by the sample documents."
)

CERTIFICATION_DISCLAIMER = (
    "This question appears to ask about certification, compliance, or "
    "regulatory approval. This system can summarise what the provided "
    "documents say, but it cannot certify legal, regulatory, structural, or "
    "compliance status. Always consult a qualified professional for "
    "certification decisions."
)

SAFETY_PREAMBLE = (
    "You are a careful assistant answering questions about construction site "
    "documentation.\n"
    "Rules you must follow strictly:\n"
    "1. Answer ONLY from the context passages provided below. Do not use any "
    "outside knowledge.\n"
    "2. If the context does not contain the answer, say that the documents do "
    "not provide enough evidence. Do not guess.\n"
    "3. Never claim or imply legal, regulatory, structural, or compliance "
    "certification. You may summarise what the documents say, nothing more.\n"
    "4. Keep the answer concise and factual, and mention which document the "
    "information comes from when possible."
)

_CERTIFICATION_PATTERNS = [
    r"\bcertif\w*",
    r"\bcompli\w*",
    r"\bsign[- ]?off\b",
    r"\bapproved for\b",
    r"\bmeets? (the )?(building )?(code|codes|regulation|regulations|standard|standards)\b",
    r"\blegal(ly)?\b",
    r"\bregulator\w*",
    r"\bwarrant\w*",
]
_CERTIFICATION_RE = re.compile("|".join(_CERTIFICATION_PATTERNS), re.IGNORECASE)


@dataclass
class SafetyAssessment:
    grounding: str          # "strong" | "moderate" | "weak"
    certification_flag: bool
    best_score: float
    notes: str

    @property
    def should_answer(self) -> bool:
        return self.grounding != "weak"


def is_certification_question(question: str) -> bool:
    return bool(_CERTIFICATION_RE.search(question))


def assess(question: str, retrieved: list[dict]) -> SafetyAssessment:
    """Combine retrieval strength and question type into a safety verdict."""
    best_score = max((r["score"] for r in retrieved), default=0.0)
    cert = is_certification_question(question)

    if not retrieved or best_score < SIMILARITY_FLOOR:
        grounding = "weak"
        notes = (f"Best similarity {best_score:.3f} is below the evidence "
                 f"floor of {SIMILARITY_FLOOR}. Answer withheld.")
    elif best_score < STRONG_THRESHOLD:
        grounding = "moderate"
        notes = (f"Best similarity {best_score:.3f} indicates partial support. "
                 "Answer generated from context, but verify against sources.")
    else:
        grounding = "strong"
        notes = (f"Best similarity {best_score:.3f}. Answer grounded in the "
                 "retrieved passages shown below.")

    return SafetyAssessment(grounding=grounding, certification_flag=cert,
                            best_score=best_score, notes=notes)
