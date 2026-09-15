"""ACL is a Chroma metadata pre-filter, not a Python post-filter and not the LLM."""

from __future__ import annotations

from app.acl import chroma_where, normalize_role
from app.config import get_embeddings
from app.ingest import get_vectorstore
from app.retrieve import retrieve


def test_unknown_role_is_public() -> None:
    assert normalize_role("superadmin") == "public"
    assert normalize_role(None) == "public"
    assert "restricted" not in chroma_where("superadmin")["classification"]["$in"]


def test_employee_salary_returns_zero_restricted(ingested) -> None:
    hits = retrieve("What is user X's salary?", "employee", k=4)
    restricted = [h for h in hits if h.classification == "restricted"]
    assert restricted == []


def test_admin_salary_returns_payroll_chunk(ingested) -> None:
    hits = retrieve("What is user X's salary?", "admin", k=4)
    restricted = [h for h in hits if h.classification == "restricted"]
    assert len(restricted) >= 1
    assert any(
        "payroll" in h.section.lower() or "user x" in h.text.lower() for h in restricted
    )


def test_hr_can_see_restricted(ingested) -> None:
    hits = retrieve("What is user X's salary?", "hr", k=4)
    assert any(h.classification == "restricted" for h in hits)


def test_retrieve_passes_where_into_chroma(ingested, monkeypatch) -> None:
    """Would fail if retrieve fetched everything and filtered in Python."""
    from app import retrieve as retrieve_mod

    captured: dict[str, object] = {}
    real = retrieve_mod._search

    def wrapped(query: str, where: dict[str, object], k: int):
        captured["where"] = where
        captured["query"] = query
        return real(query, where, k)

    monkeypatch.setattr(retrieve_mod, "_search", wrapped)
    retrieve_mod.retrieve("What is user X's salary?", "employee", k=4)
    assert captured["where"] == chroma_where("employee")
    allowed = captured["where"]["classification"]["$in"]  # type: ignore[index]
    assert "restricted" not in allowed
    assert "public" in allowed
    assert "internal" in allowed


def test_employee_where_on_chroma_returns_no_restricted(ingested) -> None:
    """Query the collection the same way retrieve does. Restricted must be
    invisible even at k larger than the restricted set (post-filter would
    drop them after the fact; pre-filter never returns them).
    """
    store = get_vectorstore(create=False)
    assert store is not None
    collection = store._collection
    total = collection.count()
    assert total > 0
    embedding = get_embeddings().embed_query("What is user X's salary?")
    raw = collection.query(
        query_embeddings=[embedding],
        n_results=min(20, total),
        where=chroma_where("employee"),
        include=["metadatas"],
    )
    metas = (raw.get("metadatas") or [[]])[0]
    assert metas, "employee filter should still see public/internal chunks"
    assert all(m.get("classification") != "restricted" for m in metas)

    unfiltered = collection.get(include=["metadatas"])
    assert any(m.get("classification") == "restricted" for m in (unfiltered.get("metadatas") or []))
