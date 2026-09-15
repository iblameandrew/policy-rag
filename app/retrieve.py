"""Role-scoped similarity search. Chroma `where` is the ACL."""

from __future__ import annotations

from dataclasses import dataclass

from app.acl import allowed_classifications, chroma_where, normalize_role
from app.config import get_embeddings
from app.ingest import get_vectorstore


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    page: int
    section: str
    classification: str
    allowed_roles: list[str]


def _search(query: str, where: dict[str, object], k: int) -> list[RetrievedChunk]:
    """Call Chroma with a metadata pre-filter. Tests monkeypatch this hook."""
    store = get_vectorstore(create=False)
    if store is None:
        return []
    collection = store._collection  # noqa: SLF001 — native where= pre-filter
    count = collection.count()
    if count == 0:
        return []
    n_results = min(k, count)
    embedding = get_embeddings().embed_query(query)
    raw = collection.query(
        query_embeddings=[embedding],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas"],
    )
    ids = (raw.get("ids") or [[]])[0]
    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]
    hits: list[RetrievedChunk] = []
    for cid, text, meta in zip(ids, docs, metas, strict=False):
        meta = meta or {}
        roles_raw = str(meta.get("allowed_roles", ""))
        hits.append(
            RetrievedChunk(
                chunk_id=str(cid),
                text=text or "",
                page=int(meta.get("page", 0) or 0),
                section=str(meta.get("section", "")),
                classification=str(meta.get("classification", "")),
                allowed_roles=[r for r in roles_raw.split(",") if r],
            )
        )
    return hits


def retrieve(query: str, role: str, k: int = 4) -> list[RetrievedChunk]:
    """Return chunks the role may see. Empty list rather than guessing.

    Authorization is the Chroma `where` clause. If a disallowed
    classification appears anyway, raise — do not silently post-filter.
    """
    normalized = normalize_role(role)
    where = chroma_where(normalized)
    if not where:
        raise RuntimeError("ACL where clause missing; fail closed")
    hits = _search(query, where, k)
    allowed = set(allowed_classifications(normalized))
    for hit in hits:
        if hit.classification not in allowed:
            raise RuntimeError(
                f"ACL leak: role={normalized} retrieved classification={hit.classification}"
            )
    return hits
