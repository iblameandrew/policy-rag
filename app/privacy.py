"""Local SSN / Social Security intent gate.

No embeddings, no vector store, no LLM. A hit must short-circuit the /ask path.
This module must not import a vector database client (enforced in tests).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("policyrag.privacy")

# US dashed SSN.
SSN_DASHED_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# Nine digits in a row (only counted when nearby context says SSN).
SSN_COMPACT_RE = re.compile(r"\b\d{9}\b")

INTENT_PHRASES: tuple[str, ...] = (
    "social security",
    "social-security",
    "ssn",
    "ss#",
    "ss #",
    "ssn#",
    "número de seguro social",
    "numero de seguro social",
    "nmero de seguro social",
    "seguro social",
    "soc sec",
    "social security number",
    "social security no",
)

_CONTEXT_WORDS_RE = re.compile(
    r"ssn|ss#|social|security|seguro|ssn#|itin|tax.?id",
    re.IGNORECASE,
)

REFUSAL_MESSAGE = (
    "I can't help with Social Security Numbers. Contact HR through the official channel."
)


@dataclass(frozen=True)
class PrivacyDecision:
    blocked: bool
    reason: str | None
    message: str | None


def _normalize(query: str) -> str:
    return query.casefold()


def _has_intent_phrase(query: str) -> bool:
    lowered = _normalize(query)
    collapsed = re.sub(r"\s+", " ", lowered)
    for phrase in INTENT_PHRASES:
        if phrase in collapsed:
            return True
    # ss# with optional space already in the list; also catch "ss #"
    if re.search(r"\bss\s*#", lowered):
        return True
    return False


def _has_dashed_ssn(query: str) -> bool:
    return SSN_DASHED_RE.search(query) is not None


def _has_compact_ssn_with_context(query: str) -> bool:
    if SSN_COMPACT_RE.search(query) is None:
        return False
    return _CONTEXT_WORDS_RE.search(query) is not None


def scrub_ssn_for_log(text: str) -> str:
    """Replace SSN-shaped tokens so logs never store raw digits."""
    scrubbed = SSN_DASHED_RE.sub("[SSN]", text)
    # Only compact 9-digit runs near SSN context; still mask all 9-digit groups
    # in a string that already looks like an SSN question.
    if _has_intent_phrase(text) or _CONTEXT_WORDS_RE.search(text):
        scrubbed = SSN_COMPACT_RE.sub("[SSN]", scrubbed)
    return scrubbed


def redact_ssn_tokens(text: str) -> str:
    """Strip SSN-shaped tokens from text before vector upsert."""
    redacted = SSN_DASHED_RE.sub("[SSN_REDACTED]", text)
    redacted = SSN_COMPACT_RE.sub("[SSN_REDACTED]", redacted)
    return redacted


def evaluate(query: str) -> PrivacyDecision:
    """Return a block decision. Callers must not retrieve or generate on hit."""
    if _has_intent_phrase(query) or _has_dashed_ssn(query) or _has_compact_ssn_with_context(query):
        logger.info("blocked=ssn_intent query=%s", scrub_ssn_for_log(query))
        return PrivacyDecision(blocked=True, reason="ssn_intent", message=REFUSAL_MESSAGE)
    return PrivacyDecision(blocked=False, reason=None, message=None)
