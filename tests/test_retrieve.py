"""Retrieval quality and redaction checks (still no network)."""

from __future__ import annotations

import re

from app.ingest import get_vectorstore
from app.privacy import SSN_DASHED_RE
from app.retrieve import retrieve


def test_pto_query_returns_pto_section(ingested) -> None:
    hits = retrieve("What is the PTO policy?", "employee", k=4)
    assert hits
    assert any(
        "PTO" in h.section or "Working Hours" in h.section or "PTO" in h.text for h in hits
    )


def test_public_salary_query_never_restricted(ingested) -> None:
    hits = retrieve("What is user X's salary?", "public", k=4)
    assert all(h.classification == "public" for h in hits)


def test_index_does_not_store_raw_ssn(ingested) -> None:
    store = get_vectorstore(create=False)
    assert store is not None
    docs = store._collection.get(include=["documents"]).get("documents") or []
    assert docs
    for text in docs:
        assert SSN_DASHED_RE.search(text) is None
        assert re.search(r"\b\d{3}-\d{2}-\d{4}\b", text) is None
    joined = "\n".join(docs)
    assert "[SSN_REDACTED]" in joined


def test_ingest_counts_all_classifications(ingested) -> None:
    store = get_vectorstore(create=False)
    assert store is not None
    metas = store._collection.get(include=["metadatas"]).get("metadatas") or []
    labels = {m.get("classification") for m in metas}
    assert labels == {"public", "internal", "restricted"}
