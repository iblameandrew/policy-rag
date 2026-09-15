"""FastAPI entry. Privacy gate runs before retrieve and before the LLM."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.acl import normalize_role
from app.config import COLLECTION_NAME, pdf_path
from app.generate import generate_answer
from app.ingest import collection_count, ingest_pdf
from app.privacy import REFUSAL_MESSAGE, evaluate
from app.retrieve import retrieve
from app.schemas import AskRequest, AskResponse, Citation, HealthResponse, IngestResponse

logger = logging.getLogger("policyrag")
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")


def _ensure_ingested() -> None:
    if collection_count() > 0:
        return
    pdf = pdf_path()
    if not pdf.is_file():
        from scripts.generate_handbook import write_handbook

        write_handbook(pdf)
    logger.info("collection empty; ingesting %s", pdf)
    ingest_pdf(pdf)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _ensure_ingested()
    yield


app = FastAPI(title="PolicyRAG", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        collection=COLLECTION_NAME,
        chunk_count=collection_count(),
    )


@app.post("/ingest", response_model=IngestResponse)
def ingest_endpoint() -> IngestResponse:
    stats = ingest_pdf(pdf_path())
    return IngestResponse(ok=True, counts=stats.counts, total=stats.total)


@app.post("/ask")
def ask(req: AskRequest) -> JSONResponse:
    started = time.perf_counter()
    role = normalize_role(req.role)
    decision = evaluate(req.query)
    if decision.blocked:
        payload = AskResponse(
            answer=decision.message or REFUSAL_MESSAGE,
            citations=[],
            blocked=True,
            block_reason=decision.reason,
            route="privacy_gate",
            role=role,
            latency_ms=_latency_ms(started),
        )
        return JSONResponse(status_code=403, content=_dump(payload))

    chunks = retrieve(req.query, role)
    answer = generate_answer(req.query, chunks)
    citations = [
        Citation(chunk_id=c.chunk_id, page=c.page, section=c.section) for c in chunks
    ]
    payload = AskResponse(
        answer=answer,
        citations=citations,
        blocked=False,
        block_reason=None,
        route="rag",
        role=role,
        latency_ms=_latency_ms(started),
    )
    return JSONResponse(status_code=200, content=_dump(payload))


def _latency_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _dump(model: AskResponse) -> dict[str, Any]:
    return model.model_dump()
