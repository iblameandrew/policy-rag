"""PDF → heading-aware chunks → Chroma. SSNs redacted before upsert."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.acl import allowed_roles_for_classification
from app.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    DOC_ID,
    chroma_dir,
    get_embeddings,
)
from app.privacy import redact_ssn_tokens

logger = logging.getLogger("policyrag.ingest")

HEADING_RE = re.compile(r"(?m)^#\s+(.+?)\s*$")

# First matching rule wins. Payroll appendix must beat generic "pay" language.
_SECTION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"payroll examples|appendix a", re.IGNORECASE), "restricted"),
    (re.compile(r"compensation philosophy", re.IGNORECASE), "internal"),
)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    page: int
    section: str
    classification: str
    allowed_roles: list[str]
    source: str
    doc_id: str
    chunk_index: int
    content_hash: str
    metadata: dict[str, str | int] = field(default_factory=dict)


@dataclass
class IngestStats:
    counts: dict[str, int]
    total: int


def classification_for_heading(heading: str) -> str:
    for pattern, label in _SECTION_RULES:
        if pattern.search(heading):
            return label
    return "public"


def _extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(pdf_path))
    pages: list[tuple[int, str]] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # pypdf may glue lines together; put `# N. ...` headings back on their own line.
        text = re.sub(r"\s+(#\s+\d+\.\s+)", r"\n\1", text)
        pages.append((idx, text))
    return pages


def _assign_pages_to_offsets(pages: list[tuple[int, str]]) -> tuple[str, list[tuple[int, int]]]:
    """Join pages and remember (char_start, page_number)."""
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    cursor = 0
    for page_no, text in pages:
        spans.append((cursor, page_no))
        parts.append(text)
        cursor += len(text)
        parts.append("\n")
        cursor += 1
    return "".join(parts), spans


def _page_at(offset: int, spans: list[tuple[int, int]]) -> int:
    page = 1
    for start, page_no in spans:
        if start <= offset:
            page = page_no
        else:
            break
    return page


def _split_sections(full_text: str) -> list[tuple[str, str, int]]:
    """Return (heading, body, start_offset) for each `#` section."""
    matches = list(HEADING_RE.finditer(full_text))
    if not matches:
        return [("Document", full_text.strip(), 0)]
    sections: list[tuple[str, str, int]] = []
    preamble = full_text[: matches[0].start()].strip()
    if preamble:
        sections.append(("Preamble", preamble, 0))
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        body = full_text[body_start:body_end].strip()
        sections.append((heading, body, match.start()))
    return sections


def build_chunks(pdf_path: Path) -> list[Chunk]:
    pages = _extract_pages(pdf_path)
    full_text, spans = _assign_pages_to_offsets(pages)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n# ", "\n\n", "\n", " ", ""],
    )
    chunks: list[Chunk] = []
    chunk_index = 0
    source = pdf_path.name
    for heading, body, start_offset in _split_sections(full_text):
        classification = classification_for_heading(heading)
        allowed = list(allowed_roles_for_classification(classification))
        pieces = splitter.split_text(f"# {heading}\n\n{body}") if body else [f"# {heading}"]
        for piece in pieces:
            redacted = redact_ssn_tokens(piece)
            content_hash = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
            chunk_id = hashlib.sha256(
                f"{DOC_ID}:{chunk_index}:{content_hash}".encode("utf-8")
            ).hexdigest()[:16]
            page = _page_at(start_offset, spans)
            if classification == "restricted" and not allowed:
                raise RuntimeError(f"restricted chunk {chunk_id} lacks allowed_roles")
            meta: dict[str, str | int] = {
                "doc_id": DOC_ID,
                "source": source,
                "page": page,
                "chunk_index": chunk_index,
                "section": heading,
                "classification": classification,
                "allowed_roles": ",".join(allowed),
                "content_hash": content_hash,
            }
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=redacted,
                    page=page,
                    section=heading,
                    classification=classification,
                    allowed_roles=allowed,
                    source=source,
                    doc_id=DOC_ID,
                    chunk_index=chunk_index,
                    content_hash=content_hash,
                    metadata=meta,
                )
            )
            chunk_index += 1
    _assert_restricted_roles(chunks)
    return chunks


def _assert_restricted_roles(chunks: list[Chunk]) -> None:
    for chunk in chunks:
        if chunk.classification != "restricted":
            continue
        if not chunk.allowed_roles:
            raise RuntimeError(f"restricted chunk {chunk.chunk_id} lacks allowed_roles")
        if set(chunk.allowed_roles) != {"hr", "admin"}:
            raise RuntimeError(
                f"restricted chunk {chunk.chunk_id} has allowed_roles={chunk.allowed_roles}"
            )


def _chroma_client():
    import chromadb

    path = chroma_dir()
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def reset_collection() -> None:
    client = _chroma_client()
    existing = {c.name for c in client.list_collections()}
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)


def get_vectorstore(*, create: bool = True):
    from langchain_community.vectorstores import Chroma

    client = _chroma_client()
    names = {c.name for c in client.list_collections()}
    if COLLECTION_NAME not in names and not create:
        return None
    return Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=str(chroma_dir()),
        embedding_function=get_embeddings(),
        client=client,
    )


def collection_count() -> int:
    client = _chroma_client()
    names = {c.name for c in client.list_collections()}
    if COLLECTION_NAME not in names:
        return 0
    return client.get_collection(COLLECTION_NAME).count()


def ingest_pdf(pdf_path: Path, *, reset: bool = True) -> IngestStats:
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    chunks = build_chunks(pdf_path)
    if reset:
        reset_collection()
    store = get_vectorstore(create=True)
    assert store is not None
    store.add_texts(
        texts=[c.text for c in chunks],
        metadatas=[c.metadata for c in chunks],
        ids=[c.chunk_id for c in chunks],
    )
    counts: dict[str, int] = {"public": 0, "internal": 0, "restricted": 0}
    for chunk in chunks:
        counts[chunk.classification] = counts.get(chunk.classification, 0) + 1
    stats = IngestStats(counts=counts, total=len(chunks))
    logger.info(
        "ingested total=%s public=%s internal=%s restricted=%s",
        stats.total,
        counts.get("public", 0),
        counts.get("internal", 0),
        counts.get("restricted", 0),
    )
    print(
        f"ingested {stats.total} chunks "
        f"public={counts.get('public', 0)} "
        f"internal={counts.get('internal', 0)} "
        f"restricted={counts.get('restricted', 0)}"
    )
    if counts.get("restricted", 0) < 1:
        raise RuntimeError("ingest produced zero restricted chunks; payroll appendix missing")
    if counts.get("internal", 0) < 1:
        raise RuntimeError("ingest produced zero internal chunks; compensation philosophy missing")
    if counts.get("public", 0) < 1:
        raise RuntimeError("ingest produced zero public chunks")
    return stats
