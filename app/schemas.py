"""Pydantic v2 request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    # Stand-in for a JWT claim. Unknown values are treated as public by acl.py.
    role: str = "public"


class Citation(BaseModel):
    chunk_id: str
    page: int
    section: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    blocked: bool
    block_reason: str | None
    route: str
    role: str
    latency_ms: float


class HealthResponse(BaseModel):
    status: str
    collection: str
    chunk_count: int


class IngestResponse(BaseModel):
    ok: bool
    counts: dict[str, int]
    total: int
